"""Qoo10 Japan scraping: sales badge/rank, review count, rating, stock status.

Fetches pages via headless Chromium (Playwright) rather than a bare `requests`
call — Qoo10 was serving its anti-bot block page (HTTP 200, so raise_for_status()
never caught it) even with full browser-like headers, so header spoofing alone
wasn't enough (see scripts/browser_fetch.py). The rendered HTML is then parsed
with BeautifulSoup exactly as before; only the fetch layer changed.

Selectors verified (2026-07) against a real saved product page
(qoo10.jp/g/680631925, "[CENTELLIAN24]センテリアン24 マデカクリーム"): the
page ships a server-rendered `<script type="application/ld+json">` schema.org
Product block with real rating/review count/stock/price — this is the
reliable source, not the DOM. The DOM's own `.review_count`/`.review_score
.score` elements are populated by client-side JS after load; even now that a
real browser executes that JS, JSON-LD stays the simpler and equally-correct
source, so it's still what's parsed.

No per-product bestseller badge ("ベストN位") was present on the one real
page inspected, so `_parse_sales_badge_and_rank`'s regex is unverified against
an actual example and will likely return None for most products; that's
expected per PRD §9 (rank badges only show for currently-ranked products).

Every field fails safe to None + a warning log rather than raising, matching
collect_amazon.py's pattern.
"""

import json
import logging
import random
import re
import time
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from scripts.browser_fetch import RenderedPageFetcher
from scripts.config import QOO10_PRODUCTS

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.qoo10.jp"
REQUEST_DELAY_RANGE_SECONDS = (2, 5)  # randomized, not fixed — be polite to the same host


def _polite_delay() -> None:
    time.sleep(random.uniform(*REQUEST_DELAY_RANGE_SECONDS))


def _get(fetcher: RenderedPageFetcher, url: str, wait_selector: str | None = None) -> BeautifulSoup | None:
    html = fetcher.fetch(url, wait_selector=wait_selector)
    if html is None:
        return None
    return BeautifulSoup(html, "html.parser")


def _resolve_goods_no(fetcher: RenderedPageFetcher, search_keyword: str) -> str | None:
    soup = _get(fetcher, f"{BASE_URL}/s/{quote_plus(search_keyword)}?keyword={quote_plus(search_keyword)}")
    if soup is None:
        return None
    for a in soup.select("a[href*='/g/']"):
        match = re.search(r"/g/(\d+)", a.get("href", ""))
        if match:
            return match.group(1)
    logger.warning("No product link found in search results for keyword %r", search_keyword)
    return None


def _looks_like_error_page(soup: BeautifulSoup) -> bool:
    """Qoo10's anti-bot block page is served with HTTP 200 (not a 4xx/5xx), so
    resp.raise_for_status() never catches it — it has to be detected from the
    page content itself, or a block silently produces an all-None result with
    no logged reason at all.
    """
    text = soup.get_text(" ", strip=True)
    return bool(re.search(r"エラーが発生しました|523 Error", text))


def _parse_json_ld_product(soup: BeautifulSoup) -> dict:
    for tag in soup.select("script[type='application/ld+json']"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("@type") == "Product":
                return candidate
    return {}


def _parse_rating_and_reviews(json_ld: dict) -> tuple[float | None, int | None]:
    rating_block = json_ld.get("aggregateRating") or {}
    try:
        rating = float(rating_block["ratingValue"]) if rating_block.get("ratingValue") is not None else None
    except (TypeError, ValueError):
        rating = None
    try:
        review_count = int(rating_block["reviewCount"]) if rating_block.get("reviewCount") is not None else None
    except (TypeError, ValueError):
        review_count = None
    return rating, review_count


def _parse_sales_badge_and_rank(soup: BeautifulSoup) -> tuple[str | None, int | None]:
    try:
        text = soup.get_text(" ", strip=True)
        match = re.search(r"(ベスト\s*([\d,]+)\s*位)", text)
        if not match:
            return None, None
        return match.group(1), int(match.group(2).replace(",", ""))
    except AttributeError as exc:
        logger.warning("Failed to parse sales badge/rank: %s", exc)
        return None, None


def _parse_in_stock(json_ld: dict, soup: BeautifulSoup) -> bool | None:
    availability = (json_ld.get("offers") or {}).get("availability", "")
    if isinstance(availability, str) and availability:
        if "OutOfStock" in availability or "SoldOut" in availability:
            return False
        if "InStock" in availability:
            return True

    # Fall back to text scanning only if JSON-LD didn't have an offers block.
    try:
        text = soup.get_text(" ", strip=True)
        if re.search(r"品切れ|完売|sold\s*out", text, re.IGNORECASE):
            return False
        if re.search(r"カートに入れる|購入する|買い物かごに入れる", text):
            return True
        return None
    except AttributeError as exc:
        logger.warning("Failed to parse stock status: %s", exc)
        return None


def _collect_product(fetcher: RenderedPageFetcher, product_cfg: dict) -> dict:
    name = product_cfg["product"]
    goods_no = product_cfg.get("goods_no") or _resolve_goods_no(fetcher, product_cfg["search_keyword"])

    result = {
        "product": name,
        "sales_badge": None,
        "category_rank": None,
        "review_count": None,
        "rating": None,
        "in_stock": None,
        "source": "scrape",
    }

    if not goods_no:
        logger.warning("Skipping detail lookup for %r — no goods_no resolved", name)
        return result

    _polite_delay()
    soup = _get(fetcher, f"{BASE_URL}/g/{goods_no}", wait_selector="script[type='application/ld+json']")
    if soup is None:
        return result

    if _looks_like_error_page(soup):
        logger.warning(
            "Qoo10 returned a block/error page for goods_no=%s (HTTP 200 but not real product "
            "content — likely an anti-bot wall, see collect_qoo10.py module docstring)",
            goods_no,
        )
        return result

    json_ld = _parse_json_ld_product(soup)
    if not json_ld:
        logger.warning(
            "No JSON-LD Product data found for goods_no=%s — page structure may have changed "
            "(fetched %d chars of HTML)",
            goods_no, len(soup.get_text()),
        )
    result["rating"], result["review_count"] = _parse_rating_and_reviews(json_ld)
    result["sales_badge"], result["category_rank"] = _parse_sales_badge_and_rank(soup)
    result["in_stock"] = _parse_in_stock(json_ld, soup)
    return result


def collect_qoo10_data() -> list[dict]:
    results = []
    with RenderedPageFetcher(locale="ja-JP") as fetcher:
        for product_cfg in QOO10_PRODUCTS:
            try:
                results.append(_collect_product(fetcher, product_cfg))
            except Exception as exc:  # keep the whole run alive on unexpected failures
                logger.warning("Unexpected failure collecting %r: %s", product_cfg["product"], exc)
                results.append(
                    {
                        "product": product_cfg["product"],
                        "sales_badge": None,
                        "category_rank": None,
                        "review_count": None,
                        "rating": None,
                        "in_stock": None,
                        "source": "scrape",
                    }
                )
            _polite_delay()
    return results


if __name__ == "__main__":
    print(json.dumps(collect_qoo10_data(), ensure_ascii=False, indent=2))

"""Amazon scraping: estimated monthly sales, BSR, review count, rating, price, stock.

Fetches search/product-detail pages via headless Chromium (Playwright) rather
than a bare `requests` call — Amazon was flatly 503-ing plain HTTP requests
even from a residential IP with full browser-like headers, so header spoofing
alone wasn't enough (see scripts/browser_fetch.py). The rendered HTML is then
parsed with BeautifulSoup exactly as before; only the fetch layer changed.
Amazon's HTML is unstable and bot-defensive regardless, so every field is
parsed defensively: a failure to find one field logs a warning and leaves it
as None rather than aborting the whole product or run.
"""

import json
import logging
import random
import re
import time
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from scripts.analyze_sentiment import analyze_amazon_sentiment
from scripts.browser_fetch import RenderedPageFetcher
from scripts.config import PRODUCTS

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.amazon.com"
REQUEST_DELAY_RANGE_SECONDS = (2, 5)  # randomized, not fixed — a fixed interval is itself a bot signal
MAX_REVIEW_TEXTS = 20


def _polite_delay() -> None:
    time.sleep(random.uniform(*REQUEST_DELAY_RANGE_SECONDS))


def _get(fetcher: RenderedPageFetcher, url: str, wait_selector: str | None = None) -> BeautifulSoup | None:
    html = fetcher.fetch(url, wait_selector=wait_selector)
    if html is None:
        return None
    return BeautifulSoup(html, "html.parser")


def _resolve_asin(fetcher: RenderedPageFetcher, search_keyword: str) -> str | None:
    soup = _get(
        fetcher,
        f"{BASE_URL}/s?k={quote_plus(search_keyword)}",
        wait_selector="div[data-component-type='s-search-result']",
    )
    if soup is None:
        return None
    result = soup.select_one("div[data-component-type='s-search-result'][data-asin]")
    if result is None or not result.get("data-asin"):
        logger.warning("No search result ASIN found for keyword %r", search_keyword)
        return None
    return result["data-asin"]


def _parse_price(soup: BeautifulSoup) -> float | None:
    try:
        el = soup.select_one(".a-price .a-offscreen")
        if not el:
            return None
        return float(re.sub(r"[^\d.]", "", el.get_text()))
    except (ValueError, AttributeError) as exc:
        logger.warning("Failed to parse price: %s", exc)
        return None


def _parse_rating(soup: BeautifulSoup) -> float | None:
    try:
        el = soup.select_one("#acrPopover") or soup.select_one("span.a-icon-alt")
        text = el.get("title") if el and el.has_attr("title") else (el.get_text() if el else None)
        if not text:
            return None
        match = re.search(r"([\d.]+)\s+out of", text)
        return float(match.group(1)) if match else None
    except (ValueError, AttributeError) as exc:
        logger.warning("Failed to parse rating: %s", exc)
        return None


def _parse_review_count(soup: BeautifulSoup) -> int | None:
    try:
        el = soup.select_one("#acrCustomerReviewText")
        if not el:
            return None
        match = re.search(r"([\d,]+)", el.get_text())
        return int(match.group(1).replace(",", "")) if match else None
    except (ValueError, AttributeError) as exc:
        logger.warning("Failed to parse review count: %s", exc)
        return None

def _parse_in_stock(soup: BeautifulSoup) -> bool | None:
    try:
        el = soup.select_one("#availability")
        if not el:
            return None
        text = el.get_text(strip=True).lower()
        if "in stock" in text:
            return True
        if "unavailable" in text or "out of stock" in text:
            return False
        return None
    except AttributeError as exc:
        logger.warning("Failed to parse stock status: %s", exc)
        return None


def _parse_est_monthly_sales(soup: BeautifulSoup) -> int | None:
    try:
        text = soup.get_text(" ", strip=True)
        match = re.search(r"([\d,]+)\+?\s*bought in past month", text, re.IGNORECASE)
        return int(match.group(1).replace(",", "")) if match else None
    except AttributeError as exc:
        logger.warning("Failed to parse estimated monthly sales: %s", exc)
        return None


_REVIEW_PERMALINK_ID_RE = re.compile(r"/gp/customer-reviews/([A-Z0-9]+)")


def _parse_review_texts(soup: BeautifulSoup) -> list[str]:
    """Amazon's classic `data-hook="review"`/`"review-body"` cards are gone
    from the current /dp/ page — replaced by an "AI review highlights"
    snippet widget built on deploy-specific hashed CSS classes (e.g.
    `__SAR2l0zNyyuZ`) with no stable selector to hook. The one thing that
    *is* stable is each snippet's review permalink, `/gp/customer-reviews/
    {review_id}` — Amazon's long-standing review-detail URL scheme. Walking
    up from that anchor to the nearest ancestor whose text is wrapped in
    literal quote marks recovers that review's (truncated, "...Read more")
    snippet without depending on any class name at all.

    (`/product-reviews/{asin}` was tried as a from-scratch fallback but
    redirects anonymous requests to the Amazon sign-in page — not usable
    without storing Amazon account credentials.)
    """
    try:
        seen_ids = set()
        texts = []
        for a in soup.select("a[href^='/gp/customer-reviews/']"):
            match = _REVIEW_PERMALINK_ID_RE.search(a.get("href", ""))
            if not match or match.group(1) in seen_ids:
                continue

            snippet = None
            node = a
            for _ in range(8):  # bounded ancestor walk — bail out rather than risk an infinite/huge climb
                node = node.parent
                if node is None:
                    break
                text = node.get_text(" ", strip=True)
                if text.startswith('"') and text.count('"') >= 2:
                    snippet = text
                    break
            if not snippet:
                continue

            if snippet.endswith("Read more"):
                snippet = snippet[: -len("Read more")].strip()
            cleaned = snippet.strip('"').strip()
            if cleaned:
                seen_ids.add(match.group(1))
                texts.append(cleaned)
            if len(texts) >= MAX_REVIEW_TEXTS:
                break
        return texts
    except AttributeError as exc:
        logger.warning("Failed to parse review texts: %s", exc)
        return []


def _parse_category_and_bsr(soup: BeautifulSoup) -> tuple[str | None, int | None]:
    try:
        text = soup.get_text(" ", strip=True)
        match = re.search(r"#([\d,]+)\s+in\s+([A-Za-z0-9&' ]+?)(?=\s*(?:#|\(|$))", text)
        if not match:
            return None, None
        bsr = int(match.group(1).replace(",", ""))
        category = match.group(2).strip()
        return category, bsr
    except AttributeError as exc:
        logger.warning("Failed to parse category/BSR: %s", exc)
        return None, None


def _collect_product(fetcher: RenderedPageFetcher, product_cfg: dict) -> dict:
    name = product_cfg["product"]
    asin = product_cfg.get("asin") or _resolve_asin(fetcher, product_cfg["search_keyword"])

    result = {
        "product": name,
        "asin": asin,
        "est_monthly_sales": None,
        "category": None,
        "bsr": None,
        "review_count": None,
        "rating": None,
        "in_stock": None,
        "price": None,
        "source": "scrape",
        "sentiment_score": None,
        "sentiment_summary": "",
        "sentiment_confidence": "low",
    }

    if not asin:
        logger.warning("Skipping detail lookup for %r — no ASIN resolved", name)
        return result

    _polite_delay()
    soup = _get(fetcher, f"{BASE_URL}/dp/{asin}", wait_selector="#acrPopover, #availability")
    if soup is None:
        return result

    result["price"] = _parse_price(soup)
    result["rating"] = _parse_rating(soup)
    result["review_count"] = _parse_review_count(soup)
    result["in_stock"] = _parse_in_stock(soup)
    result["est_monthly_sales"] = _parse_est_monthly_sales(soup)
    result["category"], result["bsr"] = _parse_category_and_bsr(soup)

    # Review text is only used in-memory to feed sentiment analysis (PRD
    # copyright consideration) — never stored in the returned dict. Parsed
    # straight off the already-fetched /dp/ page's "top reviews" section
    # (same data-hook="review" markup Amazon uses on /product-reviews/ too),
    # rather than a separate /product-reviews/{asin} request — that URL
    # 404s for some ASINs (observed for B0H2DPL69S) even though the reviews
    # are right there on the product page.
    review_texts = _parse_review_texts(soup)
    if not review_texts:
        logger.warning("No review text found on product page for %r (asin=%s)", name, asin)
    sentiment = analyze_amazon_sentiment(review_texts)
    result["sentiment_score"] = sentiment["sentiment_score"]
    result["sentiment_summary"] = sentiment["sentiment_summary"]
    result["sentiment_confidence"] = sentiment["confidence"]

    return result


def collect_amazon_data() -> list[dict]:
    results = []
    with RenderedPageFetcher(locale="en-US") as fetcher:
        for product_cfg in PRODUCTS:
            try:
                results.append(_collect_product(fetcher, product_cfg))
            except Exception as exc:  # keep the whole run alive on unexpected failures
                logger.warning("Unexpected failure collecting %r: %s", product_cfg["product"], exc)
                results.append(
                    {
                        "product": product_cfg["product"],
                        "asin": product_cfg.get("asin"),
                        "est_monthly_sales": None,
                        "category": None,
                        "bsr": None,
                        "review_count": None,
                        "rating": None,
                        "in_stock": None,
                        "price": None,
                        "source": "scrape",
                        "sentiment_score": None,
                        "sentiment_summary": "",
                        "sentiment_confidence": "low",
                    }
                )
            _polite_delay()
    return results


if __name__ == "__main__":
    print(json.dumps(collect_amazon_data(), ensure_ascii=False, indent=2))

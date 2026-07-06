"""Amazon scraping: estimated monthly sales, BSR, review count, rating, price, stock.

Uses requests + BeautifulSoup against public search/product-detail pages
(no Product Advertising API, no paid scraping service). Amazon's HTML is
unstable and bot-defensive, so every field is parsed defensively: a failure
to find one field logs a warning and leaves it as None rather than aborting
the whole product or run.
"""

import json
import logging
import re
import time
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from scripts.config import PRODUCTS

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.amazon.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_TIMEOUT = 15
REQUEST_DELAY_SECONDS = 2  # be polite between requests to the same host


def _get(url: str) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as exc:
        logger.warning("Request failed for %s: %s", url, exc)
        return None


def _resolve_asin(search_keyword: str) -> str | None:
    soup = _get(f"{BASE_URL}/s?k={quote_plus(search_keyword)}")
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


def _collect_product(product_cfg: dict) -> dict:
    name = product_cfg["product"]
    asin = product_cfg.get("asin") or _resolve_asin(product_cfg["search_keyword"])

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
    }

    if not asin:
        logger.warning("Skipping detail lookup for %r — no ASIN resolved", name)
        return result

    time.sleep(REQUEST_DELAY_SECONDS)
    soup = _get(f"{BASE_URL}/dp/{asin}")
    if soup is None:
        return result

    result["price"] = _parse_price(soup)
    result["rating"] = _parse_rating(soup)
    result["review_count"] = _parse_review_count(soup)
    result["in_stock"] = _parse_in_stock(soup)
    result["est_monthly_sales"] = _parse_est_monthly_sales(soup)
    result["category"], result["bsr"] = _parse_category_and_bsr(soup)
    return result


def collect_amazon_data() -> list[dict]:
    results = []
    for product_cfg in PRODUCTS:
        try:
            results.append(_collect_product(product_cfg))
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
                }
            )
        time.sleep(REQUEST_DELAY_SECONDS)
    return results


if __name__ == "__main__":
    print(json.dumps(collect_amazon_data(), ensure_ascii=False, indent=2))

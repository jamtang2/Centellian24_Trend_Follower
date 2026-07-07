"""Tracked products and keywords for Centellian24_US_Monitor collection scripts."""

# Amazon flagship SKUs to track. `asin` may be left as None — collect_amazon.py
# will resolve it from the search results page and you can hardcode it here
# afterwards to pin the exact product (recommended once confirmed, since a
# product can drift out of search results over time).
PRODUCTS = [
    {
        "product": "마데카 크림 타임 리버스",
        "asin": None,
        "search_keyword": "Centellian24 Madecassoside Time Reverse Cream",
    },
    {
        "product": "360도 샷 PDRN 리프팅 아이크림",
        "asin": None,
        "search_keyword": "Centellian24 360 Shot PDRN Lifting Eye Cream",
    },
    {
        "product": "마데카 크림 액티브 리뉴 PDRN",
        "asin": None,
        "search_keyword": "Centellian24 Madecassoside Active Renew PDRN Cream",
    },
]

# Google Trends keywords (tracked for both US and JP regions).
TRENDS_KEYWORDS = ["Centellian24", "Madeca Cream"]

# Qoo10 Japan flagship SKUs to track. `goods_no` pins the numeric product ID
# from a qoo10.jp/g/{goods_no} URL (recommended once confirmed, same rationale
# as Amazon's `asin` above — avoids re-resolving via search each run).
# 680631925 confirmed (2026-07) against a real saved product page — see
# scripts/collect_qoo10.py docstring for the verified JSON-LD-based parsing
# approach.
QOO10_PRODUCTS = [
    {
        "product": "마데카 크림",
        "goods_no": "680631925",
        "search_keyword": "センテリアン24 マデカクリーム",
    },
]

"""Google Trends collection (US + JP) via the unofficial `pytrends` library."""

import json
import logging
import time

from pytrends.request import TrendReq

from scripts.config import TRENDS_KEYWORDS

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REGIONS = ["US", "JP"]
TIMEFRAME = "today 12-m"
MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 5


def _fetch_region(geo: str) -> dict:
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pytrends = TrendReq(hl="en-US", tz=540)
            pytrends.build_payload(TRENDS_KEYWORDS, timeframe=TIMEFRAME, geo=geo)
            df = pytrends.interest_over_time()
            if df.empty:
                logger.warning("Empty Trends response for geo=%s", geo)
                return {kw: None for kw in TRENDS_KEYWORDS}
            latest = df.iloc[-1]
            return {kw: int(latest[kw]) for kw in TRENDS_KEYWORDS}
        except Exception as exc:  # pytrends raises assorted request/response errors
            last_exc = exc
            logger.warning(
                "Trends fetch failed for geo=%s (attempt %d/%d): %s",
                geo, attempt, MAX_RETRIES, exc,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)

    logger.warning("Giving up on geo=%s after %d attempts: %s", geo, MAX_RETRIES, last_exc)
    return {kw: None for kw in TRENDS_KEYWORDS}


def collect_trends_data() -> dict:
    return {geo: _fetch_region(geo) for geo in REGIONS}


if __name__ == "__main__":
    print(json.dumps(collect_trends_data(), ensure_ascii=False, indent=2))

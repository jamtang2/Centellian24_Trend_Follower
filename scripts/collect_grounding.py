"""Ulta Beauty / TikTok / Instagram collection via Gemini + Google Search grounding.

These three channels have no accessible scraping surface (§4.3-4.4 of the PRD),
so Gemini's Google Search grounding tool is the sole collection mechanism.
Every value returned here is an estimate, not a measurement — callers should
keep the "confidence" field attached through storage and display.
"""

import json
import logging
import os
import re

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MAX_ATTEMPTS = 2

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=api_key)


def _extract_grounding_sources(response) -> list[str]:
    """Pull real source URLs from the API's grounding metadata rather than
    trusting the model to self-report them in the JSON body — it's been
    observed to sometimes emit bare citation indices (e.g. "1", "3") instead
    of URLs there.
    """
    urls = []
    try:
        for candidate in response.candidates or []:
            metadata = getattr(candidate, "grounding_metadata", None)
            if not metadata:
                continue
            for chunk in getattr(metadata, "grounding_chunks", None) or []:
                web = getattr(chunk, "web", None)
                uri = getattr(web, "uri", None) if web else None
                if uri:
                    urls.append(uri)
    except Exception as exc:
        logger.warning("Failed to extract grounding metadata sources: %s", exc)

    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


def _call_grounded(prompt: str) -> tuple[str, list[str]]:
    client = _get_client()
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    )
    response = client.models.generate_content(model=MODEL, contents=prompt, config=config)
    return response.text, _extract_grounding_sources(response)


def _parse_json(text: str) -> dict:
    cleaned = _JSON_FENCE_RE.sub("", text.strip()).strip()
    return json.loads(cleaned)


def _query_grounded_json(prompt: str, default_fields: dict) -> dict:
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw_text, grounding_sources = _call_grounded(prompt)
        except Exception as exc:  # network errors, rate limits, auth errors, etc.
            last_error = exc
            logger.warning("Gemini grounding call failed (attempt %d/%d): %s", attempt, MAX_ATTEMPTS, exc)
            continue

        if not raw_text:
            # response.text can come back None/empty (e.g. safety-filtered or
            # grounding-only response with no text part) without raising.
            last_error = ValueError("empty response text")
            logger.warning("Gemini grounding response had no text (attempt %d/%d)", attempt, MAX_ATTEMPTS)
            continue

        try:
            parsed = _parse_json(raw_text)
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            logger.warning(
                "Gemini grounding response was not valid JSON (attempt %d/%d): %s",
                attempt, MAX_ATTEMPTS, exc,
            )
            continue

        if isinstance(parsed, list):
            # The prompt can reference multiple hashtags/items; the schema wants
            # one object, so keep the first (primary) entry and drop the rest.
            logger.warning("Gemini returned a JSON array instead of an object; using first item")
            parsed = parsed[0] if parsed else {}

        if not isinstance(parsed, dict):
            last_error = TypeError(f"Expected JSON object, got {type(parsed).__name__}")
            logger.warning(
                "Gemini grounding response was not a JSON object (attempt %d/%d): %s",
                attempt, MAX_ATTEMPTS, last_error,
            )
            continue

        if grounding_sources:
            parsed["sources"] = grounding_sources
        parsed["source"] = "gemini_grounding"
        parsed["confidence"] = "low"
        return parsed

    logger.warning("Giving up on grounding query after %d attempts: %s", MAX_ATTEMPTS, last_error)
    failed = dict(default_fields)
    failed["source"] = "gemini_grounding"
    failed["confidence"] = "failed"
    return failed


def get_ulta_data() -> dict:
    prompt = (
        "Ulta Beauty 웹사이트에서 Centellian24(센텔리안24) 제품의 현재 리뷰 수, 평균 별점, "
        "입점 SKU 수, 품절 여부를 조사해서 아래 JSON 스키마로만 답해줘 (다른 설명 없이 JSON만): "
        '{"review_count": <int>, "rating": <float>, "sku_count": <int>, '
        '"in_stock": <bool>, "sources": [<string>]}'
    )
    default_fields = {"review_count": None, "rating": None, "sku_count": None, "in_stock": None, "sources": []}
    return _query_grounded_json(prompt, default_fields)


def get_tiktok_data() -> dict:
    prompt = (
        "TikTok에서 #Centellian24, #MadecaCream 해시태그와 관련된 게시물을 조사해줘 "
        "(가능하면 최근 3개월 이내 게시물 위주로 확인해줘). "
        "해시태그 페이지의 정확한 게시물 수를 직접 확인할 수 없다면, 검색으로 찾을 수 있는 개별 영상의 조회수·좋아요 수, "
        "브랜드 공식 계정 게시물, 관련 기사·리뷰에서의 언급 등 간접적인 단서를 근거로 대략적인 범위라도 추정해줘 "
        "(정확하지 않아도 되니 수십/수백/수천 단위의 대략적인 규모로 추정치를 제시해줘). "
        "관련 검색 결과가 전혀 없어 추정할 근거조차 없는 경우에만 숫자 대신 null을 사용하고, "
        "0은 '게시물이 실제로 없다는 것이 확인된 경우'에만 사용해줘 (단순히 못 찾았다고 0을 쓰지 마). "
        "아래 JSON 스키마로만 답해줘 (다른 설명 없이 JSON만): "
        '{"hashtag": <string>, "post_count_est": <int|null>, "top_view_count_est": <int|null>, "sources": [<string>]}'
    )
    default_fields = {"hashtag": "#Centellian24", "post_count_est": None, "top_view_count_est": None, "sources": []}
    return _query_grounded_json(prompt, default_fields)


def get_instagram_data() -> dict:
    prompt = (
        "Instagram에서 #Centellian24 해시태그와 관련된 게시물을 조사해줘 "
        "(가능하면 최근 3개월 이내 게시물 위주로 확인해줘). "
        "해시태그 페이지의 정확한 게시물 수를 직접 확인할 수 없다면, 검색으로 찾을 수 있는 개별 게시물, "
        "브랜드 공식 계정 게시물, 관련 기사·리뷰에서의 언급 등 간접적인 단서를 근거로 대략적인 범위라도 추정해줘 "
        "(정확하지 않아도 되니 수십/수백/수천 단위의 대략적인 규모로 추정치를 제시해줘). "
        "관련 검색 결과가 전혀 없어 추정할 근거조차 없는 경우에만 숫자 대신 null을 사용하고, "
        "0은 '게시물이 실제로 없다는 것이 확인된 경우'에만 사용해줘 (단순히 못 찾았다고 0을 쓰지 마). "
        "아래 JSON 스키마로만 답해줘 (다른 설명 없이 JSON만): "
        '{"hashtag": <string>, "post_count_est": <int|null>, "sources": [<string>]}'
    )
    default_fields = {"hashtag": "#Centellian24", "post_count_est": None, "sources": []}
    return _query_grounded_json(prompt, default_fields)


if __name__ == "__main__":
    print("--- Ulta ---")
    print(json.dumps(get_ulta_data(), ensure_ascii=False, indent=2))
    print("--- TikTok ---")
    print(json.dumps(get_tiktok_data(), ensure_ascii=False, indent=2))
    print("--- Instagram ---")
    print(json.dumps(get_instagram_data(), ensure_ascii=False, indent=2))

"""Amazon review sentiment analysis via Gemini (PRD §4.6) — a derived metric,
not a new source: it re-processes review text already scraped by
collect_amazon.py. No Google Search grounding here, since this only reasons
over text already in hand (unlike collect_grounding.py's Ulta/TikTok/Instagram
calls, which must search the web).

Review text is passed in, scored, and discarded by the caller — only the
score/summary are persisted (PRD's copyright consideration: never store raw
review text in data/history.json).
"""

import json
import logging
import re

from scripts.collect_grounding import MODEL, _get_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2
LOW_CONFIDENCE_REVIEW_THRESHOLD = 5

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)

_PROMPT_TEMPLATE = (
    "아래는 아마존에서 수집한 Centellian24 제품 리뷰 텍스트 목록이야. 전반적인 소비자 호감도를 "
    "0~100 점수로 매기고, 그렇게 판단한 근거를 2~3문장으로 요약해줘. 극단적으로 긍정적이거나 "
    "부정적인 리뷰가 소수 있어도 전체 평균 흐름을 기준으로 판단해줘.\n\n"
    "아래 JSON 스키마로만 답해줘 (다른 설명 없이 JSON만): "
    '{{"sentiment_score": <int 0-100>, "sentiment_summary": <string>}}\n\n'
    "리뷰 목록:\n{reviews}"
)


def _build_prompt(review_texts: list[str]) -> str:
    numbered = "\n".join(f"{i+1}. {text}" for i, text in enumerate(review_texts))
    return _PROMPT_TEMPLATE.format(reviews=numbered)


def _parse_json(text: str) -> dict:
    cleaned = _JSON_FENCE_RE.sub("", text.strip()).strip()
    return json.loads(cleaned)


def analyze_amazon_sentiment(review_texts: list[str]) -> dict:
    confidence = "low" if len(review_texts) < LOW_CONFIDENCE_REVIEW_THRESHOLD else "normal"

    if not review_texts:
        return {"sentiment_score": None, "sentiment_summary": "", "confidence": "low"}

    prompt = _build_prompt(review_texts)
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            client = _get_client()
            response = client.models.generate_content(model=MODEL, contents=prompt)
        except Exception as exc:  # network errors, rate limits, auth errors, etc.
            last_error = exc
            logger.warning("Sentiment analysis call failed (attempt %d/%d): %s", attempt, MAX_ATTEMPTS, exc)
            continue

        if not response.text:
            last_error = ValueError("empty response text")
            logger.warning("Sentiment analysis response had no text (attempt %d/%d)", attempt, MAX_ATTEMPTS)
            continue

        try:
            parsed = _parse_json(response.text)
            score = int(parsed["sentiment_score"])
            summary = str(parsed["sentiment_summary"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            last_error = exc
            logger.warning(
                "Sentiment analysis response was not valid JSON (attempt %d/%d): %s",
                attempt, MAX_ATTEMPTS, exc,
            )
            continue

        return {"sentiment_score": score, "sentiment_summary": summary, "confidence": confidence}

    logger.warning("Giving up on sentiment analysis after %d attempts: %s", MAX_ATTEMPTS, last_error)
    return {"sentiment_score": None, "sentiment_summary": "", "confidence": "failed"}


if __name__ == "__main__":
    sample_reviews = [
        "보습력이 정말 좋아요, 아침저녁으로 쓰고 있습니다.",
        "향이 조금 강한 편이라 호불호가 갈릴 것 같아요.",
        "가격 대비 만족도가 높습니다. 재구매 의사 있어요.",
    ]
    print(json.dumps(analyze_amazon_sentiment(sample_reviews), ensure_ascii=False, indent=2))

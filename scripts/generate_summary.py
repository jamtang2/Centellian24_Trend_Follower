"""Gemini-based weekly qualitative summary of the collected snapshot data.

Unlike collect_grounding.py, this call does not use Google Search grounding —
it only summarizes data already collected this run (and last week's, for
comparison), so it's a plain text-generation call.
"""

import json
import logging
import os

from scripts.collect_grounding import MODEL, _get_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_BASE_INSTRUCTION = (
    "아래는 센텔리안24(동국제약)의 이번 주와 직전 주 미국/일본 시장 지표 데이터야. "
    "아마존 추정 판매량/BSR/리뷰, Google Trends(US/JP), Ulta/TikTok/Instagram 추정치 변화를 "
    "3~4문장으로 요약해줘. 수치가 추정치인 항목은 '추정'이라고 명시하고, 과장하지 말고 사실 기반으로 작성해줘."
)


def _strip_for_prompt(snapshot: dict) -> dict:
    return {k: v for k, v in snapshot.items() if k not in ("sources", "ai_summary")}


def _build_prompt(current: dict, previous: dict | None) -> str:
    current_json = json.dumps(_strip_for_prompt(current), ensure_ascii=False, indent=2)

    if previous is None:
        return (
            f"{_BASE_INSTRUCTION}\n\n"
            "단, 이번이 첫 실행이라 직전 주 데이터가 없어. 이번 주 데이터만 보고 현재 상태를 요약해줘 "
            "(전주 대비 변화는 언급하지 말고, 각 채널의 현재 수치와 신뢰도만 사실 기반으로 설명해줘).\n\n"
            f"이번 주 데이터:\n{current_json}"
        )

    previous_json = json.dumps(_strip_for_prompt(previous), ensure_ascii=False, indent=2)
    return (
        f"{_BASE_INSTRUCTION}\n\n"
        f"이번 주 데이터:\n{current_json}\n\n"
        f"직전 주 데이터:\n{previous_json}"
    )


def generate_weekly_summary(current: dict, previous: dict | None) -> str:
    prompt = _build_prompt(current, previous)
    try:
        client = _get_client()
        response = client.models.generate_content(model=MODEL, contents=prompt)
    except Exception as exc:  # network errors, rate limits, auth errors, etc.
        logger.warning("Weekly summary generation failed: %s", exc)
        return ""

    if not response.text:
        logger.warning("Gemini summary response had no text")
        return ""
    return response.text.strip()


if __name__ == "__main__":
    history_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "history.json"
    )
    history = []
    if os.path.exists(history_path):
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)

    if not history:
        print("data/history.json has no entries to summarize yet.")
    else:
        demo_current = history[-1]
        demo_previous = history[-2] if len(history) > 1 else None
        print(generate_weekly_summary(demo_current, demo_previous))

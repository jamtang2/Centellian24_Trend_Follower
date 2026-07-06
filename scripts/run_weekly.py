"""Weekly integration run: collect all channels, assemble the PRD snapshot schema,
write data/{week}.json, and append to data/history.json.

Each channel is collected independently — a hard failure in one (an unexpected
exception) must not prevent the others from being collected and saved.
"""

import datetime
import json
import logging
import os

from scripts.collect_amazon import collect_amazon_data
from scripts.collect_grounding import get_instagram_data, get_tiktok_data, get_ulta_data
from scripts.collect_trends import collect_trends_data
from scripts.generate_summary import generate_weekly_summary

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
DOCS_DATA_DIR = os.path.join(PROJECT_ROOT, "docs", "data")
DOCS_HISTORY_PATH = os.path.join(DOCS_DATA_DIR, "history.json")

_FAILED_GROUNDING = {"source": "gemini_grounding", "confidence": "failed"}


def _current_week_sunday() -> str:
    """Sunday-anchored week label for the run's execution date (today if run on Sunday)."""
    today = datetime.date.today()
    days_since_sunday = (today.weekday() - 6) % 7  # Monday=0 ... Sunday=6
    sunday = today - datetime.timedelta(days=days_since_sunday)
    return sunday.isoformat()


def _safe_collect(name: str, func, default):
    try:
        return func(), None
    except Exception as exc:  # a channel's collector must never take the whole run down
        logger.warning("%s collection raised an unexpected exception: %s", name, exc)
        return default, exc


def _amazon_has_data(data: list) -> bool:
    return any(item.get("asin") is not None for item in data)


def _trends_has_data(data: dict) -> bool:
    return any(v is not None for region in data.values() for v in region.values())


def _grounding_ok(data: dict) -> bool:
    return data.get("confidence") != "failed"


def _dedupe_sources(channels: dict) -> list:
    seen = set()
    ordered = []
    for key in ("ulta", "tiktok", "instagram"):
        for src in channels.get(key, {}).get("sources", []) or []:
            if src not in seen:
                seen.add(src)
                ordered.append(src)
    return ordered


def build_snapshot() -> tuple[dict, dict]:
    channels = {}
    ok_flags = {}

    channels["amazon"], amazon_exc = _safe_collect("amazon", collect_amazon_data, [])
    ok_flags["amazon"] = amazon_exc is None and _amazon_has_data(channels["amazon"])

    channels["google_trends"], trends_exc = _safe_collect(
        "google_trends", collect_trends_data, {"US": {}, "JP": {}}
    )
    ok_flags["google_trends"] = trends_exc is None and _trends_has_data(channels["google_trends"])

    channels["ulta"], ulta_exc = _safe_collect("ulta", get_ulta_data, dict(_FAILED_GROUNDING))
    ok_flags["ulta"] = ulta_exc is None and _grounding_ok(channels["ulta"])

    channels["tiktok"], tiktok_exc = _safe_collect("tiktok", get_tiktok_data, dict(_FAILED_GROUNDING))
    ok_flags["tiktok"] = tiktok_exc is None and _grounding_ok(channels["tiktok"])

    channels["instagram"], instagram_exc = _safe_collect(
        "instagram", get_instagram_data, dict(_FAILED_GROUNDING)
    )
    ok_flags["instagram"] = instagram_exc is None and _grounding_ok(channels["instagram"])

    snapshot = {
        "week": _current_week_sunday(),
        "amazon": channels["amazon"],
        "google_trends": channels["google_trends"],
        "ulta": channels["ulta"],
        "tiktok": channels["tiktok"],
        "instagram": channels["instagram"],
        "ai_summary": "",  # filled in by generate_summary.py in M5
        "sources": _dedupe_sources(channels),
    }
    return snapshot, ok_flags


def _load_history() -> list:
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read existing history.json, starting fresh: %s", exc)
        return []


def _write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_weekly() -> dict:
    snapshot, ok_flags = build_snapshot()
    week = snapshot["week"]

    history = _load_history()
    history = [entry for entry in history if entry.get("week") != week]  # replace same-week reruns, don't duplicate
    previous = history[-1] if history else None

    snapshot["ai_summary"] = generate_weekly_summary(snapshot, previous)
    ok_flags["ai_summary"] = bool(snapshot["ai_summary"])

    os.makedirs(DATA_DIR, exist_ok=True)
    _write_json(os.path.join(DATA_DIR, f"{week}.json"), snapshot)

    history.append(snapshot)
    _write_json(HISTORY_PATH, history)

    # Mirror history.json under docs/ so the GitHub Pages dashboard (served from
    # docs/) can fetch it with a plain relative path.
    os.makedirs(DOCS_DATA_DIR, exist_ok=True)
    _write_json(DOCS_HISTORY_PATH, history)

    succeeded = sum(1 for ok in ok_flags.values() if ok)
    total = len(ok_flags)
    logger.info("Weekly run for week=%s complete: %d/%d channels succeeded", week, succeeded, total)
    for name, ok in ok_flags.items():
        logger.info("  %-14s %s", name, "OK" if ok else "FAILED")

    return snapshot


if __name__ == "__main__":
    run_weekly()

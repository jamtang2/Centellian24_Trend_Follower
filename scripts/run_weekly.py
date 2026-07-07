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
from scripts.collect_qoo10 import collect_qoo10_data
from scripts.collect_trends import collect_trends_data
from scripts.generate_summary import generate_weekly_summary
from scripts.git_push import GitPushError, push_data_changes

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
DOCS_DATA_DIR = os.path.join(PROJECT_ROOT, "docs", "data")
DOCS_HISTORY_PATH = os.path.join(DOCS_DATA_DIR, "history.json")
RUN_LOG_PATH = os.path.join(DATA_DIR, "run_log.json")

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


def _finalize_channel(ok_flags: dict, name: str, data, exc, has_data) -> None:
    """Sets ok_flags[name] and, if the channel is marked FAILED, makes sure the
    log actually says why — a collector can fail "quietly" (no exception, but
    no usable data either, e.g. a blocked request that returns HTTP 200 with a
    block page) and _safe_collect alone has no way to explain that case.
    """
    ok = exc is None and has_data(data)
    ok_flags[name] = ok
    if exc is None and not ok:
        logger.warning(
            "%s collection completed without raising an exception but returned no usable data "
            "— see the warnings logged above from its own collector for the specific cause",
            name,
        )


def _amazon_has_data(data: list) -> bool:
    return any(item.get("asin") is not None for item in data)


def _qoo10_has_data(data: list) -> bool:
    return any(item.get("review_count") is not None or item.get("sales_badge") is not None for item in data)


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
    _finalize_channel(ok_flags, "amazon", channels["amazon"], amazon_exc, _amazon_has_data)

    channels["google_trends"], trends_exc = _safe_collect(
        "google_trends", collect_trends_data, {"US": {}, "JP": {}}
    )
    _finalize_channel(ok_flags, "google_trends", channels["google_trends"], trends_exc, _trends_has_data)

    channels["qoo10_jp"], qoo10_exc = _safe_collect("qoo10_jp", collect_qoo10_data, [])
    _finalize_channel(ok_flags, "qoo10_jp", channels["qoo10_jp"], qoo10_exc, _qoo10_has_data)

    channels["ulta"], ulta_exc = _safe_collect("ulta", get_ulta_data, dict(_FAILED_GROUNDING))
    _finalize_channel(ok_flags, "ulta", channels["ulta"], ulta_exc, _grounding_ok)

    channels["tiktok"], tiktok_exc = _safe_collect("tiktok", get_tiktok_data, dict(_FAILED_GROUNDING))
    _finalize_channel(ok_flags, "tiktok", channels["tiktok"], tiktok_exc, _grounding_ok)

    channels["instagram"], instagram_exc = _safe_collect(
        "instagram", get_instagram_data, dict(_FAILED_GROUNDING)
    )
    _finalize_channel(ok_flags, "instagram", channels["instagram"], instagram_exc, _grounding_ok)

    snapshot = {
        "week": _current_week_sunday(),
        "amazon": channels["amazon"],
        "google_trends": channels["google_trends"],
        "qoo10_jp": channels["qoo10_jp"],
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


def _append_run_log(entry: dict) -> None:
    """Record every run attempt (success or failure) so check_missed_run.py can
    tell whether this week's scheduled run actually happened — a local
    scheduler has no equivalent of GitHub Actions' run history UI.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    log = []
    if os.path.exists(RUN_LOG_PATH):
        try:
            with open(RUN_LOG_PATH, "r", encoding="utf-8") as f:
                log = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read existing run_log.json, starting fresh: %s", exc)
            log = []
    log.append(entry)
    _write_json(RUN_LOG_PATH, log)


def run_weekly() -> dict:
    week = _current_week_sunday()
    run_started_at = datetime.datetime.now().isoformat(timespec="seconds")
    ok_flags: dict = {}
    error_message = None

    try:
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

        try:
            push_data_changes()
            ok_flags["git_push"] = True
        except GitPushError as exc:
            logger.error("Git push failed — %s", exc)
            ok_flags["git_push"] = False

        succeeded = sum(1 for ok in ok_flags.values() if ok)
        total = len(ok_flags)
        logger.info("Weekly run for week=%s complete: %d/%d channels succeeded", week, succeeded, total)
        for name, ok in ok_flags.items():
            logger.info("  %-14s %s", name, "OK" if ok else "FAILED")

        return snapshot
    except Exception as exc:
        error_message = str(exc)
        logger.error("Weekly run for week=%s failed with an unexpected error: %s", week, exc)
        raise
    finally:
        _append_run_log(
            {
                "week": week,
                "run_started_at": run_started_at,
                "success": error_message is None,
                "channels": ok_flags,
                "error": error_message,
            }
        )


if __name__ == "__main__":
    run_weekly()

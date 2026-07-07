"""Detects a missed weekly run (PC was off/asleep through the scheduled window)
and surfaces it visibly, since a local Task Scheduler run has no equivalent of
GitHub Actions' run history UI to notice a silent gap in (PRD_rev.md 9장).

Kept dependency-light (stdlib + optional plyer) so it's cheap to run at every
login via Windows Startup, not just alongside the full weekly collection run.
"""

import datetime
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
RUN_LOG_PATH = os.path.join(DATA_DIR, "run_log.json")

MISSED_RUN_MESSAGE = "이번 주 실행이 누락된 것 같습니다. python -m scripts.run_weekly 를 수동으로 실행해주세요."


def _current_week_sunday() -> str:
    """Sunday-anchored week label for today — mirrors scripts.run_weekly's logic."""
    today = datetime.date.today()
    days_since_sunday = (today.weekday() - 6) % 7  # Monday=0 ... Sunday=6
    sunday = today - datetime.timedelta(days=days_since_sunday)
    return sunday.isoformat()


def _load_run_log() -> list:
    if not os.path.exists(RUN_LOG_PATH):
        return []
    try:
        with open(RUN_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read run_log.json: %s", exc)
        return []


def has_run_this_week() -> bool:
    this_week = _current_week_sunday()
    return any(entry.get("week") == this_week for entry in _load_run_log())


def _notify_desktop(message: str) -> None:
    try:
        from plyer import notification

        notification.notify(title="Centellian24 US Monitor", message=message, timeout=15)
    except Exception as exc:  # plyer not installed, or no notification backend on this OS
        logger.debug("Desktop notification unavailable (%s); console message only.", exc)


def check_missed_run() -> bool:
    """Returns True (and prints/notifies) if this week's run hasn't happened yet."""
    if has_run_this_week():
        logger.info("이번 주(%s) 실행 기록이 확인되었습니다.", _current_week_sunday())
        return False

    print(MISSED_RUN_MESSAGE)
    logger.warning(MISSED_RUN_MESSAGE)
    _notify_desktop(MISSED_RUN_MESSAGE)
    return True


if __name__ == "__main__":
    check_missed_run()

"""Commit and push data/docs changes produced by a local weekly run.

Replaces the GitHub Actions git-auto-commit step now that collection runs on
the user's local PC (see PRD/Centellian24_US_Monitor_PRD_rev.md §7). Failures
here (auth, conflicts, missing git) must be loud, not swallowed — the weekly
snapshot is already written to disk regardless, but a silent push failure
would leave the dashboard stale with no visible signal.
"""

import datetime
import logging
import os
import subprocess

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKED_PATHS = ["data", "docs"]


class GitPushError(Exception):
    """Raised when a git command needed to publish weekly data fails."""


def _run_git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except FileNotFoundError as exc:
        raise GitPushError("git executable not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else "(no stderr output)"
        raise GitPushError(f"`git {' '.join(args)}` failed: {stderr}") from exc


def _has_pending_changes() -> bool:
    status = _run_git("status", "--porcelain", "--", *TRACKED_PATHS)
    return bool(status.strip())


def push_data_changes() -> bool:
    """Commit and push changes under data/ and docs/, if any.

    Returns True if a commit was pushed, False if there was nothing to do.
    Raises GitPushError if a git command fails (auth error, conflict, etc.) —
    callers must not swallow this silently.
    """
    if not _has_pending_changes():
        logger.info("No changes under %s — skipping commit/push", TRACKED_PATHS)
        return False

    commit_message = f"Weekly update: {datetime.date.today().isoformat()}"
    _run_git("add", "--", *TRACKED_PATHS)
    _run_git("commit", "-m", commit_message)
    _run_git("push")
    logger.info("Pushed commit: %s", commit_message)
    return True


if __name__ == "__main__":
    try:
        push_data_changes()
    except GitPushError as exc:
        logger.error("Git push failed — %s", exc)
        raise SystemExit(1) from exc

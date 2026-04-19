"""
Post-commit hook: auto-infer a debug session when a fix commit touches
Claude-generated files, using file mtime to estimate duration.
"""

import os
import subprocess
import sys
from pathlib import Path

from .detector import is_claude_generated
from .tracker import get_active_session, stop_session, infer_session_from_commit


def main():
    # Get commit message
    try:
        commit_msg = subprocess.check_output(
            ["git", "log", "-1", "--format=%s"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return

    # Get files changed in latest commit
    try:
        changed = subprocess.check_output(
            ["git", "diff-tree", "--no-commit-id", "-r", "--name-only", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
        ).splitlines()
    except Exception:
        return

    claude_files = [f for f in changed if is_claude_generated(f)]
    if not claude_files:
        return

    # If there's an active manual session, auto-close it
    active = get_active_session()
    if active:
        result = stop_session(active["id"], status="resolved")
        from .tracker import duration_minutes
        dur = duration_minutes(result)
        print(
            f"\n[bugclock] Session #{active['id']} auto-closed "
            f"({dur} min) on commit '{commit_msg[:60]}'",
            file=sys.stderr,
        )
        return

    # No active session — try to auto-infer from file modification times
    duration_estimate = _estimate_duration(claude_files)
    session_id = infer_session_from_commit(claude_files, commit_msg, duration_estimate)
    if session_id:
        print(
            f"\n[bugclock] Auto-recorded debug session #{session_id} "
            f"(~{round(duration_estimate, 1)} min) for: {', '.join(claude_files[:3])}",
            file=sys.stderr,
        )


def _estimate_duration(files: list) -> float:
    """
    Estimate how long the developer was working on these files by looking at
    the gap between their last-committed mtime and now.
    Capped at 4 hours to avoid inflated estimates.
    """
    import time
    now = time.time()
    oldest_mtime = now

    for f in files:
        try:
            mtime = Path(f).stat().st_mtime
            if mtime < oldest_mtime:
                oldest_mtime = mtime
        except Exception:
            pass

    duration_seconds = min(now - oldest_mtime, 4 * 3600)
    return duration_seconds / 60


if __name__ == "__main__":
    main()

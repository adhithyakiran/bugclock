"""Core session lifecycle management."""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .storage import get_db, init_db

_ACTIVE_SESSION_FILE = Path(".claude-tracker/active_session")

# Git commit message keywords that suggest a debugging/fix commit
_FIX_KEYWORDS = [
    "fix", "bug", "debug", "patch", "resolve", "correct",
    "repair", "hotfix", "issue", "error", "broken", "crash",
]


def start_session(
    files: List[str] = None,
    notes: str = "",
    source: str = "manual",
) -> int:
    """Open a new debug session. Returns the session ID."""
    init_db()
    author = _git_author()
    now = datetime.utcnow().isoformat()

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO sessions (started_at, files, notes, author, source) VALUES (?,?,?,?,?)",
        (now, json.dumps(files or []), notes, author, source),
    )
    session_id = cur.lastrowid
    conn.commit()
    conn.close()

    _ACTIVE_SESSION_FILE.parent.mkdir(exist_ok=True)
    _ACTIVE_SESSION_FILE.write_text(str(session_id))
    return session_id


def stop_session(
    session_id: int,
    status: str = "resolved",
    notes: str = "",
) -> dict:
    """Close a session and return duration info."""
    conn = get_db()
    now = datetime.utcnow().isoformat()
    commit_hash = _current_commit()

    existing_notes = conn.execute(
        "SELECT notes FROM sessions WHERE id=?", (session_id,)
    ).fetchone()
    combined_notes = " | ".join(filter(None, [
        existing_notes["notes"] if existing_notes else "",
        notes,
    ]))

    conn.execute(
        "UPDATE sessions SET ended_at=?, status=?, commit_hash=?, notes=? WHERE id=?",
        (now, status, commit_hash, combined_notes, session_id),
    )
    conn.commit()

    row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    conn.close()

    if _ACTIVE_SESSION_FILE.exists():
        try:
            if _ACTIVE_SESSION_FILE.read_text().strip() == str(session_id):
                _ACTIVE_SESSION_FILE.unlink()
        except Exception:
            pass

    return _session_to_dict(row)


def get_active_session() -> Optional[dict]:
    """Return the currently active session, or None."""
    init_db()
    # Prefer state file for speed
    if _ACTIVE_SESSION_FILE.exists():
        try:
            sid = int(_ACTIVE_SESSION_FILE.read_text().strip())
            conn = get_db()
            row = conn.execute(
                "SELECT * FROM sessions WHERE id=? AND status='active'", (sid,)
            ).fetchone()
            conn.close()
            if row:
                return _session_to_dict(row)
        except Exception:
            pass

    # Fallback: query DB
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM sessions WHERE status='active' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return _session_to_dict(row) if row else None


def list_sessions(limit: int = 20, status: str = None) -> List[dict]:
    """Return recent sessions, newest first."""
    init_db()
    conn = get_db()
    if status:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE status=? ORDER BY started_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [_session_to_dict(r) for r in rows]


def infer_session_from_commit(
    files: List[str],
    commit_message: str,
    duration_minutes: float,
) -> Optional[int]:
    """
    Auto-create a completed debug session inferred from a git commit.
    Called by the post-commit hook when a fix-related commit touches
    Claude-generated files.
    """
    msg_lower = commit_message.lower()
    if not any(kw in msg_lower for kw in _FIX_KEYWORDS):
        return None

    init_db()
    author = _git_author()
    now = datetime.utcnow()
    started = now.replace(
        second=max(0, now.second - int(duration_minutes * 60))
    ).isoformat()

    conn = get_db()
    cur = conn.execute(
        """INSERT INTO sessions
           (started_at, ended_at, status, files, notes, commit_hash, author, source)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            started,
            now.isoformat(),
            "resolved",
            json.dumps(files),
            f"Auto-inferred from commit: {commit_message[:120]}",
            _current_commit(),
            author,
            "auto",
        ),
    )
    session_id = cur.lastrowid
    conn.commit()
    conn.close()
    return session_id


# ── Helpers ───────────────────────────────────────────────────────────────────

def duration_minutes(session: dict) -> Optional[float]:
    if not session.get("ended_at") or not session.get("started_at"):
        return None
    start = datetime.fromisoformat(session["started_at"])
    end = datetime.fromisoformat(session["ended_at"])
    return round((end - start).total_seconds() / 60, 1)


def _session_to_dict(row) -> dict:
    d = dict(row)
    d["files"] = json.loads(d.get("files") or "[]")
    return d


def _git_author() -> str:
    try:
        return subprocess.check_output(
            ["git", "config", "user.name"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return os.environ.get("USER", "unknown")


def _current_commit() -> Optional[str]:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None

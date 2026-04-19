"""SQLite-backed persistence for sessions, marked files, and config."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

_TRACKER_DIR = Path(".claude-tracker")
_DB_PATH = _TRACKER_DIR / "sessions.db"

# Committable team registry of claude-generated files
MARKED_FILES_PATH = _TRACKER_DIR / "marked_files.json"


def _ensure_dir():
    _TRACKER_DIR.mkdir(exist_ok=True)


def get_db() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at  TEXT    NOT NULL,
            ended_at    TEXT,
            status      TEXT    NOT NULL DEFAULT 'active',
            files       TEXT    NOT NULL DEFAULT '[]',
            notes       TEXT    DEFAULT '',
            commit_hash TEXT,
            author      TEXT,
            source      TEXT    NOT NULL DEFAULT 'manual'
        );

        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_status    ON sessions(status);
        CREATE INDEX IF NOT EXISTS idx_sessions_started   ON sessions(started_at);
    """)
    conn.commit()
    conn.close()


# ── Marked files registry (JSON, team-shareable) ─────────────────────────────

def load_marked_files() -> dict:
    if not MARKED_FILES_PATH.exists():
        return {}
    try:
        return json.loads(MARKED_FILES_PATH.read_text())
    except Exception:
        return {}


def save_marked_file(filepath: str, method: str = "manual"):
    registry = load_marked_files()
    registry[filepath] = {"marked_at": datetime.utcnow().isoformat(), "method": method}
    _ensure_dir()
    MARKED_FILES_PATH.write_text(json.dumps(registry, indent=2))


def is_manually_marked(filepath: str) -> bool:
    return filepath in load_marked_files()


# ── Config helpers ────────────────────────────────────────────────────────────

def get_config(key: str, default=None):
    conn = get_db()
    row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_config(key: str, value: str):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

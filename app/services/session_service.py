"""
Session metadata store for the sidebar chat history.

Uses the same memory.db file as the LangGraph SqliteSaver checkpointer, but
a separate 'sessions' table. The checkpointer owns full conversation state
(messages, tool calls, etc); this table only tracks thread_id -> title so
the sidebar can list conversations without loading full history for each.

A distinct sqlite3.Connection is used here rather than sharing the
checkpointer's connection — cleaner separation of concerns, and SQLite in
WAL mode (already enabled by SqliteSaver.setup()) supports multiple
concurrent connections to the same file safely.
"""

import sqlite3
from pathlib import Path
from typing import Optional
from app.utils.datetime_utils import now_beirut
from app.utils.logger import get_logger

logger = get_logger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "memory.db"

_conn: Optional[sqlite3.Connection] = None


def init_sessions_db() -> None:
    """Open the sessions connection and ensure the table exists. Call on startup."""
    global _conn
    _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            thread_id  TEXT PRIMARY KEY,
            title      TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    _conn.commit()
    logger.info("Sessions table ready")


def close_sessions_db() -> None:
    """Close the sessions connection. Call on shutdown."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None
        logger.info("Sessions DB connection closed")


def record_session_if_new(thread_id: str, first_message: str) -> None:
    """Insert a session row the first time a thread_id is seen.

    INSERT OR IGNORE makes this safe to call on every /chat request —
    subsequent calls for the same thread_id are no-ops, so the title stays
    fixed to whatever the user's first message was, matching standard
    chat-app UX (ChatGPT, Claude.ai) where the title never changes after
    the conversation starts.
    """
    title = first_message.strip()
    if len(title) > 60:
        title = title[:60].rstrip() + "…"

    _conn.execute(
        "INSERT OR IGNORE INTO sessions (thread_id, title, created_at) VALUES (?, ?, ?)",
        (thread_id, title, now_beirut().isoformat()),
    )
    _conn.commit()


def list_sessions() -> list[dict]:
    """Return all sessions, most recently created first."""
    rows = _conn.execute(
        "SELECT thread_id, title, created_at FROM sessions ORDER BY created_at DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def delete_session(thread_id: str) -> bool:
    """Remove a session's sidebar entry. Returns True if a row was deleted.
 
    Note: this only removes the sessions table row, hiding it from the
    sidebar. The underlying conversation state remains in the LangGraph
    checkpointer's own tables — harmless unused storage, no longer exposed
    anywhere once the session row is gone. A full purge of checkpoint data
    would require a separate call into the checkpointer itself, which is
    out of scope here.
    """
    cursor = _conn.execute("DELETE FROM sessions WHERE thread_id = ?", (thread_id,))
    _conn.commit()
    return cursor.rowcount > 0
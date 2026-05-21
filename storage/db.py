"""
F.R.I.D.A.Y. — SQLite storage layer
"""

import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS reminders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                text       TEXT    NOT NULL,
                due_time   TEXT,
                created_at TEXT    DEFAULT (datetime('now','localtime')),
                done       INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                text       TEXT    NOT NULL,
                priority   TEXT    DEFAULT 'normal',
                created_at TEXT    DEFAULT (datetime('now','localtime')),
                done       INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS notes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT,
                content    TEXT    NOT NULL,
                created_at TEXT    DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS memories (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                content    TEXT    NOT NULL,
                context    TEXT    DEFAULT '',
                created_at TEXT    DEFAULT (datetime('now','localtime'))
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                USING fts5(content, context, tokenize='porter ascii');

            CREATE TRIGGER IF NOT EXISTS memories_ai
                AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_fts(rowid, content, context)
                    VALUES (new.id, new.content, new.context);
                END;

            CREATE TRIGGER IF NOT EXISTS memories_ad
                AFTER DELETE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, context)
                    VALUES ('delete', old.id, old.content, old.context);
                END;

            CREATE TRIGGER IF NOT EXISTS memories_au
                AFTER UPDATE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, context)
                    VALUES ('delete', old.id, old.content, old.context);
                    INSERT INTO memories_fts(rowid, content, context)
                    VALUES (new.id, new.content, new.context);
                END;

            CREATE TABLE IF NOT EXISTS stock_watchlist (
                symbol     TEXT PRIMARY KEY,
                asset_type TEXT NOT NULL DEFAULT 'crypto',
                active     INTEGER DEFAULT 1,
                added_at   TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id         TEXT PRIMARY KEY,
                title      TEXT DEFAULT 'New Conversation',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                updated_at TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role            TEXT NOT NULL,
                content         TEXT NOT NULL,
                created_at      TEXT DEFAULT (datetime('now','localtime'))
            );
        """)
        conn.commit()


# ── Semantic memory helpers ───────────────────────────────────────────────────

def add_memory_to_fts(content: str, context: str = "") -> None:
    """
    No-op — FTS indexing is handled automatically by database triggers
    (memories_ai trigger fires on every INSERT into memories).
    This function exists for interface compatibility with services/memory.py.
    """
    pass  # trigger in init_db() handles this


def search_memory_fts(query: str, limit: int = 5) -> list[dict]:
    """
    Search the memories FTS5 index using porter-stemmed full-text search.
    Falls back to a LIKE scan if FTS fails (e.g. query has no indexable tokens).
    """
    with get_conn() as conn:
        # FTS5 full-text search — rowid maps 1:1 to memories.id
        try:
            fts_rows = conn.execute(
                "SELECT rowid FROM memories_fts WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?",
                (query, limit),
            ).fetchall()
            if fts_rows:
                ids = [r[0] for r in fts_rows]
                placeholders = ",".join("?" * len(ids))
                rows = conn.execute(
                    f"SELECT id, content, context, created_at FROM memories "
                    f"WHERE id IN ({placeholders})",
                    ids,
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            pass
        # LIKE fallback for short / symbol-only queries
        rows = conn.execute(
            "SELECT id, content, context, created_at FROM memories "
            "WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

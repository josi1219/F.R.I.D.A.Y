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
                context    TEXT,
                created_at TEXT    DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS stock_watchlist (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol     TEXT    NOT NULL UNIQUE,
                asset_type TEXT    NOT NULL DEFAULT 'crypto',
                added_at   TEXT    DEFAULT (datetime('now','localtime')),
                active     INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS conversation_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                logged_at  TEXT    DEFAULT (datetime('now','localtime'))
            );
        """)
        conn.commit()

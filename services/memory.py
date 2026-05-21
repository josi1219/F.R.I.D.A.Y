"""
F.R.I.D.A.Y. — Semantic Memory Service
Uses SQLite FTS5 (porter tokenizer) for fast, zero-API recall of stored facts.
No external embeddings required — fully offline, instant startup.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from storage.db import add_memory_to_fts, search_memory_fts, get_conn

logger = logging.getLogger(__name__)


def store_memory(content: str, context: str = "") -> int:
    """
    Save a fact to both the memories table and the FTS index.
    Returns the new memory ID.
    """
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO memories (content, context) VALUES (?, ?)",
            (content, context or ""),
        )
        mem_id = cur.lastrowid
        conn.commit()
    # Index in FTS (separate connection to avoid lock contention)
    try:
        add_memory_to_fts(content, context)
    except Exception as exc:
        logger.warning("FTS index failed for memory %d: %s", mem_id, exc)
    return mem_id


def recall_memories(query: str, limit: int = 5) -> list[dict]:
    """
    Search memories using FTS5 full-text search.
    Falls back to LIKE-based search if FTS fails.
    Returns list of dicts with keys: id, content, context, created_at.
    """
    return search_memory_fts(query, limit=limit)


def list_all_memories() -> list[dict]:
    """Return all stored memories, newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, content, context, created_at FROM memories ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_memory(mem_id: int) -> bool:
    """Remove a memory by ID. Returns True if deleted."""
    with get_conn() as conn:
        result = conn.execute("DELETE FROM memories WHERE id=?", (mem_id,))
        conn.commit()
    return result.rowcount > 0


def get_memories_for_prompt() -> str:
    """
    Return a formatted string of all memories for injection into the system prompt.
    Returns empty string if there are no memories.
    """
    memories = list_all_memories()
    if not memories:
        return ""
    lines = ["[Persistent memory — facts about the user:]"]
    for m in memories:
        ctx = f" [{m['context']}]" if m.get("context") else ""
        lines.append(f"  #{m['id']}: {m['content']}{ctx}")
    return "\n".join(lines)

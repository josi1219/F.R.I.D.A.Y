"""
Task Checkpoint System — Persistent state management for long-running workflows.

Enables resumable multi-stage processing with:
- Durable execution state tracking
- Chunk-based progress tracking
- Incremental report generation
- Automatic recovery from API key rotation
- State continuity across model instances
"""

import json
import logging
import hashlib
from datetime import datetime
from typing import Any, Optional
from contextlib import contextmanager

from storage.db import get_conn

logger = logging.getLogger(__name__)


class TaskCheckpoint:
    """
    Manages persistent task state for long-running workflows.
    
    Enables:
    - Breaking large tasks into resumable chunks
    - Tracking progress across API key rotations
    - Preserving reasoning state and intermediate outputs
    - Incremental report generation
    - Automatic recovery and retry
    """

    def __init__(self, task_id: str, task_type: str):
        """
        Initialize or load a task checkpoint.
        
        Args:
            task_id: Unique identifier for the task (e.g., 'research_20260522_xyz')
            task_type: Type of task ('document_analysis', 'research', 'report_gen', etc.)
        """
        self.task_id = task_id
        self.task_type = task_type
        self.checkpoint_id = self._load_or_create()
        
    def _load_or_create(self) -> int:
        """Load existing checkpoint or create new one."""
        with get_conn() as conn:
            # Check if checkpoint exists
            row = conn.execute(
                "SELECT id FROM task_checkpoints WHERE task_id = ?",
                (self.task_id,)
            ).fetchone()
            
            if row:
                logger.info(f"Loaded existing checkpoint for task {self.task_id}")
                return row['id']
            
            # Create new checkpoint
            conn.execute(
                """
                INSERT INTO task_checkpoints (task_id, task_type, status)
                VALUES (?, ?, 'pending')
                """,
                (self.task_id, self.task_type)
            )
            conn.commit()
            
            new_row = conn.execute(
                "SELECT id FROM task_checkpoints WHERE task_id = ?",
                (self.task_id,)
            ).fetchone()
            
            logger.info(f"Created new checkpoint for task {self.task_id}")
            return new_row['id']
    
    def save_checkpoint_state(self, stage: str, progress: float, state_data: dict) -> None:
        """
        Save execution state at a checkpoint stage.
        
        Args:
            stage: Current processing stage (e.g., 'chunk_1_parsed', 'summary_generated')
            progress: Progress percentage (0-100)
            state_data: Dict containing execution state to persist
        """
        with get_conn() as conn:
            state_json = json.dumps(state_data, default=str)
            
            # Update or insert checkpoint state
            existing = conn.execute(
                "SELECT id FROM checkpoint_state WHERE checkpoint_id = ? AND stage = ?",
                (self.checkpoint_id, stage)
            ).fetchone()
            
            if existing:
                conn.execute(
                    """
                    UPDATE checkpoint_state 
                    SET progress = ?, state_data = ?, created_at = datetime('now','localtime')
                    WHERE checkpoint_id = ? AND stage = ?
                    """,
                    (progress, state_json, self.checkpoint_id, stage)
                )
            else:
                conn.execute(
                    """
                    INSERT INTO checkpoint_state (checkpoint_id, stage, progress, state_data)
                    VALUES (?, ?, ?, ?)
                    """,
                    (self.checkpoint_id, stage, progress, state_json)
                )
            
            conn.execute(
                "UPDATE task_checkpoints SET updated_at = datetime('now','localtime') WHERE id = ?",
                (self.checkpoint_id,)
            )
            conn.commit()
            
            logger.info(f"Saved checkpoint state: {stage} ({progress}%)")
    
    def load_checkpoint_state(self, stage: str) -> Optional[dict]:
        """Load previously saved checkpoint state."""
        with get_conn() as conn:
            row = conn.execute(
                "SELECT state_data FROM checkpoint_state WHERE checkpoint_id = ? AND stage = ?",
                (self.checkpoint_id, stage)
            ).fetchone()
            
            if row:
                return json.loads(row['state_data'])
            return None
    
    def add_processed_chunk(self, chunk_id: str, chunk_order: int, 
                           summary: str, extracted_data: dict, content_hash: str = "") -> None:
        """
        Record a processed chunk with its summary and extracted data.
        
        Args:
            chunk_id: Unique identifier for the chunk
            chunk_order: Sequence order of chunk
            summary: Extracted summary from chunk
            extracted_data: Structured data extracted from chunk
            content_hash: Hash of chunk content for validation
        """
        with get_conn() as conn:
            extracted_json = json.dumps(extracted_data, default=str)
            
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_chunks 
                (checkpoint_id, chunk_id, chunk_order, content_hash, summary, extracted_data, status)
                VALUES (?, ?, ?, ?, ?, ?, 'completed')
                """,
                (self.checkpoint_id, chunk_id, chunk_order, content_hash, summary, extracted_json)
            )
            conn.commit()
            logger.info(f"Recorded processed chunk: {chunk_id}")
    
    def get_processed_chunks(self) -> list[dict]:
        """Get all processed chunks in order."""
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT chunk_id, chunk_order, summary, extracted_data, status, processed_at
                FROM processed_chunks
                WHERE checkpoint_id = ?
                ORDER BY chunk_order ASC
                """,
                (self.checkpoint_id,)
            ).fetchall()
            
            chunks = []
            for row in rows:
                chunks.append({
                    'chunk_id': row['chunk_id'],
                    'order': row['chunk_order'],
                    'summary': row['summary'],
                    'extracted_data': json.loads(row['extracted_data']) if row['extracted_data'] else {},
                    'status': row['status'],
                    'processed_at': row['processed_at']
                })
            return chunks
    
    def add_report_section(self, section_id: str, section_title: str, 
                          markdown_content: str, chunk_ids: list[str], 
                          citations: list[str] = None) -> None:
        """
        Add or update a completed report section.
        
        Args:
            section_id: Unique identifier for section
            section_title: Title of the section
            markdown_content: Markdown-formatted content
            chunk_ids: List of chunk IDs that contributed to this section
            citations: List of citation references
        """
        with get_conn() as conn:
            chunk_ids_json = json.dumps(chunk_ids)
            citations_json = json.dumps(citations or [])
            
            conn.execute(
                """
                INSERT OR REPLACE INTO report_sections 
                (checkpoint_id, section_id, section_title, markdown_content, chunk_ids, citations, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now','localtime'))
                """,
                (self.checkpoint_id, section_id, section_title, markdown_content, 
                 chunk_ids_json, citations_json)
            )
            conn.commit()
            logger.info(f"Saved report section: {section_id}")
    
    def get_report_sections(self) -> list[dict]:
        """Get all completed report sections."""
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT section_id, section_title, markdown_content, chunk_ids, citations
                FROM report_sections
                WHERE checkpoint_id = ?
                ORDER BY CAST(SUBSTR(section_id, 8) AS INTEGER) ASC
                """,
                (self.checkpoint_id,)
            ).fetchall()
            
            sections = []
            for row in rows:
                sections.append({
                    'id': row['section_id'],
                    'title': row['section_title'],
                    'content': row['markdown_content'],
                    'chunk_ids': json.loads(row['chunk_ids']),
                    'citations': json.loads(row['citations'] or '[]')
                })
            return sections
    
    def get_final_report(self) -> str:
        """
        Assemble final markdown report from all sections.
        """
        sections = self.get_report_sections()
        
        parts = [
            f"# {self.task_id} Report",
            f"*Generated: {datetime.now().isoformat()}*",
            ""
        ]
        
        for section in sections:
            parts.append(f"## {section['title']}")
            parts.append(section['content'])
            
            if section['citations']:
                parts.append("\n### References")
                for i, cite in enumerate(section['citations'], 1):
                    parts.append(f"[{i}] {cite}")
            parts.append("")
        
        return "\n".join(parts)
    
    def set_metadata(self, key: str, value: Any) -> None:
        """Store task metadata."""
        with get_conn() as conn:
            value_str = json.dumps(value) if not isinstance(value, str) else value
            
            conn.execute(
                """
                INSERT OR REPLACE INTO task_metadata (checkpoint_id, key, value)
                VALUES (?, ?, ?)
                """,
                (self.checkpoint_id, key, value_str)
            )
            conn.commit()
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Retrieve task metadata."""
        with get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM task_metadata WHERE checkpoint_id = ? AND key = ?",
                (self.checkpoint_id, key)
            ).fetchone()
            
            if row:
                try:
                    return json.loads(row['value'])
                except:
                    return row['value']
            return default
    
    def mark_stage_complete(self, stage: str) -> None:
        """Mark a processing stage as complete."""
        self.set_metadata(f"stage_complete_{stage}", datetime.now().isoformat())
        logger.info(f"Marked stage complete: {stage}")
    
    def is_stage_complete(self, stage: str) -> bool:
        """Check if a stage was previously completed."""
        return self.get_metadata(f"stage_complete_{stage}") is not None
    
    def update_status(self, status: str) -> None:
        """Update task status."""
        with get_conn() as conn:
            conn.execute(
                "UPDATE task_checkpoints SET status = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                (status, self.checkpoint_id)
            )
            
            if status == 'completed':
                conn.execute(
                    "UPDATE task_checkpoints SET completed_at = datetime('now','localtime') WHERE id = ?",
                    (self.checkpoint_id,)
                )
            
            conn.commit()
            logger.info(f"Task {self.task_id} status: {status}")
    
    def get_progress_summary(self) -> dict:
        """Get overall progress summary."""
        with get_conn() as conn:
            checkpoint = conn.execute(
                "SELECT status, created_at, updated_at, completed_at FROM task_checkpoints WHERE id = ?",
                (self.checkpoint_id,)
            ).fetchone()
            
            chunks = conn.execute(
                "SELECT COUNT(*) as total FROM processed_chunks WHERE checkpoint_id = ?",
                (self.checkpoint_id,)
            ).fetchone()
            
            sections = conn.execute(
                "SELECT COUNT(*) as total FROM report_sections WHERE checkpoint_id = ?",
                (self.checkpoint_id,)
            ).fetchone()
            
            states = conn.execute(
                "SELECT MAX(progress) as max_progress FROM checkpoint_state WHERE checkpoint_id = ?",
                (self.checkpoint_id,)
            ).fetchone()
            
            return {
                'task_id': self.task_id,
                'status': checkpoint['status'],
                'progress': states['max_progress'] or 0,
                'chunks_processed': chunks['total'] or 0,
                'report_sections': sections['total'] or 0,
                'created_at': checkpoint['created_at'],
                'updated_at': checkpoint['updated_at'],
                'completed_at': checkpoint['completed_at']
            }


@contextmanager
def checkpoint_context(task_id: str, task_type: str):
    """
    Context manager for task checkpoint operations.
    
    Usage:
        with checkpoint_context('analysis_001', 'document_analysis') as cp:
            cp.save_checkpoint_state('parsing', 10, {'parsed_pages': 10})
            # ... do work ...
            cp.save_checkpoint_state('parsing', 100, {'parsed_pages': 100})
    """
    cp = TaskCheckpoint(task_id, task_type)
    try:
        yield cp
    except Exception as exc:
        cp.update_status('failed')
        logger.error(f"Task {task_id} failed: {exc}")
        raise

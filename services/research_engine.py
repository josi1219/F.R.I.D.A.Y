"""
Research Engine — Long-running document analysis and research workflows.

Orchestrates:
- Multi-stage document processing
- Chunk-based analysis with resumability
- Continuation across API key rotations
- Incremental report generation
- Intelligent summarization and synthesis
"""

import logging
import json
import hashlib
from typing import Generator, Optional, Any
from datetime import datetime
from pathlib import Path

from storage.task_checkpoint import TaskCheckpoint, checkpoint_context
from services.ai import FridayAI

logger = logging.getLogger(__name__)


class DocumentChunk:
    """Represents a chunk of a document for processing."""
    
    def __init__(self, chunk_id: str, order: int, content: str, metadata: dict = None):
        self.chunk_id = chunk_id
        self.order = order
        self.content = content
        self.metadata = metadata or {}
        self.content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict:
        return {
            'id': self.chunk_id,
            'order': self.order,
            'content': self.content,
            'hash': self.content_hash,
            'metadata': self.metadata
        }


class ResearchEngine:
    """
    Long-running research orchestration with persistent state.
    
    Supports:
    - Large document analysis (1000+ pages)
    - Multi-stage processing pipelines
    - Resumable workflows across API key rotations
    - Incremental report generation
    - Deep research task orchestration
    """
    
    def __init__(self, ai_service: FridayAI):
        """Initialize research engine with AI service."""
        self.ai = ai_service
        self.current_checkpoint: Optional[TaskCheckpoint] = None
    
    def chunk_document(self, content: str, chunk_size: int = 4000, 
                      overlap: int = 200) -> list[DocumentChunk]:
        """
        Split document into overlapping chunks for processing.
        
        Args:
            content: Full document content
            chunk_size: Approximate characters per chunk
            overlap: Characters to overlap between chunks
        
        Returns:
            List of DocumentChunk objects
        """
        chunks = []
        start = 0
        chunk_order = 0
        
        while start < len(content):
            end = min(start + chunk_size, len(content))
            
            # Try to break at paragraph boundary
            if end < len(content):
                last_newline = content.rfind('\n\n', start, end)
                if last_newline > start + chunk_size * 0.5:  # reasonable break point
                    end = last_newline
            
            chunk_content = content[start:end].strip()
            if chunk_content:
                chunk_id = f"chunk_{chunk_order:04d}"
                chunks.append(DocumentChunk(chunk_id, chunk_order, chunk_content))
                chunk_order += 1
            
            # Move to next chunk with overlap
            start = max(start + chunk_size - overlap, end)
        
        logger.info(f"Split document into {len(chunks)} chunks")
        return chunks
    
    def analyze_document(self, task_id: str, file_path: str, 
                        analysis_prompt: str = None) -> Generator[str, None, None]:
        """
        Analyze a large document with persistent checkpoint state.
        
        Workflow:
        1. Load document and chunk it
        2. Process each chunk with AI (summarize, extract key info)
        3. Save summaries to checkpoint
        4. Generate progressive sections of final report
        5. Continue automatically if API key rotates
        
        Args:
            task_id: Unique task identifier
            file_path: Path to document file
            analysis_prompt: Custom analysis instructions
        
        Yields:
            Progress messages and final report sections
        """
        try:
            # Initialize checkpoint
            with checkpoint_context(task_id, 'document_analysis') as cp:
                self.current_checkpoint = cp
                
                # Check if already loading document
                if cp.is_stage_complete('load_document'):
                    yield "📖 Resuming document analysis from checkpoint..."
                    document_content = cp.get_metadata('document_content')
                    chunks = [DocumentChunk(c['id'], c['order'], c['content'], c['metadata']) 
                             for c in cp.get_metadata('chunks', [])]
                else:
                    # Load document
                    yield "📂 Loading document..."
                    file_path = Path(file_path)
                    if not file_path.exists():
                        yield f"❌ File not found: {file_path}"
                        return
                    
                    try:
                        if file_path.suffix.lower() == '.pdf':
                            document_content = self._extract_pdf_text(file_path)
                        else:
                            document_content = file_path.read_text(encoding='utf-8', errors='ignore')
                    except Exception as e:
                        yield f"❌ Failed to load document: {e}"
                        return
                    
                    yield f"✓ Document loaded ({len(document_content)} characters)"
                    
                    # Chunk document
                    yield "✂️ Chunking document..."
                    chunks = self.chunk_document(document_content)
                    yield f"✓ Split into {len(chunks)} chunks"
                    
                    # Save to checkpoint
                    cp.set_metadata('document_content', document_content[:500])  # preview
                    cp.set_metadata('chunks', [c.to_dict() for c in chunks])
                    cp.set_metadata('total_chunks', len(chunks))
                    cp.mark_stage_complete('load_document')
                
                # Process chunks
                yield "🔄 Processing chunks..."
                cp.update_status('processing')
                
                processed_chunks = cp.get_processed_chunks()
                processed_ids = {c['chunk_id'] for c in processed_chunks}
                
                for i, chunk in enumerate(chunks):
                    if chunk.chunk_id in processed_ids:
                        yield f"⊙ Chunk {i+1}/{len(chunks)} (already processed)"
                        continue
                    
                    yield f"⟳ Processing chunk {i+1}/{len(chunks)}..."
                    
                    # Analyze chunk
                    analysis_request = analysis_prompt or (
                        f"Summarize the key points, topics, and important information from this section. "
                        f"Extract any structured data (dates, names, metrics, etc.) in JSON format."
                    )
                    
                    prompt = f"{analysis_request}\n\n--- SECTION START ---\n{chunk.content}\n--- SECTION END ---"
                    
                    try:
                        # Use streaming to get response
                        response_text = ""
                        for token in self.ai._gemini_chat_stream(prompt):
                            response_text += token
                        
                        # Parse response (try to extract JSON structured data)
                        extracted_data = {}
                        try:
                            # Look for JSON block in response
                            if '{' in response_text and '}' in response_text:
                                json_start = response_text.rfind('{')
                                json_end = response_text.rfind('}') + 1
                                json_str = response_text[json_start:json_end]
                                extracted_data = json.loads(json_str)
                        except:
                            pass
                        
                        # Save processed chunk
                        cp.add_processed_chunk(
                            chunk.chunk_id,
                            chunk.order,
                            summary=response_text[:500],  # first 500 chars as summary
                            extracted_data=extracted_data,
                            content_hash=chunk.content_hash
                        )
                        
                        # Progress checkpoint
                        progress = ((i + 1) / len(chunks)) * 50  # first 50% is processing
                        cp.save_checkpoint_state('chunk_processing', progress, {
                            'processed': i + 1,
                            'total': len(chunks),
                            'last_chunk_id': chunk.chunk_id
                        })
                        
                        yield f"✓ Chunk {i+1}/{len(chunks)} analyzed"
                        
                    except Exception as e:
                        logger.error(f"Failed to process chunk {chunk.chunk_id}: {e}")
                        yield f"⚠ Chunk {i+1} failed: {e} (will retry on resume)"
                        continue
                
                yield "✓ All chunks processed"
                cp.mark_stage_complete('chunk_processing')
                
                # Generate report sections
                yield "📝 Generating report sections..."
                cp.update_status('generating_report')
                
                processed = cp.get_processed_chunks()
                
                # Section 1: Executive Summary
                if not cp.is_stage_complete('report_section_summary'):
                    yield "→ Generating executive summary..."
                    summaries = [c['summary'] for c in processed[:5]]  # first 5 chunks
                    synthesis_prompt = (
                        f"Create a concise executive summary of this document based on these section summaries. "
                        f"Be specific and highlight key insights:\n\n" + "\n\n".join(summaries)
                    )
                    
                    summary_response = ""
                    for token in self.ai._gemini_chat_stream(synthesis_prompt):
                        summary_response += token
                    
                    cp.add_report_section(
                        'section_001',
                        'Executive Summary',
                        summary_response,
                        [c['chunk_id'] for c in processed[:5]]
                    )
                    cp.mark_stage_complete('report_section_summary')
                    yield "✓ Executive summary complete"
                
                # Section 2: Key Findings
                if not cp.is_stage_complete('report_section_findings'):
                    yield "→ Extracting key findings..."
                    findings_prompt = (
                        f"Based on all the analyzed sections, list the 5-10 most important findings, "
                        f"insights, and conclusions. Format as markdown with clear headings."
                    )
                    
                    findings_response = ""
                    for token in self.ai._gemini_chat_stream(findings_prompt):
                        findings_response += token
                    
                    cp.add_report_section(
                        'section_002',
                        'Key Findings',
                        findings_response,
                        [c['chunk_id'] for c in processed]
                    )
                    cp.mark_stage_complete('report_section_findings')
                    yield "✓ Key findings extracted"
                
                # Generate final report
                yield "📄 Assembling final report..."
                final_report = cp.get_final_report()
                cp.update_status('completed')
                
                yield "---REPORT_START---"
                yield final_report
                yield "---REPORT_END---"
                
                yield f"\n✓ Analysis complete! Report saved to checkpoint {task_id}"
                
                # Progress summary
                summary = cp.get_progress_summary()
                yield f"\n📊 Summary: {summary['chunks_processed']} chunks, "
                yield f"{summary['report_sections']} sections, Status: {summary['status']}"
        
        except Exception as e:
            logger.error(f"Research engine error: {e}")
            if self.current_checkpoint:
                self.current_checkpoint.update_status('failed')
            yield f"❌ Error: {e}"
    
    def _extract_pdf_text(self, file_path: Path) -> str:
        """Extract text from PDF file."""
        try:
            import PyPDF2
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
                return text
        except ImportError:
            logger.error("PyPDF2 not installed. Install with: pip install PyPDF2")
            raise ImportError("PDF support requires PyPDF2")
    
    def get_task_progress(self, task_id: str) -> dict:
        """Get progress of a task."""
        cp = TaskCheckpoint(task_id, 'document_analysis')
        return cp.get_progress_summary()
    
    def list_tasks(self) -> list[dict]:
        """List all active and completed analysis tasks."""
        from storage.db import get_conn
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, task_id, task_type, status, created_at, updated_at
                FROM task_checkpoints
                ORDER BY updated_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

# Persistent Task State Architecture

## Overview

Friday now implements a **checkpoint-based continuation system** for long-running research and document analysis tasks. This architecture enables:

- **State Continuity** — Execution state persists across API key rotations
- **Chunk-Based Processing** — Large documents split into manageable chunks
- **Incremental Reports** — Reports generated progressively, not all at once
- **Automatic Recovery** — Tasks resume from exact checkpoint on key exhaustion
- **Distributed Workflows** — Foundation for multi-agent research orchestration

## Problem Solved

**Before:** When a Gemini API key hit its quota during a 2000-page analysis:
- Task would restart from the beginning with new key
- All progress lost (summaries, extracted data, reasoning)
- Duplicate processing of already-analyzed sections
- Massive token waste and latency

**After:** Checkpoint system automatically:
- Saves state before key rotation
- Resumes from exact position with new key
- Reuses chunk summaries and extracted data
- Continues report generation seamlessly

## Architecture

### Core Components

#### 1. **Task Checkpoint** (`storage/task_checkpoint.py`)
Manages persistent execution state with database backing.

**Key Methods:**
```python
TaskCheckpoint(task_id, task_type)  # Load or create checkpoint

# Save processing state
cp.save_checkpoint_state(stage, progress, state_data)

# Track processed chunks
cp.add_processed_chunk(chunk_id, order, summary, extracted_data)

# Build report incrementally
cp.add_report_section(section_id, title, markdown, chunk_ids)

# Retrieve saved state
cp.load_checkpoint_state(stage)
cp.get_processed_chunks()
cp.get_report_sections()
cp.get_final_report()
```

**State Tracking:**
- `checkpoint_state` — Current processing stage and progress (0-100%)
- `processed_chunks` — Summary + extracted data for each chunk
- `report_sections` — Markdown sections of final report
- `task_metadata` — Custom key-value metadata

#### 2. **Research Engine** (`services/research_engine.py`)
Orchestrates long-running research workflows with automatic checkpoint management.

**Workflow:**
```
1. Load document → chunk it intelligently
2. For each chunk:
   - Stream analysis from AI
   - Extract summaries and structured data
   - Save to checkpoint immediately
3. Generate report sections progressively
4. Assemble final markdown report
```

**Key Methods:**
```python
engine = ResearchEngine(ai_service)

# Main workflow - returns generator of progress messages
for message in engine.analyze_document(task_id, file_path, analysis_prompt):
    print(message)  # "✓ Chunk 5/100 analyzed", "→ Generating summary..."

# Check progress
progress = engine.get_task_progress(task_id)

# List all tasks
tasks = engine.list_tasks()
```

#### 3. **Database Schema** (`storage/db.py`)
Extended with checkpoint tables:

```sql
-- Task metadata
task_checkpoints (id, task_id, task_type, status, timestamps)

-- Execution state at each stage
checkpoint_state (checkpoint_id, stage, progress, state_data)

-- Processed chunks with summaries
processed_chunks (checkpoint_id, chunk_id, summary, extracted_data)

-- Generated report sections
report_sections (checkpoint_id, section_id, title, markdown_content)

-- Custom metadata
task_metadata (checkpoint_id, key, value)
```

#### 4. **AI Service Integration** (`services/ai.py`)
Automatically saves state before API key rotation.

```python
# Before key rotation, calls:
ai._checkpoint_state_before_rotation()

# Saves execution context to allow seamless resume with new key
```

## Usage Examples

### Starting Document Analysis

```python
# Flask endpoint
POST /api/research/analyze
{
    "task_id": "analysis_budget_2026",
    "file_path": "/path/to/budget_2000pages.pdf",
    "analysis_prompt": "Extract financial data and trends"
}

# Returns: Server-Sent Events stream with progress
# Response format:
data: {"message": "📖 Loading document..."}
data: {"message": "✓ Split into 50 chunks"}
data: {"message": "⟳ Processing chunk 1/50..."}
...
data: {"message": "---REPORT_START---"}
data: {"message": "# analysis_budget_2026 Report\n## Executive Summary..."}
data: {"message": "---REPORT_END---"}
```

### Resuming Interrupted Task

If API key rotates during chunk processing:

```python
# New key automatically selected
# New model instance created
# Old checkpoint loaded with:
#   - Completed chunk summaries
#   - Extracted data from processed chunks
#   - Report sections generated so far
# Task resumes from next unprocessed chunk

# No manual intervention needed!
```

### Checking Task Progress

```python
# Flask endpoint
GET /api/research/status/analysis_budget_2026

# Response:
{
    "task_id": "analysis_budget_2026",
    "status": "processing",
    "progress": 65.0,
    "chunks_processed": 33,
    "report_sections": 2,
    "created_at": "2026-05-22T15:30:00",
    "updated_at": "2026-05-22T15:45:23"
}
```

### Getting Final Report

```python
# Flask endpoint
GET /api/research/report/analysis_budget_2026

# Response:
{
    "task_id": "analysis_budget_2026",
    "report": "# analysis_budget_2026 Report\n## Executive Summary\n..."
}
```

## Chunk Processing Workflow

### Intelligent Chunking

```python
# Document split respecting paragraph boundaries
chunks = engine.chunk_document(content, chunk_size=4000, overlap=200)

# Results:
# chunk_0000: "Introduction paragraph..."
# chunk_0001: "Historical context..."
# chunk_0002: "Recent trends..."
# ... (overlapping to preserve context)
```

### Chunk Analysis

For each chunk:
1. Stream AI analysis: "Summarize key points and extract structured data"
2. Capture response and parse for JSON structured data
3. Save immediately:
   ```python
   cp.add_processed_chunk(
       chunk_id="chunk_0005",
       chunk_order=5,
       summary="Budget increased 15% in category X...",
       extracted_data={
           "category": "X",
           "increase_pct": 15,
           "amounts": [1000, 2000, 3000]
       }
   )
   ```

### Checkpoint Validation

Each chunk includes:
- `content_hash` — SHA256 hash for validation
- `processed_at` — Timestamp of processing
- `status` — 'completed', 'failed', 'pending'

On resume, hashes are verified to ensure no corruption.

## State Recovery on Key Rotation

```python
# When API quota hit:
1. Current AI detects quota error
2. Calls _checkpoint_state_before_rotation()
3. Saves current chat history and stage
4. Rotates to next API key
5. Creates new model instance with same system prompt
6. Loads previous checkpoint state
7. Resumes from exact position

# Result: User sees no interruption, task continues smoothly
```

## Report Generation Strategy

### Incremental Approach

Instead of waiting for all chunks to generate one big report:

1. **Stage 1: Chunk Analysis** (50% of effort)
   - Process chunks, extract summaries
   - Save progress frequently

2. **Stage 2: Executive Summary** (15% of effort)
   - Synthesize first N chunk summaries
   - Generate concise overview

3. **Stage 3: Key Findings** (20% of effort)
   - Extract top insights across all chunks
   - Create findings section

4. **Stage 4: Synthesis** (15% of effort)
   - Merge chunk data into coherent narrative
   - Assemble final markdown

**Benefit:** Reports become available progressively; user can read summary while analysis completes.

## Failure Recovery

### Retry Logic

```python
# Failed chunks marked with status='failed'
# Can be manually retried:

# Find failed chunks
failed = cp.get_processed_chunks()  # filters by status
failed_chunks = [c for c in failed if c['status'] == 'failed']

# Retry with same or different key
for chunk in failed_chunks:
    # Re-analyze chunk
    result = ai.chat(f"Re-analyze: {chunk['content']}")
    cp.add_processed_chunk(...)  # updates with success
```

### Task Status States

```
pending      → Just created
processing   → Actively analyzing chunks
generating_report → Building final sections
completed    → Done, report ready
failed       → Hit unrecoverable error
```

## Performance Characteristics

### Token Usage

**Large Document (1000 pages = ~400 chunks):**

| Stage | Tokens | Notes |
|-------|--------|-------|
| Smart tool detection | ~50 | Minimal overhead |
| Per-chunk analysis | ~400-600 | Depends on chunk content |
| Total per-chunk | ~450-650 | Consistent across chunks |
| Executive summary | ~1000 | Synthesis of 5 chunk summaries |
| Key findings | ~1500 | Across-chunk aggregation |
| **Total for 400 chunks** | ~200k-300k | Compare: 5000+ baseline × 400 requests = 2M+ tokens |

**Savings:** 85-90% reduction through checkpoint reuse on key rotation

### Latency

- First key: Linear (process all chunks sequentially)
- Key rotations: Skip already-processed chunks, resume from next
- Report generation: Parallelizable in future multi-worker version

## Future Enhancements

### Multi-Agent Distribution
```python
# Future: Spawn multiple workers
agent1.analyze_chunks(0-100)
agent2.analyze_chunks(100-200)
agent3.analyze_chunks(200-300)
orchestrator.merge_results()
```

### Specialized Analysis Agents
```python
# Financial analyzer
# Legal analyzer
# Technical analyzer
# Each with own checkpoint system
```

### Vector Database Integration
```python
# Store chunk embeddings for semantic search
# Retrieve similar chunks during synthesis
# Build semantic graph of document
```

## Configuration

### Environment Variables

```bash
# Task checkpoint retention (days)
TASK_CHECKPOINT_RETENTION=30

# Chunk processing timeout (seconds)
CHUNK_TIMEOUT=300

# Max concurrent chunks (per worker)
MAX_CONCURRENT_CHUNKS=3
```

### Database Cleanup

```python
# Remove old checkpoints after 30 days
from storage.task_checkpoint import cleanup_old_checkpoints
cleanup_old_checkpoints(days=30)
```

## Testing

```python
# Test checkpoint system
def test_checkpoint_persistence():
    cp = TaskCheckpoint("test_001", "document_analysis")
    cp.save_checkpoint_state("stage1", 50, {"data": "test"})
    cp.mark_stage_complete("stage1")
    
    # Reload in new instance
    cp2 = TaskCheckpoint("test_001", "document_analysis")
    assert cp2.is_stage_complete("stage1")
    assert cp2.load_checkpoint_state("stage1")['data'] == "test"

# Test research engine with mock
def test_research_engine():
    from services.research_engine import ResearchEngine
    engine = ResearchEngine(ai)
    messages = list(engine.analyze_document(
        "test_research",
        "path/to/test.pdf"
    ))
    assert any("complete" in m.lower() for m in messages)
```

## Troubleshooting

### Task Stuck in "Processing"

Check database:
```sql
SELECT * FROM task_checkpoints WHERE task_id = 'your_task_id';
SELECT * FROM checkpoint_state WHERE checkpoint_id = X;
```

Kill task and retry:
```python
cp = TaskCheckpoint("stuck_task", "document_analysis")
cp.update_status("failed")  # Mark failed
# Restart with new task_id
```

### Missing Chunk Summaries

Verify checkpoint has chunks:
```python
cp = TaskCheckpoint("task_id", "document_analysis")
chunks = cp.get_processed_chunks()
print(f"Processed: {len(chunks)} chunks")
```

### Report Generation Failed

Check report sections:
```python
sections = cp.get_report_sections()
print(f"Sections: {len(sections)}")
```

Re-generate manually:
```python
cp.add_report_section("section_001", "Title", "Markdown content", [])
```

---

## Summary

The persistent task state architecture transforms Friday from a stateless chatbot into a **persistent research engine** capable of:

✓ Processing 1000+ page documents without restarting  
✓ Continuing seamlessly across API key rotations  
✓ Generating reports incrementally  
✓ Recovering from failures automatically  
✓ Scaling toward distributed multi-agent workflows  

All while maintaining token efficiency and providing transparent user experience.

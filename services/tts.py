"""
F.R.I.D.A.Y. — TTS Service
Wraps edge-tts with emotional prosody detection.
"""

import asyncio
import io
import re
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import edge_tts
from config import FRIDAY_VOICE, TTS_MODES


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting so TTS reads clean prose instead of symbols."""
    # Fenced code blocks → remove entirely (not useful for speech)
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'~~~[\s\S]*?~~~', '', text)
    # Bold+italic: ***text***
    text = re.sub(r'\*{3}(.+?)\*{3}', r'\1', text, flags=re.DOTALL)
    # Bold: **text**
    text = re.sub(r'\*{2}(.+?)\*{2}', r'\1', text, flags=re.DOTALL)
    # Italic: *text*
    text = re.sub(r'\*(.+?)\*', r'\1', text, flags=re.DOTALL)
    # Bold+italic: __text__
    text = re.sub(r'__(.+?)__', r'\1', text, flags=re.DOTALL)
    # Italic: _text_  (only when surrounded by word boundaries to avoid breaking snake_case)
    text = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'\1', text, flags=re.DOTALL)
    # Inline code: `code`
    text = re.sub(r'`(.+?)`', r'\1', text)
    # ATX headers: # Heading → Heading
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Blockquotes: > text → text
    text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)
    # Horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # Unordered list markers: - item / * item / + item → item
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    # Ordered list markers: 1. item → item
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # Links: [text](url) → text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Images: ![alt](url) → alt
    text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', r'\1', text)
    # Stray lone asterisks / underscores not part of words
    text = re.sub(r'(?<!\w)[*_]+(?!\w)', '', text)
    # Collapse excess blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _detect_tone(text: str) -> str:
    """Infer the appropriate tone/prosody from the response content."""
    t = text.lower()
    if re.search(r"\b(warning|alert|critical|danger|emergency|breach|threat|urgent)\b", t):
        return "urgent"
    if re.search(r"\b(sorry|unfortunately|regret|apolog|unable to|failed|cannot)\b", t):
        return "apologetic"
    if re.search(r"\b(excellent|perfect|outstanding|wonderful|great news|congratulations)\b", t):
        return "excited"
    if re.search(r"\b(relax|breathe|calm down|take it easy|steady)\b", t):
        return "calm"
    if re.search(r"\b(good morning|good afternoon|good evening|welcome back|good to see)\b", t):
        return "warm"
    return "normal"


async def _generate(text: str, tone: str) -> io.BytesIO:
    mode = TTS_MODES.get(tone, TTS_MODES["normal"])
    communicate = edge_tts.Communicate(
        text,
        FRIDAY_VOICE,
        rate=mode["rate"],
        pitch=mode["pitch"],
    )
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    buf.seek(0)
    return buf


def synthesize(text: str, tone: str = "auto") -> io.BytesIO:
    """
    Generate TTS audio for the given text.
    tone: 'auto' detects from text content, or pass an explicit tone key.
    """
    text = _strip_markdown(text)
    if tone == "auto":
        tone = _detect_tone(text)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_generate(text, tone))
    finally:
        loop.close()

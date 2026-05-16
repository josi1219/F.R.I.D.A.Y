"""
F.R.I.D.A.Y. — TTS Service
Wraps edge-tts with emotional prosody detection.
"""

import asyncio
import concurrent.futures
import io
import re
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import edge_tts
from config import FRIDAY_VOICE, TTS_MODES


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
    Runs the async edge-tts call in a fresh isolated thread to avoid
    conflicts with any running event loop in the caller's thread.
    """
    if tone == "auto":
        tone = _detect_tone(text)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, _generate(text, tone))
        return future.result()

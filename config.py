"""
F.R.I.D.A.Y. — Configuration
Loads settings from .env file.
"""

import os
from dotenv import load_dotenv

_BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_BASE, '.env'))

# ── Gemini ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# ── Flask ───────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(32).hex())

# ── TTS ─────────────────────────────────────────────────────────────────────
FRIDAY_VOICE = "en-IE-EmilyNeural"

TTS_MODES = {
    "normal":     {"rate": "+14%",  "pitch": "-2Hz"},
    "excited":    {"rate": "+18%", "pitch": "+3Hz"},
    "urgent":     {"rate": "+20%", "pitch": "+5Hz"},
    "calm":       {"rate": "+0%",  "pitch": "-6Hz"},
    "apologetic": {"rate": "-4%",  "pitch": "-4Hz"},
    "warm":       {"rate": "+5%",  "pitch": "-1Hz"},
}

# ── Storage ─────────────────────────────────────────────────────────────────
DB_PATH     = os.path.join(_BASE, "friday.db")
MAX_HISTORY = 30

# ── Voice ────────────────────────────────────────────────────────────────────
# tiny.en is ~4x faster than base.en on CPU — sufficient for voice commands
WHISPER_MODEL   = os.getenv("WHISPER_MODEL",   "tiny.en")
WHISPER_DEVICE  = "cpu"   # Intel UHD integrated — CPU-only path
WAKE_WORD_MODEL = os.getenv("WAKE_WORD_MODEL", "hey_jarvis")
HOTKEY_ACTIVATE = os.getenv("HOTKEY_ACTIVATE", "ctrl+alt+f")

# ── Overlay ──────────────────────────────────────────────────────────────────
OVERLAY_OPACITY  = float(os.getenv("OVERLAY_OPACITY",  "0.92"))
OVERLAY_POSITION = os.getenv("OVERLAY_POSITION", "bottom-right")

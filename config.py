"""
F.R.I.D.A.Y. — Configuration
Loads settings from .env file.
"""

import os
from dotenv import load_dotenv

_BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_BASE, '.env'))

# ── AI Provider ──────────────────────────────────────────────────────────────
# Switch between "gemini" and "groq" in .env
AI_PROVIDER   = os.getenv("AI_PROVIDER", "gemini").lower()

# ── Gemini ───────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")  # legacy single-key fallback
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Build ordered list from GEMINI_API_KEY_1, _2, _3 ... then fall back to GEMINI_API_KEY
_gemini_keys: list = []
for _i in range(1, 20):
    _k = os.getenv(f"GEMINI_API_KEY_{_i}", "")
    if _k:
        _gemini_keys.append(_k)
if GEMINI_API_KEY and GEMINI_API_KEY not in _gemini_keys:
    _gemini_keys.insert(0, GEMINI_API_KEY)
GEMINI_API_KEYS: list = _gemini_keys

# ── Groq ─────────────────────────────────────────────────────────────────────
GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL        = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# ── STT (Speech-to-Text) ─────────────────────────────────────────────────────
# Switch between "whisper" (offline), "groq", or "deepgram" in .env
STT_PROVIDER      = os.getenv("STT_PROVIDER", "whisper").lower()

# Offline Whisper settings
WHISPER_MODEL     = os.getenv("WHISPER_MODEL", "tiny.en")
WHISPER_DEVICE    = os.getenv("WHISPER_DEVICE", "cpu")

# Groq Whisper settings (reuses GROQ_API_KEY above)
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")

# Deepgram settings
DEEPGRAM_API_KEY  = os.getenv("DEEPGRAM_API_KEY", "")
DEEPGRAM_MODEL    = os.getenv("DEEPGRAM_MODEL", "nova-3")

# ── Flask ───────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(32).hex())

# ── TTS ─────────────────────────────────────────────────────────────────────
# en-GB-ThomasNeural — formal RP British male, closer to JARVIS (Paul Bettany)
# FRIDAY_VOICE = "en-GB-ThomasNeural"

# TTS_MODES = {
#     "normal":     {"rate": "-4%",   "pitch": "-4Hz"},   # calm, precise, JARVIS baseline
#     "excited":    {"rate": "+6%",   "pitch": "+0Hz"},   # quicker, still composed
#     "urgent":     {"rate": "+12%",  "pitch": "+2Hz"},   # brisk, alert
#     "calm":       {"rate": "-10%",  "pitch": "-8Hz"},   # very measured
#     "apologetic": {"rate": "-6%",   "pitch": "-6Hz"},   # slow, sincere
#     "warm":       {"rate": "-2%",   "pitch": "-3Hz"},   # gentle
# }



# orginal_friday
FRIDAY_VOICE = "en-IE-EmilyNeural"

TTS_MODES = {
    "normal":     {"rate": "+14%",  "pitch": "-2Hz"},
    "excited":    {"rate": "+18%", "pitch": "+3Hz"},
    "urgent":     {"rate": "+20%", "pitch": "+5Hz"},
    "calm":       {"rate": "+0%",  "pitch": "-6Hz"},
    "apologetic": {"rate": "-4%",  "pitch": "-4Hz"},
    "warm":       {"rate": "+5%",  "pitch": "-1Hz"},
}

#jarvis1
# FRIDAY_VOICE = "en-GB-RyanNeural"

# TTS_MODES = {
#     "normal":     {"rate": "-5%",   "pitch": "-8Hz"},   # calm, deliberate, JARVIS baseline
#     "excited":    {"rate": "+5%",   "pitch": "-4Hz"},   # slightly quicker, still composed
#     "urgent":     {"rate": "+10%",  "pitch": "-2Hz"},   # brisk but controlled
#     "calm":       {"rate": "-12%",  "pitch": "-12Hz"},  # very measured, deep
#     "apologetic": {"rate": "-8%",   "pitch": "-10Hz"},  # slow, sincere
#     "warm":       {"rate": "-4%",   "pitch": "-6Hz"},   # gentle, warm
# }
# ── Storage ─────────────────────────────────────────────────────────────────
DB_PATH     = os.path.join(_BASE, "friday.db")
MAX_HISTORY = 30

# ── Voice ────────────────────────────────────────────────────────────────────
# tiny.en is ~4x faster than base.en on CPU — sufficient for voice commands
WHISPER_MODEL   = os.getenv("WHISPER_MODEL",   "tiny.en")
WHISPER_DEVICE  = "cpu"   # Intel UHD integrated — CPU-only path
WAKE_WORD_MODEL = os.getenv("WAKE_WORD_MODEL", "hey_jarvis")
HOTKEY_ACTIVATE = os.getenv("HOTKEY_ACTIVATE", "ctrl+alt+f")

# ── 24/7 Operation ───────────────────────────────────────────────────────────
# Minutes of inactivity before Gemini chat history is silently reset
CHAT_IDLE_RESET_MINUTES = int(os.getenv("CHAT_IDLE_RESET_MINUTES", "120"))
# Points to lower system volume while FRIDAY speaks (0 = disable ducking)
VOLUME_DUCK_AMOUNT      = int(os.getenv("VOLUME_DUCK_AMOUNT", "40"))

# ── Conversation mode ────────────────────────────────────────────────────────
# Phrase that exits continuous conversation mode and returns to idle/wake-word
SLEEP_PHRASE = os.getenv("SLEEP_PHRASE", "sleep").lower()

# ── Wake keyword (STT-based spotter) ─────────────────────────────────────────
# Leave empty (default) to use the local OpenWakeWord model (hey_jarvis) for
# fast, offline wake detection — no API round-trip required.
# Set to a non-empty word (e.g. "friday") only to override with STT-based spotting.
WAKE_KEYWORD       = os.getenv("WAKE_KEYWORD", "").lower()
# Ultra-low RMS threshold for capturing audio bursts in keyword-spotter mode.
# Lower = more sensitive (even a whisper triggers a transcription check).
WAKE_VAD_THRESHOLD = float(os.getenv("WAKE_VAD_THRESHOLD", "0.001"))

# ── Voice Activity Detection ─────────────────────────────────────────────────
# RMS energy level to detect speech start (lower = more sensitive)
VAD_THRESHOLD     = float(os.getenv("VAD_THRESHOLD",     "0.005"))
# RMS level considered silence (lower = catches quieter speech)
VAD_SILENCE_THRESHOLD = float(os.getenv("VAD_SILENCE_THRESHOLD", "0.003"))

# ── Overlay ──────────────────────────────────────────────────────────────────
OVERLAY_OPACITY  = float(os.getenv("OVERLAY_OPACITY",  "0.92"))
OVERLAY_POSITION = os.getenv("OVERLAY_POSITION", "bottom-right")

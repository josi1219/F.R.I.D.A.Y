# Configuration Reference — F.R.I.D.A.Y.

All configuration is loaded from a `.env` file at the project root via `python-dotenv`. Copy `.env.example` to `.env` and edit your values before running.

> **Security:** Never commit `.env` to source control. It is listed in `.gitignore`.

---

## Table of Contents

- [AI Provider](#ai-provider)
- [Gemini Settings](#gemini-settings)
- [Groq Settings](#groq-settings)
- [Speech-to-Text (STT)](#speech-to-text-stt)
- [Text-to-Speech (TTS)](#text-to-speech-tts)
- [Flask / Web](#flask--web)
- [Storage](#storage)
- [Voice Pipeline](#voice-pipeline)
- [Wake Word & Hotkey](#wake-word--hotkey)
- [Voice Activity Detection](#voice-activity-detection)
- [24/7 Operation](#247-operation)
- [Complete .env.example](#complete-envexample)

---

## AI Provider

| Variable | Default | Values | Description |
|---|---|---|---|
| `AI_PROVIDER` | `gemini` | `gemini`, `groq` | Selects the active AI backend |

Switch between Gemini and Groq by changing this single variable.

---

## Gemini Settings

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Primary/fallback Gemini API key. Get one free at [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| `GEMINI_API_KEY_1` … `GEMINI_API_KEY_19` | — | Additional keys for automatic rotation on 429/quota errors. Keys are tried in numeric order |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Model name. Options: `gemini-2.0-flash`, `gemini-1.5-flash`, `gemini-1.5-pro` |

### Multi-key rotation

Supply multiple keys to avoid hitting per-key rate limits:

```dotenv
GEMINI_API_KEY_1=AIza...key1
GEMINI_API_KEY_2=AIza...key2
GEMINI_API_KEY_3=AIza...key3
```

On a 429 response FRIDAY automatically advances to the next key mid-session without interrupting the conversation.

---

## Groq Settings

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | — | Groq API key from [console.groq.com](https://console.groq.com) |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model to use |
| `GROQ_WHISPER_MODEL` | `whisper-large-v3-turbo` | Groq Whisper model for cloud STT |

To use Groq as the AI backend:
```dotenv
AI_PROVIDER=groq
GROQ_API_KEY=gsk_...
```

---

## Speech-to-Text (STT)

| Variable | Default | Values | Description |
|---|---|---|---|
| `STT_PROVIDER` | `whisper` | `whisper`, `groq`, `deepgram` | STT backend |

### Whisper (offline)

| Variable | Default | Description |
|---|---|---|
| `WHISPER_MODEL` | `tiny.en` | Model size: `tiny.en`, `base.en`, `small.en`, `medium.en` |
| `WHISPER_DEVICE` | `cpu` | `cpu` or `cuda` (GPU requires CUDA toolkit) |

### Groq Whisper (cloud)

Uses `GROQ_API_KEY`. Model configured by `GROQ_WHISPER_MODEL`.

### Deepgram (cloud)

| Variable | Default | Description |
|---|---|---|
| `DEEPGRAM_API_KEY` | — | Deepgram API key |
| `DEEPGRAM_MODEL` | `nova-3` | Deepgram model |

---

## Text-to-Speech (TTS)

TTS is handled by Microsoft `edge-tts` (free, no API key required). Configuration is in `config.py` rather than `.env` because the voice identity is part of FRIDAY's persona.

To change voice or prosody, edit `config.py` directly:

```python
# Voice identity
FRIDAY_VOICE = "en-IE-EmilyNeural"   # Irish female — original FRIDAY

# Alternative voices
# FRIDAY_VOICE = "en-GB-ThomasNeural"   # British male — JARVIS-style
# FRIDAY_VOICE = "en-GB-RyanNeural"     # British male — alternative

# Prosody per emotional tone
TTS_MODES = {
    "normal":     {"rate": "+14%",  "pitch": "-2Hz"},
    "excited":    {"rate": "+18%",  "pitch": "+3Hz"},
    "urgent":     {"rate": "+20%",  "pitch": "+5Hz"},
    "calm":       {"rate": "+0%",   "pitch": "-6Hz"},
    "apologetic": {"rate": "-4%",   "pitch": "-4Hz"},
    "warm":       {"rate": "+5%",   "pitch": "-1Hz"},
}
```

Tone is auto-detected from response content by `services/tts._detect_tone()` based on keyword matching.

---

## Flask / Web

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | random hex | Flask session secret. Set to a long random string in production |

Generate a secure key:
```python
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Storage

Configured in `config.py` (not `.env`):

| Constant | Default | Description |
|---|---|---|
| `DB_PATH` | `friday.db` (project root) | SQLite database file path |
| `MAX_HISTORY` | `30` | Maximum conversation turns kept in memory |

---

## Voice Pipeline

| Variable | Default | Description |
|---|---|---|
| `HOTKEY_ACTIVATE` | `ctrl+alt+f` | Global hotkey to activate FRIDAY from any window |
| `WAKE_WORD_MODEL` | `hey_jarvis` | OpenWakeWord model filename (without extension) |
| `WAKE_KEYWORD` | `""` (disabled) | STT-based keyword spotter word. Leave empty to use OpenWakeWord instead |
| `WAKE_VAD_THRESHOLD` | `0.001` | RMS energy threshold for keyword-spotter audio capture. Lower = more sensitive |
| `SLEEP_PHRASE` | `sleep` | Spoken word that deactivates conversation mode and returns to idle |

---

## Wake Word & Hotkey

### Global hotkey

The default `ctrl+alt+f` activates FRIDAY from any foreground window. Change it in `.env`:

```dotenv
HOTKEY_ACTIVATE=ctrl+shift+space
```

Valid formats follow the `keyboard` library conventions (e.g. `ctrl+alt+f`, `win+shift+f`, `f8`).

### Wake word

When `openwakeword` is installed, FRIDAY listens for "hey jarvis" continuously in the background. To change the wake word, supply a different `openwakeword` model file:

```dotenv
WAKE_WORD_MODEL=alexa          # uses alexa.onnx from openwakeword
```

Available built-in models: `hey_jarvis`, `alexa`, `hey_mycroft`.

---

## Voice Activity Detection

Configured in `config.py`:

| Constant | Default | Description |
|---|---|---|
| `VAD_THRESHOLD` | `0.015` | RMS energy threshold for speech detection. Raise in noisy environments |
| `VAD_SILENCE_SECS` | `1.2` | Seconds of silence after which recording stops |
| `VAD_MAX_RECORD_SECS` | `30` | Maximum recording duration per utterance |
| `VAD_PRE_ROLL_SECS` | `0.3` | Audio buffer kept before speech starts |

---

## 24/7 Operation

| Variable | Default | Description |
|---|---|---|
| `CHAT_IDLE_RESET_MINUTES` | `120` | Minutes of inactivity before conversation history is silently reset |
| `VOLUME_DUCK_AMOUNT` | `40` | Percentage points to lower system volume while FRIDAY speaks (0 = disabled) |

---

## Complete .env.example

```dotenv
# ─── F.R.I.D.A.Y. Environment Configuration ───────────────────────────────
# Copy this file to .env and fill in your values.

# ── AI Provider ──────────────────────────────────────────────────────────────
AI_PROVIDER=gemini                   # gemini | groq

# ── Gemini ───────────────────────────────────────────────────────────────────
GEMINI_API_KEY=your_gemini_api_key_here
# Multiple keys for rotation (optional)
# GEMINI_API_KEY_1=key1
# GEMINI_API_KEY_2=key2
GEMINI_MODEL=gemini-2.0-flash

# ── Groq ─────────────────────────────────────────────────────────────────────
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_WHISPER_MODEL=whisper-large-v3-turbo

# ── STT ──────────────────────────────────────────────────────────────────────
STT_PROVIDER=whisper                 # whisper | groq | deepgram
WHISPER_MODEL=tiny.en                # tiny.en | base.en | small.en | medium.en
WHISPER_DEVICE=cpu                   # cpu | cuda

# Deepgram (only if STT_PROVIDER=deepgram)
DEEPGRAM_API_KEY=your_deepgram_api_key_here
DEEPGRAM_MODEL=nova-3

# ── Flask ─────────────────────────────────────────────────────────────────────
SECRET_KEY=change_this_to_a_random_string

# ── Voice Pipeline ────────────────────────────────────────────────────────────
HOTKEY_ACTIVATE=ctrl+alt+f
WAKE_WORD_MODEL=hey_jarvis
WAKE_KEYWORD=                        # leave empty to use OpenWakeWord
SLEEP_PHRASE=sleep

# ── 24/7 Operation ────────────────────────────────────────────────────────────
CHAT_IDLE_RESET_MINUTES=120
VOLUME_DUCK_AMOUNT=40
```

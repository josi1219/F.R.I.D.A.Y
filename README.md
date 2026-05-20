# F.R.I.D.A.Y.

**Female Replacement Intelligent Digital Assistant Youth**

A production-grade, locally-running AI personal assistant inspired by Tony Stark's FRIDAY from the Marvel films. Powered by Google Gemini or Groq, with full voice interaction, screen vision, computer control, and a web-based HUD interface.

---

## Table of Contents

- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Running Modes](#running-modes)
- [Configuration](#configuration)
- [Documentation](#documentation)
- [Project Structure](#project-structure)
- [License](#license)

---

## Features

| Category | Capabilities |
|---|---|
| **AI** | Gemini 2.0 Flash / Groq LLaMA — streaming responses, function calling, multi-key rotation |
| **Voice I/O** | Wake word ("hey jarvis"), hotkey (`Ctrl+Alt+F`), faster-whisper STT, edge-tts TTS with emotional prosody |
| **Screen Vision** | Full-screen & region capture via `mss`, AI image analysis via Gemini Vision |
| **Computer Control** | Mouse/keyboard automation, window management, process control, volume/brightness |
| **Browser Automation** | Playwright-powered Chromium control, TradingView chart opening |
| **Task & Memory** | SQLite-backed reminders, tasks, notes, and conversation memories |
| **System Info** | Battery, CPU, RAM, disk, network, running processes |
| **Overlay UI** | PyQt6 transparent HUD widget showing IDLE / LISTENING / THINKING / SPEAKING states |
| **Web UI** | Flask-served HUD at `http://localhost:5000` with streaming chat |
| **Watchdog** | Crash-loop protection with automatic restart for 24/7 operation |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     run_overlay.py                      │
│  (Entry point — Flask + PyQt6 + Engine all in one)      │
└───────────┬──────────────────────────┬──────────────────┘
            │                          │
   ┌────────▼──────┐          ┌────────▼──────────┐
   │  Flask app.py │          │  FridayEngine     │
   │  Web UI / API │          │  engine.py        │
   └───────────────┘          └────────┬──────────┘
                                       │
          ┌──────────────┬─────────────┴──────────────┐
          │              │                             │
   ┌──────▼──────┐ ┌─────▼──────┐           ┌────────▼──────┐
   │VoiceListener│ │VoiceSpeaker│           │  FridayOverlay│
   │ voice/      │ │ voice/     │           │  overlay/     │
   └──────┬──────┘ └─────┬──────┘           └───────────────┘
          │              │
   ┌──────▼──────────────▼────────────────────────────────┐
   │                  FridayAI  services/ai.py             │
   │      Gemini / Groq  +  Function Calling               │
   └──────────────┬───────────────────────────────────────┘
                  │
     ┌────────────┴───────────────┐
     │        services/tools.py   │
     │  All AI-callable functions │
     └───────┬────────────────────┘
             │
    ┌────────┴──────────┐
    │  storage/db.py    │
    │  SQLite persistence│
    └───────────────────┘
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full system design.

---

## Requirements

- **OS:** Windows 10/11 (required for PyQt6 overlay, `pycaw`, `pywin32`)
- **Python:** 3.10 or later
- **API Keys:** Google Gemini API key (or Groq API key for Groq mode)
- **Optional:** Microphone for voice input

---

## Quick Start

### 1 — Clone and install

```bash
git clone https://github.com/josi1219/F.R.I.D.A.Y.git
cd friday
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 2 — Configure

```bash
copy .env.example .env
# Edit .env and add your GEMINI_API_KEY (and any other keys you need)
```

### 3 — Run

```bash
# Full experience (voice + overlay + web UI)
python run_overlay.py

# Web UI only (no voice, no overlay)
python app.py

# Desktop app wrapper (pywebview)
python run_desktop.py

# 24/7 watchdog (auto-restarts on crash)
python watchdog.py
```

Open **http://localhost:5000** in your browser for the web interface.

---

## Running Modes

| Command | Description |
|---|---|
| `python app.py` | Flask web server only — chat via browser at `:5000` |
| `python run_desktop.py` | Flask + pywebview native window |
| `python run_overlay.py` | Full stack — Flask + PyQt6 overlay + voice pipeline |
| `python watchdog.py` | Production launcher — keeps `run_overlay.py` alive 24/7 |
| `run_friday.bat` | Convenience batch launcher |

---

## Configuration

All settings live in `.env` (copy from `.env.example`). Key variables:

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Google AI Studio API key |
| `AI_PROVIDER` | `gemini` | `gemini` or `groq` |
| `STT_PROVIDER` | `whisper` | `whisper`, `groq`, or `deepgram` |
| `WHISPER_MODEL` | `tiny.en` | faster-whisper model size |
| `HOTKEY_ACTIVATE` | `ctrl+alt+f` | Global hotkey to activate listening |

Full reference: [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

---

## Documentation

| Document | Description |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, module map, data-flow diagrams |
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Step-by-step installation for all environments |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | All `.env` variables and `config.py` settings |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | REST API endpoint reference |
| [docs/MODULES.md](docs/MODULES.md) | Developer reference for every module |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [SECURITY.md](SECURITY.md) | Security policy and vulnerability reporting |

---

## Project Structure

```
Friday/
├── app.py                  # Flask application & routes
├── config.py               # Configuration loader
├── engine.py               # Core voice pipeline orchestrator
├── run_overlay.py          # Full-stack launcher (recommended)
├── run_desktop.py          # pywebview desktop launcher
├── watchdog.py             # 24/7 process watchdog
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
│
├── services/
│   ├── ai.py               # FridayAI — Gemini/Groq provider
│   ├── tools.py            # All AI function-calling tools
│   └── tts.py              # Text-to-speech with prosody detection
│
├── voice/
│   ├── listener.py         # Microphone input, VAD, Whisper STT
│   └── speaker.py          # Audio playback with volume ducking
│
├── overlay/
│   └── window.py           # PyQt6 transparent HUD overlay
│
├── vision/
│   ├── capture.py          # Screen capture (mss)
│   └── analyzer.py         # AI-powered screen analysis
│
├── automation/
│   ├── browser.py          # Playwright browser automation
│   └── mouse_keyboard.py   # PyAutoGUI input control
│
├── storage/
│   └── db.py               # SQLite layer (reminders, tasks, notes, memories)
│
└── templates/
    └── index.html          # Web HUD frontend
```

---

## License

This project is for personal and educational use. The FRIDAY character concept is the property of Marvel/Disney. This project is not affiliated with or endorsed by Marvel Studios.

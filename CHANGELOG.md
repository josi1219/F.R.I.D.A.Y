# Changelog — F.R.I.D.A.Y.

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned
- Gmail integration (send, read, search emails)
- Calendar integration (Google Calendar / Outlook)
- Proactive reminder notifications with voice alerts
- Multi-monitor overlay support
- Custom wake-word training

---

## [2.0.0] — 2026-05-20

### Added
- **Gemini 2.0 Flash** as primary AI provider with full function-calling support
- **Groq** provider as an alternative backend (LLaMA 3.3 70B)
- Multi-key rotation: up to 19 Gemini API keys auto-rotated on 429 errors
- **faster-whisper** STT pipeline (offline, CPU/GPU)
- Groq Whisper and Deepgram cloud STT options
- **OpenWakeWord** integration: "hey jarvis" wake word, always-on detection
- **PyQt6 transparent overlay** HUD with animated state indicator (IDLE/LISTENING/THINKING/SPEAKING/SLEEPING)
- `AnnotationOverlay` for on-screen element highlighting by vision tools
- **80+ AI-callable tools** across system, file, browser, vision, and automation domains
- Screen capture and Gemini Vision analysis (`capture_and_analyze_screen`, `read_text_on_screen`, `find_on_screen`)
- Computer control: `click_screen`, `type_on_screen`, `press_keyboard_key`, `keyboard_shortcut`
- Window management: `list_open_windows`, `focus_window`, `close_window`, `minimize_all_windows`
- File operations: `read_file_contents`, `list_directory`, `search_files`, `create_file`, `move_file`, `delete_file`
- Process management: `list_running_processes`, `kill_process`
- Volume and media control via `pycaw`: `get_volume`, `set_volume`, `media_play_pause`
- TradingView chart automation: `open_tradingview_chart`
- **SQLite persistence** for reminders, tasks, notes, and memories
- Reminder polling in background — speaks due reminders via TTS
- Volume ducking: system volume lowered while FRIDAY speaks, restored after
- Conversation mode: stay in LISTENING after each response until "sleep" command
- **Watchdog process** with crash-loop protection (max 10 restarts/hour)
- `setup_autostart.bat` — registers watchdog as Windows startup item
- Idle history reset: conversation cleared after 2 hours of inactivity
- `POST /chat/stream` SSE endpoint for real-time streaming responses
- Emotional prosody detection in TTS (`urgent`, `apologetic`, `excited`, `calm`, `warm`, `normal`)
- `run_overlay.py` unified launcher (Flask + Qt + Engine in one process)
- `run_desktop.py` pywebview launcher for native window experience

### Changed
- AI provider migrated from legacy `g4f` to Gemini/Groq with official SDKs
- STT migrated from `SpeechRecognition` (Google cloud-only) to `faster-whisper` (offline-first)
- TTS migrated from browser Web Speech API to server-side `edge-tts`
- Configuration centralised in `config.py` with `.env` file support

### Security
- Server binds to `127.0.0.1` only (not `0.0.0.0`)
- API keys loaded from `.env`, never hardcoded
- `delete_file` requires explicit AI confirmation before execution
- `restart_computer` and `shutdown_computer` require user confirmation

---

## [1.0.0] — 2025-12-01

### Added
- Initial Flask web assistant
- Basic chat via `g4f` (GPT-4-free wrapper)
- Browser-side Web Speech API for voice input
- Simple regex command matching
- `POST /chat` non-streaming endpoint
- `GET /status` health check
- Basic TTS via `edge-tts`

---

[Unreleased]: https://github.com/josi1219/F.R.I.D.A.Y/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/josi1219/F.R.I.D.A.Y/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/josi1219/F.R.I.D.A.Y/releases/tag/v1.0.0

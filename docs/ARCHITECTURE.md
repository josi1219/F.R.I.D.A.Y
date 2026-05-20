# Architecture — F.R.I.D.A.Y.

This document describes the system architecture, module responsibilities, thread model, and data-flow for the F.R.I.D.A.Y. assistant.

---

## Table of Contents

- [High-Level Overview](#high-level-overview)
- [Entry Points](#entry-points)
- [Module Map](#module-map)
- [Thread Model](#thread-model)
- [Voice Pipeline](#voice-pipeline)
- [AI Provider Layer](#ai-provider-layer)
- [Tool / Function-Calling System](#tool--function-calling-system)
- [Storage Layer](#storage-layer)
- [Overlay System](#overlay-system)
- [Web API Layer](#web-api-layer)
- [Inter-Module Communication](#inter-module-communication)
- [State Machine](#state-machine)
- [Dependency Graph](#dependency-graph)

---

## High-Level Overview

FRIDAY is a modular desktop AI assistant built around three subsystems that run concurrently:

1. **Web API** — Flask HTTP server providing the browser-based chat interface.
2. **Voice Pipeline** — Continuous microphone capture → STT → AI → TTS loop.
3. **Desktop Overlay** — PyQt6 transparent widget showing real-time assistant state.

All three share a single `FridayAI` instance and a single SQLite database.

```
                  ┌────────────────────────────────────────────────┐
                  │              run_overlay.py                     │
                  │         (process entry point)                   │
                  └────┬──────────────────┬──────────────────┬─────┘
                       │                  │                  │
              ┌────────▼──────┐  ┌────────▼──────┐  ┌───────▼──────────┐
              │  Flask Thread │  │  Qt App Thread│  │  Engine Threads  │
              │  app.py       │  │  overlay/     │  │  engine.py       │
              │  :5000        │  │  window.py    │  │                  │
              └───────────────┘  └───────────────┘  └──────────────────┘
                       │                                     │
                       └─────────────┬───────────────────────┘
                                     │
                         ┌───────────▼───────────┐
                         │      FridayAI          │
                         │   services/ai.py       │
                         │  Gemini / Groq client  │
                         └───────────┬────────────┘
                                     │
                    ┌────────────────┼──────────────────┐
                    │                │                  │
           ┌────────▼──────┐ ┌───────▼──────┐ ┌────────▼──────┐
           │ services/     │ │  storage/    │ │  vision/      │
           │ tools.py      │ │  db.py       │ │  capture.py   │
           │ (80+ tools)   │ │  SQLite      │ │  analyzer.py  │
           └───────────────┘ └──────────────┘ └───────────────┘
```

---

## Entry Points

### `run_overlay.py` — Recommended production launcher

Boots all three subsystems in order:

1. Calls `init_db()` to ensure the database schema exists.
2. Starts Flask in a **daemon thread** on `127.0.0.1:5000`.
3. Creates a `QApplication`.
4. Instantiates `FridayOverlay` and `AnnotationOverlay` widgets.
5. Instantiates `FridayAI` and `FridayEngine`.
6. Calls `engine.start()` — launches voice pipeline threads.
7. Enters `app.exec()` (Qt event loop, blocking main thread).

### `app.py` — Web-only mode

Runs Flask alone. Suitable for browser-only interaction without voice or overlay.

### `run_desktop.py` — pywebview mode

Embeds the Flask app in a native OS window via `pywebview`. No voice pipeline.

### `watchdog.py` — 24/7 wrapper

Spawns `run_overlay.py` as a child process. Restarts it on non-zero exit codes. Includes crash-loop protection (max 10 restarts/hour, then 5-minute pause).

---

## Module Map

| Path | Class / Entry | Responsibility |
|---|---|---|
| `app.py` | `Flask app` | HTTP routes, SSE streaming |
| `config.py` | module | `.env` loader, all constants |
| `engine.py` | `FridayEngine` | Voice pipeline orchestrator |
| `services/ai.py` | `FridayAI` | AI client, function calling, history |
| `services/tools.py` | functions | All AI-callable tool implementations |
| `services/tts.py` | `synthesize()` | edge-tts with prosody detection |
| `voice/listener.py` | `VoiceListener` | Mic capture, VAD, STT |
| `voice/speaker.py` | `VoiceSpeaker` | Audio playback, volume ducking |
| `overlay/window.py` | `FridayOverlay`, `AnnotationOverlay` | PyQt6 HUD widgets |
| `vision/capture.py` | functions | Screen capture via mss |
| `vision/analyzer.py` | functions | Gemini Vision analysis |
| `automation/browser.py` | `_BrowserSingleton` | Playwright Chromium automation |
| `automation/mouse_keyboard.py` | functions | PyAutoGUI input control |
| `storage/db.py` | functions | SQLite CRUD |
| `watchdog.py` | script | Process guardian |

---

## Thread Model

FRIDAY uses Python threads (not async) for concurrency. The main thread belongs to the Qt event loop.

```
Main Thread         Qt event loop (QApplication.exec)
Flask Thread        daemon — serves HTTP requests
Engine-Listen Thread  VoiceListener.listen_loop() — mic capture + STT
Engine-Loop Thread    FridayEngine._engine_loop() — orchestrates responses
Engine-Proactive Thread  FridayEngine._proactive_loop() — scheduled speech
Engine-Reminder Thread   reminder poller
```

Thread safety is managed with:
- `threading.Event` — stop signal
- `threading.Lock` — protecting `_is_active` flag
- `queue.Queue` — decoupling wake triggers and proactive speech
- SQLite `check_same_thread=False` — safe for concurrent reads

---

## Voice Pipeline

The voice pipeline is a state machine implemented in `FridayEngine` (`engine.py`).

```
  ┌──────────────────────────────────────────────────────────────┐
  │                        IDLE / SLEEPING                       │
  │  Waiting for: Ctrl+Alt+F hotkey  OR  wake word detection     │
  └──────────────┬───────────────────────────────────────────────┘
                 │  trigger
  ┌──────────────▼───────────────────────────────────────────────┐
  │                        LISTENING                             │
  │  VoiceListener records audio until silence (VAD)             │
  │  faster-whisper transcribes audio → text                     │
  └──────────────┬───────────────────────────────────────────────┘
                 │  transcribed text
  ┌──────────────▼───────────────────────────────────────────────┐
  │                        THINKING                              │
  │  1. local_fallback() — fast regex matcher (no AI call)       │
  │  2. FridayAI.chat() — Gemini/Groq with function calling      │
  └──────────────┬───────────────────────────────────────────────┘
                 │  response text
  ┌──────────────▼───────────────────────────────────────────────┐
  │                        SPEAKING                              │
  │  services/tts.synthesize() → edge-tts → MP3 bytes            │
  │  VoiceSpeaker.speak() — plays via pygame, ducks system vol   │
  └──────────────┬───────────────────────────────────────────────┘
                 │
  ┌──────────────▼───────────────────────────────────────────────┐
  │    Conversation mode?                                        │
  │    YES → return to LISTENING                                 │
  │    NO  → return to IDLE                                      │
  └──────────────────────────────────────────────────────────────┘
```

### Wake Word Detection

`VoiceListener` supports two wake methods:

1. **OpenWakeWord** (preferred): runs a lightweight neural model on every audio frame. Triggers on "hey_jarvis" with no cloud call.
2. **STT-based keyword spotter**: transcribes short audio bursts and checks for `WAKE_KEYWORD` in the text. Slower but configurable.

---

## AI Provider Layer

`services/ai.py` — `FridayAI` class

### Provider selection

Controlled by `AI_PROVIDER` in `.env`:
- `gemini` → `google-genai` SDK, `gemini-2.0-flash` by default
- `groq` → `groq` SDK, `llama-3.3-70b-versatile` by default

### Multi-key rotation (Gemini)

Up to 19 API keys can be supplied as `GEMINI_API_KEY_1` … `GEMINI_API_KEY_19`. On a 429/quota error, `FridayAI` rotates to the next key automatically without interrupting the response.

### Conversation history

History is kept in memory as a list of `{role, parts}` dicts. It is automatically trimmed to `MAX_HISTORY` (default 30) turns. After `CHAT_IDLE_RESET_MINUTES` (default 120) of inactivity, it is silently cleared on next use.

### Function calling

All functions in `services/tools.py` are passed to the AI as a tools list. The SDK auto-generates JSON schemas from type hints and docstrings. When the model emits a function call, `FridayAI` dispatches it synchronously and feeds the result back before yielding any text to the caller.

---

## Tool / Function-Calling System

`services/tools.py` contains ~80 functions grouped by capability:

| Group | Examples |
|---|---|
| Time & date | `get_current_time`, `get_current_date` |
| Weather | `get_weather` |
| System info | `get_battery_status`, `get_cpu_usage`, `get_ram_usage`, `get_disk_usage` |
| App control | `open_application`, `open_website`, `open_file` |
| Window mgmt | `list_open_windows`, `focus_window`, `close_window`, `minimize_all_windows` |
| File ops | `read_file_contents`, `list_directory`, `search_files`, `create_file`, `create_folder`, `move_file`, `delete_file`, `download_file` |
| Process mgmt | `list_running_processes`, `get_process_info`, `kill_process` |
| Volume/media | `get_volume`, `set_volume`, `mute_volume`, `unmute_volume`, `media_play_pause`, `media_next_track` |
| Browser | `open_browser_to`, `open_tradingview_chart` |
| Screen vision | `capture_and_analyze_screen`, `read_text_on_screen`, `find_on_screen` |
| Input control | `click_screen`, `type_on_screen`, `press_keyboard_key`, `keyboard_shortcut` |
| Search | `web_search`, `get_directions` |
| Storage | `add_reminder`, `list_reminders`, `complete_reminder`, `add_task`, `list_tasks`, `add_note`, `add_memory` |
| Power | `lock_screen`, `sleep_computer`, `restart_computer`, `shutdown_computer` |
| Clipboard | `read_clipboard`, `write_clipboard` |
| Network | `get_network_info` |

Tool functions are pure Python — they have no dependency on the AI layer and can be called independently for testing.

---

## Storage Layer

`storage/db.py` — SQLite via the standard library `sqlite3`

### Tables

| Table | Purpose | Key columns |
|---|---|---|
| `reminders` | Time-based alerts | `text`, `due_time` (ISO string), `done` |
| `tasks` | To-do items | `text`, `priority`, `done` |
| `notes` | Free-form notes | `title`, `content` |
| `memories` | Long-term AI memory facts | `content`, `context` |

Database file: `friday.db` in the project root (path from `config.DB_PATH`).

The schema is created idempotently on every startup via `init_db()` using `CREATE TABLE IF NOT EXISTS`.

---

## Overlay System

`overlay/window.py` — PyQt6

### FridayOverlay

A small `QWidget` with `WA_TranslucentBackground` and `WindowStaysOnTopHint`. Positioned bottom-right. Draggable. Shows:
- Animated pulsing circle whose colour reflects the current state.
- Status text label.
- Transcribed text / response preview.

State colours:

| State | Colour |
|---|---|
| IDLE | Dim blue |
| LISTENING | Bright green |
| THINKING | Amber |
| SPEAKING | Purple |
| SLEEPING | Very dim dark blue |

### AnnotationOverlay

A full-screen transparent widget used to draw coloured bounding-box highlights when FRIDAY uses `find_on_screen` or identifies elements via vision tools.

---

## Web API Layer

`app.py` — Flask

Routes are documented in full in [API_REFERENCE.md](API_REFERENCE.md). Summary:

| Route | Method | Description |
|---|---|---|
| `/` | GET | Serves the web HUD |
| `/chat/stream` | POST | SSE streaming chat response |
| `/chat` | POST | Non-streaming chat response |
| `/chat/reset` | POST | Clears conversation history |
| `/tts` | POST | Synthesize audio, returns MP3 |
| `/listen` | POST | Record one phrase via microphone, return transcript |
| `/status` | GET | Returns AI provider status |

---

## Inter-Module Communication

```
FridayEngine  ──set_state()──►  FridayOverlay   (direct method call, Qt-thread-safe via QMetaObject)
FridayEngine  ──inject_tool_refs()──►  services/tools.py  (module-level globals _engine, _ann_overlay)
VoiceListener ──Queue.put()──►  FridayEngine._listen_q  (wake trigger)
FridayAI      ──dispatch()──►  services/tools.py functions  (direct call in engine thread)
Flask routes  ──FridayAI.chat()──►  FridayAI  (Flask worker thread, lock-guarded)
```

---

## State Machine

The engine state is a simple string managed by `FridayEngine`:

```
          ┌──────────┐
    ┌────►│  IDLE    │◄────────────────────────────────┐
    │     └────┬─────┘                                 │
    │          │ hotkey / wake word                    │
    │     ┌────▼──────┐                                │
    │     │ LISTENING  │                               │
    │     └────┬──────┘                                │
    │          │ speech detected                       │
    │     ┌────▼──────┐                                │
    │     │ THINKING  │                                │
    │     └────┬──────┘                                │
    │          │ response ready                        │
    │     ┌────▼──────┐    conversation mode?          │
    │     │ SPEAKING  │──────────────────────────────► │ (loop to LISTENING)
    │     └────┬──────┘                                │
    │          │ done speaking                         │
    └──────────┘
```

`sleep` command → transitions to `SLEEPING`. Any hotkey/wake-word → back to `IDLE`.

---

## Dependency Graph

```
run_overlay.py
  ├── app.py
  │   ├── config.py
  │   ├── services/ai.py
  │   │   ├── config.py
  │   │   └── services/tools.py
  │   │       ├── config.py
  │   │       ├── storage/db.py
  │   │       ├── vision/capture.py
  │   │       ├── vision/analyzer.py
  │   │       └── automation/browser.py
  │   ├── services/tts.py
  │   └── storage/db.py
  ├── engine.py
  │   ├── config.py
  │   ├── voice/listener.py
  │   ├── voice/speaker.py
  │   └── services/tts.py
  └── overlay/window.py
      └── config.py
```

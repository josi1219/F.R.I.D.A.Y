# Module Reference — F.R.I.D.A.Y.

Developer reference for every Python module in the project. Each section covers the module's purpose, public API, and key design decisions.

---

## Table of Contents

- [app.py](#apppy)
- [config.py](#configpy)
- [engine.py](#enginepy)
- [services/ai.py](#servicesaipy)
- [services/tools.py](#servicestoolspy)
- [services/tts.py](#servicesttsspy)
- [voice/listener.py](#voicelistenerpy)
- [voice/speaker.py](#voicespeakerpy)
- [overlay/window.py](#overlaywindowpy)
- [vision/capture.py](#visioncapturepy)
- [vision/analyzer.py](#visionanalyzerpy)
- [automation/browser.py](#automationbrowserpy)
- [automation/mouse_keyboard.py](#automationmouse_keyboardpy)
- [storage/db.py](#storagedbpy)
- [watchdog.py](#watchdogpy)

---

## app.py

**Flask application and HTTP route definitions.**

### Overview

`app.py` is the web layer. It bootstraps the database and AI service on import, registers all HTTP routes, and provides a `local_fallback()` fast-path that handles common queries with zero AI round-trip.

### Key components

#### `local_fallback(text: str) -> str | None`

Regex-based pre-processor that matches common greetings, identity questions, jokes, and control commands before sending to the AI. Returns `None` for anything it can't handle, falling through to `FridayAI`.

**Why it exists:** Eliminates latency for the most frequent commands and provides a safety net when the AI backend is offline.

#### Flask routes

See [API_REFERENCE.md](API_REFERENCE.md) for full HTTP documentation.

| Route | Handler | Notes |
|---|---|---|
| `GET /` | `index()` | Renders `templates/index.html` |
| `POST /chat/stream` | `chat_stream()` | SSE streaming response |
| `POST /chat` | `chat()` | Non-streaming response |
| `POST /chat/reset` | `chat_reset()` | Clears AI history |
| `POST /tts` | `tts()` | Returns MP3 audio |
| `POST /listen` | `listen()` | Microphone capture (browser mode) |
| `GET /status` | `status()` | Provider health check |

### Module-level singletons

```python
ai = FridayAI()    # shared across all Flask worker threads
```

Thread safety: `FridayAI.chat()` is lock-guarded internally.

---

## config.py

**Central configuration loader.**

Loads all settings from `.env` using `python-dotenv`. All other modules import from `config` rather than reading environment variables directly.

### Constants

| Name | Type | Source |
|---|---|---|
| `AI_PROVIDER` | `str` | `$AI_PROVIDER` |
| `GEMINI_API_KEY` | `str` | `$GEMINI_API_KEY` |
| `GEMINI_API_KEYS` | `list[str]` | Built from `$GEMINI_API_KEY_1`…`_19` + fallback |
| `GEMINI_MODEL` | `str` | `$GEMINI_MODEL` |
| `GROQ_API_KEY` | `str` | `$GROQ_API_KEY` |
| `GROQ_MODEL` | `str` | `$GROQ_MODEL` |
| `STT_PROVIDER` | `str` | `$STT_PROVIDER` |
| `WHISPER_MODEL` | `str` | `$WHISPER_MODEL` |
| `WHISPER_DEVICE` | `str` | `$WHISPER_DEVICE` |
| `FRIDAY_VOICE` | `str` | Hardcoded `"en-IE-EmilyNeural"` |
| `TTS_MODES` | `dict` | Hardcoded prosody settings |
| `DB_PATH` | `str` | `<project_root>/friday.db` |
| `MAX_HISTORY` | `int` | `30` |
| `HOTKEY_ACTIVATE` | `str` | `$HOTKEY_ACTIVATE` |
| `WAKE_WORD_MODEL` | `str` | `$WAKE_WORD_MODEL` |
| `SLEEP_PHRASE` | `str` | `$SLEEP_PHRASE` |
| `CHAT_IDLE_RESET_MINUTES` | `int` | `$CHAT_IDLE_RESET_MINUTES` |
| `VOLUME_DUCK_AMOUNT` | `int` | `$VOLUME_DUCK_AMOUNT` |
| `SECRET_KEY` | `str` | `$SECRET_KEY` or random hex |

---

## engine.py

**Core voice pipeline orchestrator.**

### `FridayEngine`

```python
class FridayEngine:
    def __init__(self, ai: FridayAI, overlay: FridayOverlay, annotation_overlay=None)
    def start() -> None
    def stop() -> None
    def trigger_listen() -> None
    def say(text: str, tone: str = "auto") -> None
    def set_conversation_mode(enabled: bool) -> None
```

#### `start()`

Launches four daemon threads:
- `_engine_loop` — main LISTENING → THINKING → SPEAKING cycle
- `_listen_loop_thread` — runs `VoiceListener.listen_loop()`
- `_proactive_loop` — processes queued proactive speech
- `_reminder_poll` — checks SQLite reminders every 30 seconds

Registers the global hotkey (`Ctrl+Alt+F`) via the `keyboard` library.

#### `stop()`

Sets `_stop_event`, unregisters the hotkey, and waits for threads to exit.

#### State management

The engine notifies `FridayOverlay` of state changes by calling `overlay.set_state(state)`. All Qt calls go through `QMetaObject.invokeMethod` to be thread-safe.

#### Volume ducking

Before speaking, `VoiceSpeaker` lowers system volume by `VOLUME_DUCK_AMOUNT` (default 40%) and restores it afterwards. This ensures the user can hear FRIDAY over background audio.

#### Conversation mode

When activated, after each response the engine immediately returns to LISTENING instead of IDLE. The user can chain multiple commands without re-triggering. Speaking the `SLEEP_PHRASE` (default `"sleep"`) exits conversation mode.

---

## services/ai.py

**AI provider abstraction with function calling.**

### `FridayAI`

```python
class FridayAI:
    enabled: bool                  # False if no valid key found
    def chat(text: str) -> str
    def chat_stream(text: str) -> Iterator[str]
    def reset() -> None
```

#### Provider selection

On instantiation, reads `config.AI_PROVIDER` and initialises either the Gemini or Groq client. If no API key is found, `enabled` is set to `False` and all calls return empty strings.

#### Gemini implementation

- Uses `google-genai` SDK with `GenerativeModel.generate_content`.
- Passes all `services/tools.py` functions as a `tools=` list — the SDK auto-generates JSON schemas.
- Conversation history is maintained as a list of content dicts.
- On `429 ResourceExhausted`: rotates to next key in `GEMINI_API_KEYS`, retries once.

#### Groq implementation

- Uses `groq` SDK with `client.chat.completions.create`.
- Supports function calling via the OpenAI-compatible tool calling API.
- Same conversation history format.

#### `chat_stream()`

Yields text token chunks as they arrive from the API. Used by `POST /chat/stream`. For function calls the engine resolves them silently before yielding any text.

#### History management

History is trimmed to `MAX_HISTORY` turns (oldest first) on each call. After `CHAT_IDLE_RESET_MINUTES` of inactivity, history is cleared transparently on the next call.

---

## services/tools.py

**All AI-callable tool implementations.**

### Design

Each function:
- Has **type-annotated parameters** so the SDK auto-generates JSON schemas.
- Has a **docstring** that becomes the function description shown to the model.
- Returns a **plain string** (the tool result fed back to the model).
- Has **no side effects** beyond what the name implies.
- Uses **lazy imports** (inside function body) for optional heavy dependencies.

### Module-level runtime references

```python
_engine      = None   # injected by run_overlay.py
_ann_overlay = None   # injected by run_overlay.py
```

These are set at startup to allow tools to call `engine.say()` or draw overlays.

### Tool categories

#### Time & weather
`get_current_time()`, `get_current_date()`, `get_weather(city: str)`

#### System information
`get_battery_status()`, `get_cpu_usage()`, `get_ram_usage()`, `get_disk_usage()`, `get_network_info()`

#### Application control
`open_application(name: str)`, `open_website(url: str)`, `open_file(path: str)`

#### Window management
`list_open_windows()`, `focus_window(title: str)`, `close_window(title: str)`, `minimize_window(title: str)`, `maximize_window(title: str)`, `minimize_all_windows()`

#### File operations
`read_file_contents(path: str)`, `list_directory(path: str)`, `search_files(name: str, directory: str)`, `create_file(path: str, content: str)`, `create_folder(path: str)`, `move_file(src: str, dest: str)`, `delete_file(path: str)`, `download_file(url: str, save_path: str)`

#### Process management
`list_running_processes()`, `get_process_info(name: str)`, `kill_process(name: str)`

#### Volume & media
`get_volume()`, `set_volume(level: int)`, `mute_volume()`, `unmute_volume()`, `media_play_pause()`, `media_next_track()`, `media_previous_track()`, `media_stop()`

#### Browser automation
`open_browser_to(url: str)`, `open_tradingview_chart(symbol: str, interval: str)`

#### Screen vision
`capture_and_analyze_screen(question: str)`, `read_text_on_screen()`, `find_on_screen(element_description: str)`

#### Input control
`click_screen(x: int, y: int)`, `type_on_screen(text: str)`, `press_keyboard_key(key: str)`, `keyboard_shortcut(shortcut: str)`

#### Web search
`web_search(query: str)`, `get_directions(origin: str, destination: str)`

#### Storage / memory
`add_reminder(text: str, due_time: str)`, `list_reminders()`, `complete_reminder(id: int)`, `add_task(text: str, priority: str)`, `list_tasks()`, `complete_task(id: int)`, `add_note(title: str, content: str)`, `list_notes()`, `add_memory(content: str, context: str)`

#### Power
`lock_screen()`, `sleep_computer()`, `restart_computer()`, `shutdown_computer()`, `cancel_shutdown()`

#### Clipboard
`read_clipboard()`, `write_clipboard(text: str)`

---

## services/tts.py

**Text-to-speech with emotional prosody.**

### `synthesize(text: str, tone: str = "auto") -> io.BytesIO`

Generates MP3 audio for the given text. Runs `edge-tts` in an isolated thread to avoid event loop conflicts.

Returns a `BytesIO` buffer positioned at offset 0 ready for streaming.

### `_detect_tone(text: str) -> str`

Keyword-based tone classifier. Returns one of: `urgent`, `apologetic`, `excited`, `calm`, `warm`, `normal`.

| Keywords | → Tone |
|---|---|
| warning, alert, critical, danger, emergency | `urgent` |
| sorry, unfortunately, regret, apolog, failed, cannot | `apologetic` |
| excellent, perfect, wonderful, great news, congratulations | `excited` |
| relax, breathe, calm down, take it easy | `calm` |
| good morning/afternoon/evening, welcome back | `warm` |
| (default) | `normal` |

### Edge TTS voice selection

Set `FRIDAY_VOICE` in `config.py`. The value must be a valid edge-tts voice name. List all available voices:

```python
import asyncio, edge_tts
asyncio.run(edge_tts.list_voices())
```

---

## voice/listener.py

**Microphone input with VAD and STT.**

### `VoiceListener`

```python
class VoiceListener:
    def listen_loop(stop_event: threading.Event, on_speech: Callable[[str], None]) -> None
    def listen_once(timeout: float = 8.0) -> str
```

#### Pipeline

1. `sounddevice` opens a continuous 16 kHz mono input stream.
2. Audio frames are checked against `VAD_THRESHOLD` (RMS energy).
3. When energy exceeds the threshold, recording begins. Pre-roll buffer is prepended.
4. Recording stops after `VAD_SILENCE_SECS` of low energy or `VAD_MAX_RECORD_SECS` total.
5. Recorded audio is passed to `_transcribe()`.

#### STT backends

- **faster-whisper** (default): local, offline, runs on CPU or CUDA.
- **Groq Whisper**: cloud, high accuracy, requires `GROQ_API_KEY`.
- **Deepgram**: cloud, real-time, requires `DEEPGRAM_API_KEY`.

#### Wake word integration

When `openwakeword` is installed, `listen_loop` runs the model on every audio frame in parallel with VAD. On a wake detection event, it signals the engine regardless of VAD state.

---

## voice/speaker.py

**Audio playback with volume ducking.**

### `VoiceSpeaker`

```python
class VoiceSpeaker:
    def speak(audio: io.BytesIO) -> None
    def stop() -> None
```

Uses `pygame.mixer` for MP3 playback. Before playback:
1. Queries current system volume via `pycaw`.
2. Reduces it by `VOLUME_DUCK_AMOUNT` percent.
3. Plays the audio, blocking until complete.
4. Restores the original volume.

---

## overlay/window.py

**PyQt6 transparent desktop HUD.**

### `FridayOverlay(QWidget)`

```python
def set_state(state: str) -> None   # thread-safe via QMetaObject
def set_text(text: str) -> None
def show_notification(text: str, duration_ms: int = 3000) -> None
```

States: `"idle"`, `"listening"`, `"thinking"`, `"speaking"`, `"sleeping"`

The overlay uses `Qt.WindowType.WindowStaysOnTopHint` and `Qt.WindowType.Tool` to float above all windows without appearing in the taskbar. Background is fully transparent (`WA_TranslucentBackground`).

### `AnnotationOverlay(QWidget)`

Full-screen transparent drawing layer. Used to highlight screen regions found by vision tools.

```python
def highlight_region(x: int, y: int, w: int, h: int, label: str = "") -> None
def clear() -> None
```

---

## vision/capture.py

**Screen capture utilities.**

### Functions

```python
def capture_screen() -> Image | None
def capture_region(x: int, y: int, w: int, h: int) -> Image | None
def capture_to_base64(image: Image) -> str
def save_capture(image: Image, path: str) -> str
```

Uses `mss` for fast BitBlt-based capture. Falls back to `None` if `mss` or `Pillow` is unavailable.

---

## vision/analyzer.py

**AI-powered screen analysis via Gemini Vision.**

### Functions

```python
def analyze_screen(question: str) -> str
def read_text(image: Image) -> str
def find_element(image: Image, description: str) -> dict | None
```

`analyze_screen` captures the screen, encodes it as base64, and sends it to Gemini with the user's question. Uses the same API key and rotation logic as the chat session.

`find_element` returns `{"x": int, "y": int, "w": int, "h": int}` of the found element, or `None`.

---

## automation/browser.py

**Playwright-based browser automation.**

### `_BrowserSingleton`

Manages a single persistent Chromium instance. Lazy-initialised on first use. Thread-safe via an internal lock.

### Functions

```python
def open_browser_to(url: str) -> str
def open_tradingview_chart(symbol: str, interval: str = "1h") -> str
def browser_back() -> str
def browser_forward() -> str
def browser_refresh() -> str
def close_browser() -> str
```

All return strings suitable for AI tool responses (e.g. `"Opened Bitcoin chart on TradingView, Sir."`).

### TradingView interval mapping

| User says | Interval code |
|---|---|
| `1m`, `5m`, `15m`, `30m` | `1`, `5`, `15`, `30` |
| `1h`, `2h`, `4h` | `60`, `120`, `240` |
| `1d`, `1w`, `1M` | `D`, `W`, `M` |

---

## automation/mouse_keyboard.py

**PyAutoGUI input simulation.**

### Functions

```python
def click(x: int, y: int) -> str
def double_click(x: int, y: int) -> str
def right_click(x: int, y: int) -> str
def type_text(text: str) -> str
def press_key(key: str) -> str
def hotkey(*keys: str) -> str
def scroll(x: int, y: int, amount: int) -> str
def drag(x1: int, y1: int, x2: int, y2: int) -> str
```

All functions add a small randomised delay to appear more human-like and avoid triggering anti-automation detection.

---

## storage/db.py

**SQLite persistence layer.**

### Functions

```python
def get_conn() -> sqlite3.Connection
def init_db() -> None
```

### Schema

```sql
CREATE TABLE reminders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT    NOT NULL,
    due_time   TEXT,                    -- ISO datetime string 'YYYY-MM-DD HH:MM'
    created_at TEXT    DEFAULT (datetime('now','localtime')),
    done       INTEGER DEFAULT 0
);

CREATE TABLE tasks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT    NOT NULL,
    priority   TEXT    DEFAULT 'normal', -- 'low', 'normal', 'high'
    created_at TEXT    DEFAULT (datetime('now','localtime')),
    done       INTEGER DEFAULT 0
);

CREATE TABLE notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT,
    content    TEXT    NOT NULL,
    created_at TEXT    DEFAULT (datetime('now','localtime'))
);

CREATE TABLE memories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    content    TEXT    NOT NULL,
    context    TEXT,
    created_at TEXT    DEFAULT (datetime('now','localtime'))
);
```

`get_conn()` returns a connection with `row_factory = sqlite3.Row` so rows can be accessed by column name.

`init_db()` is idempotent — safe to call on every startup.

---

## watchdog.py

**24/7 process guardian.**

### Behaviour

- Spawns `run_overlay.py` via `subprocess.Popen`.
- Waits for the process to exit.
- **Exit code 0:** FRIDAY was intentionally closed. Watchdog stops.
- **Any other code:** Waits `RESTART_DELAY_SECS` (5s) and restarts.

### Crash-loop protection

If FRIDAY crashes `MAX_RESTARTS_PER_HOUR` (10) times within a rolling 60-minute window, the watchdog pauses `CRASH_PAUSE_SECS` (300s = 5 minutes) before the next attempt. The crash counter is then reset.

### Logging

All events are logged to both `stdout` and `friday_watchdog.log` in the project root with timestamps.

```
[2026-05-20 14:32:01] INFO: Starting FRIDAY (attempt 1)
[2026-05-20 14:35:44] WARNING: FRIDAY exited with code 1 — restarting in 5s
[2026-05-20 14:35:49] INFO: Starting FRIDAY (attempt 2)
```

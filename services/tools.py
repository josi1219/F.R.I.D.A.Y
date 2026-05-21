"""
F.R.I.D.A.Y. — Tool Functions
All functions callable by the Gemini AI via function calling.
Each function has type hints and a docstring so the SDK auto-generates its schema.
"""

import datetime
import os
import platform
import re
import subprocess
import webbrowser
import sys
from urllib.parse import quote_plus as _qp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Vision / Automation lazy imports ─────────────────────────────────────────
# These are imported at call time so tools.py still loads even if the packages
# are not yet installed.

# Runtime references injected by run_overlay.py
_engine      = None   # FridayEngine instance
_ann_overlay = None   # AnnotationOverlay instance

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import requests as req_lib
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from storage.db import get_conn


# ── Gemini vision helpers — shared client + rotation ─────────────────────────

def _get_vision_client():
    """
    Return (client, model_name) using the SAME key as the active chat session.
    Falls back to building a client from config if the engine isn't available.
    """
    if _engine is not None and hasattr(_engine, '_ai'):
        ai = _engine._ai
        if getattr(ai, '_client', None) is not None:
            return ai._client, ai._model_name
    # Fallback when running without the overlay engine (e.g. web-only mode)
    try:
        from google import genai as _genai
        import config as _cfg
        keys = getattr(_cfg, "GEMINI_API_KEYS", [])
        if keys:
            return _genai.Client(api_key=keys[0]), _cfg.GEMINI_MODEL
    except Exception:
        pass
    return None, None


def _rotate_vision_key() -> bool:
    """Tell the AI service to advance to the next API key (shared with chat)."""
    if _engine is not None and hasattr(_engine, '_ai'):
        ai = _engine._ai
        if hasattr(ai, '_rotate_gemini_key'):
            return ai._rotate_gemini_key()
    return False


def _is_vision_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(x in msg for x in (
        "429", "quota", "resource_exhausted", "rate limit",
        "ratelimitexceeded", "too many requests", "quota exceeded",
    ))


# ── Time / Date ──────────────────────────────────────────────────────────────

def get_current_time() -> str:
    """Get the current local time in 12-hour format."""
    return datetime.datetime.now().strftime('%I:%M %p')


def get_current_date() -> str:
    """Get the current date including the day of the week."""
    return datetime.datetime.now().strftime('%A, %B %d, %Y')


# ── System ───────────────────────────────────────────────────────────────────

def get_battery_status() -> str:
    """Get the current battery percentage and whether the device is charging."""
    if not HAS_PSUTIL:
        return "psutil not available"
    try:
        b = psutil.sensors_battery()
        if not b:
            return "No battery detected — desktop system"
        state = "charging" if b.power_plugged else "on battery"
        secs = b.secsleft
        time_left = f", approximately {secs // 3600}h {(secs % 3600) // 60}m remaining" if secs > 0 else ""
        return f"{b.percent:.0f}% {state}{time_left}"
    except Exception as e:
        return f"Battery check failed: {e}"


def get_cpu_usage() -> str:
    """Get current CPU load percentage and core count."""
    if not HAS_PSUTIL:
        return "psutil not available"
    try:
        cpu = psutil.cpu_percent(interval=1)
        cores = psutil.cpu_count()
        freq = psutil.cpu_freq()
        freq_str = f" at {freq.current:.0f} MHz" if freq else ""
        return f"{cpu}% usage across {cores} cores{freq_str}"
    except Exception as e:
        return f"CPU check failed: {e}"


def get_memory_usage() -> str:
    """Get current RAM usage — how much is used versus total."""
    if not HAS_PSUTIL:
        return "psutil not available"
    try:
        m = psutil.virtual_memory()
        avail = m.available / (1024 ** 3)
        total = m.total / (1024 ** 3)
        return f"{m.percent}% used — {avail:.1f} GB free of {total:.1f} GB total"
    except Exception as e:
        return f"Memory check failed: {e}"


def get_disk_usage() -> str:
    """Get disk space usage for the main system drive."""
    if not HAS_PSUTIL:
        return "psutil not available"
    try:
        path = 'C:\\' if platform.system() == 'Windows' else '/'
        d = psutil.disk_usage(path)
        free  = d.free  / (1024 ** 3)
        total = d.total / (1024 ** 3)
        return f"{d.percent}% full — {free:.1f} GB free of {total:.1f} GB total"
    except Exception as e:
        return f"Disk check failed: {e}"


def get_system_info() -> str:
    """Get operating system name, version, and machine architecture."""
    return (
        f"{platform.system()} {platform.release()} "
        f"({platform.machine()}) — host: {platform.node()}"
    )


def get_weather(location: str = "") -> str:
    """
    Get the current weather conditions.
    location: optional city name or empty for local weather.
    """
    if not HAS_REQUESTS:
        return "requests library not available"
    try:
        q = location.strip().replace(' ', '+') if location.strip() else ""
        resp = req_lib.get(f"https://wttr.in/{q}?format=3", timeout=6)
        return resp.text.strip()
    except Exception as e:
        return f"Weather unavailable: {e}"


# ── Applications ─────────────────────────────────────────────────────────────

_APP_MAP: dict[str, str] = {
    "calculator":        "calc.exe",
    "calc":              "calc.exe",
    "notepad":           "notepad.exe",
    "explorer":          "explorer.exe",
    "file explorer":     "explorer.exe",
    "my files":          "explorer.exe",
    "task manager":      "taskmgr.exe",
    "taskmgr":           "taskmgr.exe",
    "settings":          "ms-settings:",
    "windows settings":  "ms-settings:",
    "control panel":     "control",
    "paint":             "mspaint.exe",
    "mspaint":           "mspaint.exe",
    "wordpad":           "wordpad.exe",
    "snipping tool":     "snippingtool.exe",
    "snip":              "snippingtool.exe",
    "camera":            "microsoft.windows.camera:",
    "photos":            "ms-photos:",
    "store":             "ms-windows-store:",
    "windows store":     "ms-windows-store:",
    "mail":              "outlookmail:",
    "calendar":          "outlookcal:",
    "maps":              "bingmaps:",
    "clock":             "ms-clock:",
    "alarm":             "ms-clock:",
    "music":             "mswindowsmusic:",
    "video":             "mswindowsvideo:",
    "spotify":           "spotify",
    "chrome":            "chrome",
    "google chrome":     "chrome",
    "firefox":           "firefox",
    "mozilla firefox":   "firefox",
    "edge":              "msedge",
    "microsoft edge":    "msedge",
    "discord":           "discord",
    "slack":             "slack",
    "zoom":              "zoom",
    "teams":             "msteams",
    "microsoft teams":   "msteams",
    "vs code":           "code",
    "vscode":            "code",
    "visual studio code":"code",
    "terminal":          "wt",
    "windows terminal":  "wt",
    "cmd":               "cmd",
    "command prompt":    "cmd",
    "powershell":        "powershell",
    "word":              "winword",
    "microsoft word":    "winword",
    "excel":             "excel",
    "microsoft excel":   "excel",
    "powerpoint":        "powerpnt",
    "outlook":           "outlook",
    "notepad++":         "notepad++",
    "vlc":               "vlc",
    "steam":             "steam",
    "obs":               "obs64",
    "obs studio":        "obs64",
    "skype":             "skype",
    "brave":             "brave",
    "opera":             "opera",
}


def open_application(app_name: str) -> str:
    """
    Open a Windows application or program by name.
    Supported apps include: calculator, notepad, explorer, task manager,
    settings, paint, chrome, firefox, edge, spotify, discord, vs code,
    terminal, word, excel, powerpoint, outlook, steam, vlc, zoom, teams,
    slack, camera, photos, store, and many more.
    """
    key = app_name.lower().strip()
    target = _APP_MAP.get(key, app_name)
    try:
        if target.endswith(':'):
            os.startfile(target)
        else:
            subprocess.Popen(target, shell=True)
        return f"Opened {app_name}"
    except Exception as e:
        return f"Could not open {app_name}: {e}"


def open_file_explorer(path: str = "") -> str:
    """
    Open Windows File Explorer. Optionally provide a folder path to navigate directly.
    Leave path empty to open the default view.
    """
    try:
        if path and os.path.exists(path):
            subprocess.Popen(f'explorer.exe "{path}"', shell=True)
            return f"Opened File Explorer at {path}"
        subprocess.Popen('explorer.exe', shell=True)
        return "Opened File Explorer"
    except Exception as e:
        return f"Could not open File Explorer: {e}"


def take_screenshot() -> str:
    """Take a screenshot using the Windows Snipping Tool."""
    try:
        subprocess.Popen('snippingtool.exe /clip', shell=True)
        return "Snipping Tool launched for screenshot"
    except Exception as e:
        return f"Could not launch Snipping Tool: {e}"


# ── Web / Search / Maps ───────────────────────────────────────────────────────

def search_web(query: str) -> str:
    """Search Google for the given query and open results in the browser."""
    url = f"https://www.google.com/search?q={_qp(query)}"
    webbrowser.open(url)
    return f"Opened Google search for: {query}"


def search_youtube(query: str) -> str:
    """Search YouTube for a video or topic and open results in the browser."""
    url = f"https://www.youtube.com/results?search_query={_qp(query)}"
    webbrowser.open(url)
    return f"Opened YouTube search for: {query}"


def open_url(url: str) -> str:
    """Open any specific URL in the default web browser."""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    webbrowser.open(url)
    return f"Opened {url}"


def get_directions(destination: str, origin: str = "") -> str:
    """
    Open Google Maps turn-by-turn directions in the browser.
    destination: where to go (required).
    origin: starting point (optional; omit to use current location).
    """
    dest = _qp(destination)
    if origin.strip():
        orig = _qp(origin.strip())
        url  = f"https://www.google.com/maps/dir/{orig}/{dest}"
        desc = f"directions from {origin} to {destination}"
    else:
        url  = f"https://www.google.com/maps/dir//{dest}"
        desc = f"directions to {destination}"
    webbrowser.open(url)
    return f"Opened {desc} in your browser"


def search_maps(query: str) -> str:
    """Search Google Maps for a place, business, or address."""
    url = f"https://www.google.com/maps/search/{_qp(query)}"
    webbrowser.open(url)
    return f"Opened Google Maps search for: {query}"


# ── Reminders ─────────────────────────────────────────────────────────────────

def add_reminder(text: str, due_time: str = "") -> str:
    """
    Add a new reminder to the reminder list.
    text: what to be reminded about.
    due_time: optional ISO datetime string, e.g. '2026-05-18 15:00'. Always use YYYY-MM-DD HH:MM format.
    Do NOT pass '3:00 PM' style strings — use get_current_date to determine today's date if needed.
    """
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO reminders (text, due_time) VALUES (?, ?)",
                (text.strip(), due_time.strip() or None),
            )
            conn.commit()
        return f"Reminder added: '{text}'" + (f" at {due_time}" if due_time else "")
    except Exception as e:
        return f"Failed to add reminder: {e}"


def list_reminders() -> str:
    """List all active (not yet dismissed) reminders."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id, text, due_time FROM reminders WHERE done=0 ORDER BY id DESC LIMIT 15"
            ).fetchall()
        if not rows:
            return "No active reminders"
        return "\n".join(
            f"#{r['id']}: {r['text']}" + (f" [{r['due_time']}]" if r['due_time'] else "")
            for r in rows
        )
    except Exception as e:
        return f"Failed to list reminders: {e}"


def dismiss_reminder(reminder_id: int) -> str:
    """Mark a reminder as done and dismiss it by its numeric ID."""
    try:
        with get_conn() as conn:
            conn.execute("UPDATE reminders SET done=1 WHERE id=?", (reminder_id,))
            conn.commit()
        return f"Reminder #{reminder_id} dismissed"
    except Exception as e:
        return f"Failed to dismiss reminder: {e}"


# ── Tasks ─────────────────────────────────────────────────────────────────────

def add_task(text: str, priority: str = "normal") -> str:
    """
    Add a new task to the to-do list.
    text: task description.
    priority: 'low', 'normal', or 'high'. Defaults to 'normal'.
    """
    priority = priority.lower()
    if priority not in ("low", "normal", "high"):
        priority = "normal"
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO tasks (text, priority) VALUES (?, ?)",
                (text.strip(), priority),
            )
            conn.commit()
        return f"Task added: '{text}' (priority: {priority})"
    except Exception as e:
        return f"Failed to add task: {e}"


def list_tasks() -> str:
    """List all pending (not yet completed) tasks, sorted by priority."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id, text, priority FROM tasks WHERE done=0 "
                "ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, id"
            ).fetchall()
        if not rows:
            return "No pending tasks"
        flags = {"high": "🔴", "normal": "🟡", "low": "🟢"}
        return "\n".join(
            f"#{r['id']} {flags.get(r['priority'], '•')} {r['text']}"
            for r in rows
        )
    except Exception as e:
        return f"Failed to list tasks: {e}"


def complete_task(task_id: int) -> str:
    """Mark a task as complete and remove it from the active list by its numeric ID."""
    try:
        with get_conn() as conn:
            conn.execute("UPDATE tasks SET done=1 WHERE id=?", (task_id,))
            conn.commit()
        return f"Task #{task_id} marked complete"
    except Exception as e:
        return f"Failed to complete task: {e}"


# ── Vision tools ──────────────────────────────────────────────────────────────

def capture_and_analyze_screen(question: str = "Describe what you see on the screen.") -> str:
    """
    Take a screenshot of the entire screen and analyze it with Gemini Vision.
    Use this when the user asks you to look at their screen, read something visible,
    check an error, analyze a chart, or describe what is currently on display.
    question: what to ask about the screen, e.g. 'What error is shown?'
    """
    import config as _cfg
    max_attempts = max(1, len(getattr(_cfg, "GEMINI_API_KEYS", [None])))
    last_exc = None
    for _attempt in range(max_attempts):
        client, model = _get_vision_client()
        if client is None:
            return "Gemini Vision not available — no API key configured."
        try:
            from vision.analyzer import ScreenAnalyzer
            analyzer = ScreenAnalyzer(client, model)
            result = analyzer.analyze(question)
            _try_annotate_from_vision(question, result)
            return result
        except Exception as exc:
            last_exc = exc
            if _is_vision_rate_limit(exc):
                import logging; logging.getLogger(__name__).warning(
                    "Vision rate limited on attempt %d — rotating key...", _attempt + 1
                )
                if not _rotate_vision_key():
                    break
                continue
            return f"Screen analysis error: {exc}"
    return f"Screen analysis error: {last_exc}"


def read_text_on_screen() -> str:
    """
    Read and return all visible text currently on the screen using Gemini Vision.
    Useful for reading error messages, articles, chat messages, or any on-screen text.
    """
    return capture_and_analyze_screen(
        "Read and transcribe all visible text on the screen, grouped by section."
    )


def find_on_screen(description: str) -> str:
    """
    Find a specific UI element or object on the screen and return its location.
    description: what to look for, e.g. 'the Close button', 'the search bar', 'the error dialog'
    Returns a description of where it is on screen (or that it was not found).
    """
    import config as _cfg
    max_attempts = max(1, len(getattr(_cfg, "GEMINI_API_KEYS", [None])))
    last_exc = None
    for _attempt in range(max_attempts):
        client, model = _get_vision_client()
        if client is None:
            return "Gemini Vision not available — no API key configured."
        try:
            from vision.analyzer import ScreenAnalyzer
            analyzer = ScreenAnalyzer(client, model)
            info = analyzer.find_element(description)
            if info.get("found"):
                x, y, w, h = info["x"], info["y"], info["w"], info["h"]
                if _ann_overlay:
                    try:
                        _ann_overlay.highlight_region(x, y, w, h, label=description)
                    except Exception:
                        pass
                return f"Found '{description}' at ({x}, {y}), size {w}x{h}"
            return f"Could not find '{description}' on screen"
        except Exception as exc:
            last_exc = exc
            if _is_vision_rate_limit(exc):
                import logging; logging.getLogger(__name__).warning(
                    "Vision rate limited on attempt %d — rotating key...", _attempt + 1
                )
                if not _rotate_vision_key():
                    break
                continue
            return f"Screen element search error: {exc}"
    return f"Screen element search error: {last_exc}"


def _try_annotate_from_vision(question: str, result: str) -> None:
    """Best-effort: highlight screen region if bounding box JSON appears in vision result."""
    if _ann_overlay is None:
        return
    import re, json
    m = re.search(r'\{[^{}]+"x"\s*:\s*\d+[^{}]+\}', result)
    if m:
        try:
            info = json.loads(m.group())
            if all(k in info for k in ("x", "y", "w", "h")):
                _ann_overlay.highlight_region(
                    info["x"], info["y"], info["w"], info["h"], label=question[:40]
                )
        except Exception:
            pass


# ── Computer control tools ────────────────────────────────────────────────────

def click_screen(x: int, y: int) -> str:
    """
    Click the mouse at absolute screen coordinates (x, y).
    Use after find_on_screen to click a detected element.
    x: horizontal pixel position from left edge of screen.
    y: vertical pixel position from top edge of screen.
    """
    try:
        from automation.mouse_keyboard import click
        return click(x, y)
    except Exception as exc:
        return f"Click error: {exc}"


def type_on_screen(text: str) -> str:
    """
    Type text at the current cursor position, as if pressing keyboard keys.
    Make sure the correct input field is focused before calling this.
    text: the string to type.
    """
    try:
        from automation.mouse_keyboard import type_text
        return type_text(text)
    except Exception as exc:
        return f"Type error: {exc}"


def press_keyboard_key(key: str) -> str:
    """
    Press a single keyboard key.
    key: one of enter, tab, escape, backspace, delete, space, up, down, left, right,
         home, end, pageup, pagedown, f1-f12, win, or any letter/digit.
    """
    try:
        from automation.mouse_keyboard import press_key
        return press_key(key)
    except Exception as exc:
        return f"Key press error: {exc}"


def keyboard_shortcut(keys: str) -> str:
    """
    Press a keyboard shortcut with multiple keys held simultaneously.
    keys: keys separated by '+', e.g. 'ctrl+c', 'ctrl+alt+delete', 'win+d', 'alt+f4'.
    """
    try:
        from automation.mouse_keyboard import hotkey
        parts = [k.strip() for k in keys.split('+')]
        return hotkey(*parts)
    except Exception as exc:
        return f"Shortcut error: {exc}"


def open_tradingview_chart(symbol: str, timeframe: str) -> str:
    """
    Open TradingView in the browser with a specific symbol and timeframe.
    symbol: trading pair or ticker, e.g. 'XAUUSD', 'EURUSD', 'BTCUSDT', 'AAPL', 'SPX'.
    timeframe: chart interval — '1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'.
    After calling this, you can use capture_and_analyze_screen to analyze the chart.
    """
    try:
        from automation.browser import open_tradingview_chart as _tv
        return _tv(symbol, timeframe)
    except Exception as exc:
        return f"TradingView error: {exc}"


def open_browser_to(url: str) -> str:
    """
    Open a URL in the Playwright browser (more reliable than the system browser for automation).
    url: full web address, e.g. 'https://finance.yahoo.com' or 'tradingview.com'.
    """
    try:
        from automation.browser import open_browser_url
        return open_browser_url(url)
    except Exception as exc:
        return f"Browser navigation error: {exc}"


# ── Volume & Media ────────────────────────────────────────────────────────────

def get_volume() -> str:
    """Get the current system master volume level as a percentage and mute state."""
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        level  = int(round(volume.GetMasterVolumeLevelScalar() * 100))
        muted  = bool(volume.GetMute())
        return f"Volume is at {level}%" + (" (muted)" if muted else "")
    except Exception as exc:
        return f"Volume error: {exc}"


def set_volume(level: int) -> str:
    """
    Set the system master volume.
    level: integer from 0 (silent) to 100 (maximum).
    """
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(max(0.0, min(1.0, level / 100.0)), None)
        return f"Volume set to {level}%"
    except Exception as exc:
        return f"Set volume error: {exc}"


def mute_volume() -> str:
    """Mute the system audio output."""
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        cast(interface, POINTER(IAudioEndpointVolume)).SetMute(1, None)
        return "Audio muted"
    except Exception as exc:
        return f"Mute error: {exc}"


def unmute_volume() -> str:
    """Unmute the system audio output."""
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        cast(interface, POINTER(IAudioEndpointVolume)).SetMute(0, None)
        return "Audio unmuted"
    except Exception as exc:
        return f"Unmute error: {exc}"


def media_play_pause() -> str:
    """Toggle play/pause for the currently active media player."""
    try:
        import keyboard as kb
        kb.send("play/pause media")
        return "Media play/pause toggled"
    except Exception as exc:
        return f"Media control error: {exc}"


def media_next_track() -> str:
    """Skip to the next track in the active media player."""
    try:
        import keyboard as kb
        kb.send("next track")
        return "Skipped to next track"
    except Exception as exc:
        return f"Media control error: {exc}"


def media_previous_track() -> str:
    """Go back to the previous track in the active media player."""
    try:
        import keyboard as kb
        kb.send("previous track")
        return "Went to previous track"
    except Exception as exc:
        return f"Media control error: {exc}"


def media_stop() -> str:
    """Stop media playback in the active media player."""
    try:
        import keyboard as kb
        kb.send("stop media")
        return "Media stopped"
    except Exception as exc:
        return f"Media control error: {exc}"


# ── Window Management ─────────────────────────────────────────────────────────

def list_open_windows() -> str:
    """List all currently visible open window titles on the desktop."""
    try:
        import win32gui
        windows: list[str] = []
        def _cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                t = win32gui.GetWindowText(hwnd)
                if t.strip():
                    windows.append(t)
        win32gui.EnumWindows(_cb, None)
        return ", ".join(windows[:25]) if windows else "No windows found"
    except Exception as exc:
        return f"Window list error: {exc}"


def focus_window(title: str) -> str:
    """
    Bring a window to the foreground and give it focus.
    title: partial window title to search for (case-insensitive).
    """
    try:
        import win32gui, win32con
        title_lower = title.lower()
        found = None
        def _cb(hwnd, _):
            nonlocal found
            if win32gui.IsWindowVisible(hwnd) and title_lower in win32gui.GetWindowText(hwnd).lower():
                found = hwnd
        win32gui.EnumWindows(_cb, None)
        if found:
            win32gui.ShowWindow(found, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(found)
            return f"Focused '{win32gui.GetWindowText(found)}'"
        return f"No window matching '{title}' found"
    except Exception as exc:
        return f"Focus window error: {exc}"


def close_window(title: str) -> str:
    """
    Close a window by its title.
    title: partial window title (case-insensitive).
    """
    try:
        import win32gui, win32con
        title_lower = title.lower()
        found = None
        def _cb(hwnd, _):
            nonlocal found
            if win32gui.IsWindowVisible(hwnd) and title_lower in win32gui.GetWindowText(hwnd).lower():
                found = hwnd
        win32gui.EnumWindows(_cb, None)
        if found:
            name = win32gui.GetWindowText(found)
            win32gui.PostMessage(found, win32con.WM_CLOSE, 0, 0)
            return f"Closed '{name}'"
        return f"No window matching '{title}' found"
    except Exception as exc:
        return f"Close window error: {exc}"


def minimize_window(title: str) -> str:
    """
    Minimize a window by its title.
    title: partial window title (case-insensitive).
    """
    try:
        import win32gui, win32con
        title_lower = title.lower()
        found = None
        def _cb(hwnd, _):
            nonlocal found
            if win32gui.IsWindowVisible(hwnd) and title_lower in win32gui.GetWindowText(hwnd).lower():
                found = hwnd
        win32gui.EnumWindows(_cb, None)
        if found:
            name = win32gui.GetWindowText(found)
            win32gui.ShowWindow(found, win32con.SW_MINIMIZE)
            return f"Minimized '{name}'"
        return f"No window matching '{title}' found"
    except Exception as exc:
        return f"Minimize error: {exc}"


def maximize_window(title: str) -> str:
    """
    Maximize a window by its title.
    title: partial window title (case-insensitive).
    """
    try:
        import win32gui, win32con
        title_lower = title.lower()
        found = None
        def _cb(hwnd, _):
            nonlocal found
            if win32gui.IsWindowVisible(hwnd) and title_lower in win32gui.GetWindowText(hwnd).lower():
                found = hwnd
        win32gui.EnumWindows(_cb, None)
        if found:
            name = win32gui.GetWindowText(found)
            win32gui.ShowWindow(found, win32con.SW_MAXIMIZE)
            return f"Maximized '{name}'"
        return f"No window matching '{title}' found"
    except Exception as exc:
        return f"Maximize error: {exc}"


def minimize_all_windows() -> str:
    """Minimize all open windows and show the desktop (Win+D)."""
    try:
        import keyboard as kb
        kb.send("win+d")
        return "All windows minimized — desktop shown"
    except Exception as exc:
        return f"Minimize all error: {exc}"


# ── File Operations ───────────────────────────────────────────────────────────

def read_file_contents(path: str) -> str:
    """
    Read and return the text contents of a file.
    path: absolute or relative file path (supports ~ and %VARS%).
    Returns up to 8000 characters.
    """
    try:
        path = os.path.expandvars(os.path.expanduser(path))
        if not os.path.isfile(path):
            return f"File not found: {path}"
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(8000)
        return content or "(empty file)"
    except Exception as exc:
        return f"Read file error: {exc}"


def open_file(path: str) -> str:
    """
    Open a file or folder with its default application (PDF, image, document, etc.).
    path: absolute path to the file or folder.
    """
    try:
        path = os.path.expandvars(os.path.expanduser(path))
        os.startfile(path)
        return f"Opened: {path}"
    except Exception as exc:
        return f"Open file error: {exc}"


def create_file(path: str, content: str = "") -> str:
    """
    Create a new file (or overwrite an existing one) with the given text content.
    path: file path to create.
    content: text to write into the file (can be empty).
    """
    try:
        path = os.path.expandvars(os.path.expanduser(path))
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File created: {path}"
    except Exception as exc:
        return f"Create file error: {exc}"


def delete_file(path: str) -> str:
    """
    Delete a file or folder permanently.
    path: path to the file or folder to delete.
    Only call this after confirming with the user.
    """
    try:
        import shutil
        path = os.path.expandvars(os.path.expanduser(path))
        if os.path.isfile(path):
            os.remove(path)
            return f"Deleted file: {path}"
        elif os.path.isdir(path):
            shutil.rmtree(path)
            return f"Deleted folder: {path}"
        return f"Path not found: {path}"
    except Exception as exc:
        return f"Delete error: {exc}"


def create_folder(path: str) -> str:
    """
    Create a folder and any necessary parent folders.
    path: directory path to create.
    """
    try:
        path = os.path.expandvars(os.path.expanduser(path))
        os.makedirs(path, exist_ok=True)
        return f"Folder created: {path}"
    except Exception as exc:
        return f"Create folder error: {exc}"


def move_file(source: str, destination: str) -> str:
    """
    Move or rename a file or folder.
    source: current path.
    destination: new path or target directory.
    """
    try:
        import shutil
        src = os.path.expandvars(os.path.expanduser(source))
        dst = os.path.expandvars(os.path.expanduser(destination))
        shutil.move(src, dst)
        return f"Moved '{src}' → '{dst}'"
    except Exception as exc:
        return f"Move error: {exc}"


def list_directory(path: str = "") -> str:
    """
    List files and folders in a directory.
    path: directory to list — defaults to the Desktop if empty.
    """
    try:
        if not path:
            path = os.path.join(os.path.expanduser("~"), "Desktop")
        path = os.path.expandvars(os.path.expanduser(path))
        if not os.path.isdir(path):
            return f"Directory not found: {path}"
        entries = os.listdir(path)
        if not entries:
            return f"{path} is empty"
        folders = sorted(e + "/" for e in entries if os.path.isdir(os.path.join(path, e)))
        files   = sorted(e for e in entries if os.path.isfile(os.path.join(path, e)))
        return f"{path}:\n" + "\n".join(folders + files)
    except Exception as exc:
        return f"List directory error: {exc}"


def search_files(name: str, directory: str = "") -> str:
    """
    Search for files whose name contains the given string.
    name: filename or partial name (case-insensitive).
    directory: directory to search in — defaults to user home folder.
    Returns up to 20 matching paths.
    """
    try:
        if not directory:
            directory = os.path.expanduser("~")
        directory = os.path.expandvars(os.path.expanduser(directory))
        name_lower = name.lower()
        _skip = {"AppData", "node_modules", "__pycache__", ".git", "Windows"}
        matches: list[str] = []
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in _skip and not d.startswith(".")]
            for f in files:
                if name_lower in f.lower():
                    matches.append(os.path.join(root, f))
                    if len(matches) >= 20:
                        return "\n".join(matches)
        return "\n".join(matches) if matches else f"No files matching '{name}' found in {directory}"
    except Exception as exc:
        return f"Search error: {exc}"


def download_file(url: str, destination: str = "") -> str:
    """
    Download a file from a URL and save it locally.
    url: direct download URL.
    destination: local path to save to — defaults to Downloads folder.
    """
    if not HAS_REQUESTS:
        return "requests library not available"
    try:
        if not destination:
            destination = os.path.join(os.path.expanduser("~"), "Downloads",
                                       os.path.basename(url.split("?")[0]) or "download")
        destination = os.path.expandvars(os.path.expanduser(destination))
        os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
        with req_lib.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(destination, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return f"Downloaded to: {destination}"
    except Exception as exc:
        return f"Download error: {exc}"


# ── Process Management ────────────────────────────────────────────────────────

def list_running_processes() -> str:
    """List the top 10 running processes sorted by CPU usage, with name, PID, CPU%, and RAM%."""
    if not HAS_PSUTIL:
        return "psutil not available"
    try:
        import time as _time
        # Two-pass for accurate cpu_percent
        procs = []
        for p in psutil.process_iter(["name", "pid", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        _time.sleep(0.15)
        procs.clear()
        for p in psutil.process_iter(["name", "pid", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
        lines = [
            f"{p['name']} (PID {p['pid']}) — CPU: {p['cpu_percent']:.1f}%,"
            f" RAM: {(p['memory_percent'] or 0):.1f}%"
            for p in procs[:10]
        ]
        return "\n".join(lines) or "No processes found"
    except Exception as exc:
        return f"Process list error: {exc}"


def kill_process(name: str) -> str:
    """
    Kill a running process by name.
    name: process name or partial name, e.g. 'notepad.exe', 'chrome'.
    Only call after confirming with the user.
    """
    if not HAS_PSUTIL:
        return "psutil not available"
    try:
        killed: list[str] = []
        for p in psutil.process_iter(["name", "pid"]):
            try:
                if name.lower() in (p.info["name"] or "").lower():
                    p.kill()
                    killed.append(f"{p.info['name']} (PID {p.info['pid']})")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return f"Killed: {', '.join(killed)}" if killed else f"No process matching '{name}' found"
    except Exception as exc:
        return f"Kill process error: {exc}"


def get_process_info(name: str) -> str:
    """
    Get CPU%, RAM%, and PID for a specific running process.
    name: process name or partial name, e.g. 'chrome', 'python'.
    """
    if not HAS_PSUTIL:
        return "psutil not available"
    try:
        results: list[str] = []
        for p in psutil.process_iter(["name", "pid", "cpu_percent", "memory_percent", "status"]):
            try:
                if name.lower() in (p.info["name"] or "").lower():
                    results.append(
                        f"{p.info['name']} (PID {p.info['pid']}) — "
                        f"CPU: {p.info['cpu_percent']:.1f}%, "
                        f"RAM: {(p.info['memory_percent'] or 0):.1f}%, "
                        f"Status: {p.info['status']}"
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return "\n".join(results) if results else f"No process matching '{name}' found"
    except Exception as exc:
        return f"Process info error: {exc}"


# ── Power & System Control ────────────────────────────────────────────────────

def lock_screen() -> str:
    """Lock the Windows user session immediately."""
    try:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
        return "Screen locked"
    except Exception as exc:
        return f"Lock screen error: {exc}"


def sleep_computer() -> str:
    """Put the computer into sleep mode."""
    try:
        subprocess.Popen(
            ["rundll32.exe", "powrprof.dll,SetSuspendState", "0", "1", "0"]
        )
        return "Going to sleep, Sir"
    except Exception as exc:
        return f"Sleep error: {exc}"


def restart_computer() -> str:
    """
    Restart the computer after a 10-second delay.
    Only call this after the user has explicitly confirmed they want to restart.
    """
    try:
        subprocess.Popen(
            ["shutdown", "/r", "/t", "10", "/c", "F.R.I.D.A.Y. initiated restart"]
        )
        return "Restarting in 10 seconds. Say 'cancel shutdown' to abort."
    except Exception as exc:
        return f"Restart error: {exc}"


def shutdown_computer() -> str:
    """
    Shut down the computer after a 10-second delay.
    Only call this after the user has explicitly confirmed they want to shut down.
    """
    try:
        subprocess.Popen(
            ["shutdown", "/s", "/t", "10", "/c", "F.R.I.D.A.Y. initiated shutdown"]
        )
        return "Shutting down in 10 seconds. Say 'cancel shutdown' to abort."
    except Exception as exc:
        return f"Shutdown error: {exc}"


def cancel_shutdown() -> str:
    """Cancel a pending scheduled shutdown or restart."""
    try:
        subprocess.run(["shutdown", "/a"], capture_output=True)
        return "Shutdown/restart cancelled"
    except Exception as exc:
        return f"Cancel shutdown error: {exc}"


def get_network_info() -> str:
    """Get the current IP address, hostname, and active network adapter information."""
    try:
        import socket
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        result   = subprocess.run(
            ["ipconfig"], capture_output=True, text=True, timeout=8
        )
        # Extract only the useful adapter blocks (skip empty lines)
        lines    = [l for l in result.stdout.splitlines() if l.strip()]
        trimmed  = "\n".join(lines[:40])
        return f"Hostname: {hostname}\nLocal IP: {local_ip}\n\n{trimmed}"
    except Exception as exc:
        return f"Network info error: {exc}"


def set_brightness(level: int) -> str:
    """
    Set the screen brightness.
    level: integer from 0 to 100.
    Only works on laptops with a built-in display managed by Windows WMI.
    """
    try:
        level = max(0, min(100, level))
        cmd = (
            f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
            f".WmiSetBrightness(1,{level})"
        )
        subprocess.run(["powershell", "-Command", cmd], capture_output=True, timeout=8)
        return f"Brightness set to {level}%"
    except Exception as exc:
        return f"Brightness error: {exc}"


# ── Clipboard ─────────────────────────────────────────────────────────────────

def read_clipboard() -> str:
    """Read and return the current text content of the clipboard."""
    try:
        import pyperclip
        text = pyperclip.paste()
        if not text:
            return "Clipboard is empty"
        return text[:3000]
    except Exception as exc:
        return f"Clipboard read error: {exc}"


def write_clipboard(text: str) -> str:
    """
    Write text to the clipboard so it can be pasted anywhere.
    text: the content to place on the clipboard.
    """
    try:
        import pyperclip
        pyperclip.copy(text)
        preview = text[:80] + ("..." if len(text) > 80 else "")
        return f"Copied to clipboard: {preview}"
    except Exception as exc:
        return f"Clipboard write error: {exc}"


# ── Notes ─────────────────────────────────────────────────────────────────────

def take_note(title: str, content: str) -> str:
    """
    Save a note to persistent storage.
    title: short label for the note.
    content: the body of the note.
    """
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO notes (title, content) VALUES (?, ?)", (title, content)
            )
            conn.commit()
        return f"Note '{title}' saved"
    except Exception as exc:
        return f"Note save error: {exc}"


def list_notes() -> str:
    """List the 10 most recent saved notes (title and creation time)."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id, title, created_at FROM notes ORDER BY id DESC LIMIT 10"
            ).fetchall()
        if not rows:
            return "No notes saved yet"
        return "\n".join(f"#{r['id']} [{r['created_at']}] {r['title']}" for r in rows)
    except Exception as exc:
        return f"List notes error: {exc}"


def read_note(title: str) -> str:
    """
    Retrieve the content of a saved note by its title.
    title: partial title to search for (case-insensitive).
    """
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT title, content, created_at FROM notes WHERE lower(title) LIKE ? ORDER BY id DESC LIMIT 1",
                (f"%{title.lower()}%",)
            ).fetchone()
        if row:
            return f"[{row['title']}] {row['created_at']}\n\n{row['content']}"
        return f"No note matching '{title}' found"
    except Exception as exc:
        return f"Read note error: {exc}"


def delete_note(note_id: int) -> str:
    """
    Delete a saved note by its numeric ID (visible from list_notes).
    note_id: the ID number of the note to delete.
    """
    try:
        with get_conn() as conn:
            conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
            conn.commit()
        return f"Note #{note_id} deleted"
    except Exception as exc:
        return f"Delete note error: {exc}"


# ── Persistent Memory ─────────────────────────────────────────────────────

def remember_fact(fact: str) -> str:
    """
    Save an important fact about the user to persistent memory.
    fact: a concise statement, e.g. 'User prefers Celsius' or 'User\'s name is Alex'.
    Call this when the user shares personal details, preferences, or asks you to remember
    something. Facts persist across sessions and are injected at the start of each new chat.
    Never store passwords, API keys, or other sensitive credentials.
    """
    try:
        with get_conn() as conn:
            conn.execute("INSERT INTO memories (content) VALUES (?)", (fact,))
            conn.commit()
        return f"Remembered: {fact}"
    except Exception as exc:
        return f"Memory save error: {exc}"


def forget_fact(fact_id: int) -> str:
    """
    Remove a persistent memory by its numeric ID.
    fact_id: the ID shown in the memory list injected at the start of this session.
    Call this when information is outdated or the user asks you to forget something.
    """
    try:
        with get_conn() as conn:
            result = conn.execute("DELETE FROM memories WHERE id=?", (fact_id,))
            conn.commit()
        if result.rowcount:
            return f"Memory #{fact_id} forgotten"
        return f"No memory with ID #{fact_id} found"
    except Exception as exc:
        return f"Memory delete error: {exc}"


# ── Shell Commands ────────────────────────────────────────────────────────────

def run_shell_command(command: str) -> str:
    """
    Execute a Windows shell command and return its output.
    command: the command to run, e.g. 'ipconfig', 'dir C:\\Users', 'ping google.com -n 2'.
    Output is capped at 3000 characters. Confirm with the user before running destructive commands.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = (result.stdout + result.stderr).strip()
        return output[:3000] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Command timed out (15 second limit)"
    except Exception as exc:
        return f"Shell command error: {exc}"


# ── Stock / Crypto Watchlist ──────────────────────────────────────────────────

def add_to_watchlist(symbol: str, asset_type: str = "crypto") -> str:
    """
    Add a stock or cryptocurrency to the price-alert watchlist.
    symbol: ticker symbol, e.g. 'BTC', 'ETH', 'AAPL', 'TSLA'.
    asset_type: 'crypto' for cryptocurrencies, 'stock' for equities.
    Friday will alert you when the price moves significantly.
    """
    symbol = symbol.upper().strip()
    asset_type = asset_type.lower().strip()
    if asset_type not in ("crypto", "stock"):
        asset_type = "crypto"
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO stock_watchlist (symbol, asset_type, active) VALUES (?, ?, 1)",
                (symbol, asset_type),
            )
            conn.commit()
        return f"Added {symbol} ({asset_type}) to your watchlist. I'll alert you on big moves."
    except Exception as exc:
        return f"Watchlist add error: {exc}"


def remove_from_watchlist(symbol: str) -> str:
    """
    Remove a symbol from the price-alert watchlist.
    symbol: ticker symbol to remove, e.g. 'BTC', 'AAPL'.
    """
    symbol = symbol.upper().strip()
    try:
        with get_conn() as conn:
            conn.execute("UPDATE stock_watchlist SET active = 0 WHERE symbol = ?", (symbol,))
            conn.commit()
        return f"Removed {symbol} from your watchlist."
    except Exception as exc:
        return f"Watchlist remove error: {exc}"


def list_watchlist() -> str:
    """List all symbols currently on your price-alert watchlist with their latest prices."""
    try:
        from services.monitor import _fetch_price, _get_watchlist
        items = _get_watchlist()
        if not items:
            return "Watchlist is empty. Add symbols with 'add BTC to my watchlist'."
        lines = []
        for item in items:
            price = _fetch_price(item["symbol"], item["asset_type"])
            price_str = f"${price:,.2f}" if price else "price unavailable"
            lines.append(f"{item['symbol']} ({item['asset_type']}) — {price_str}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Watchlist list error: {exc}"


def get_price(symbol: str, asset_type: str = "crypto") -> str:
    """
    Get the current price of a cryptocurrency or stock.
    symbol: ticker symbol, e.g. 'BTC', 'ETH', 'AAPL', 'TSLA', 'SPY'.
    asset_type: 'crypto' or 'stock'.
    """
    symbol = symbol.upper().strip()
    try:
        from services.monitor import _fetch_price
        price = _fetch_price(symbol, asset_type.lower())
        if price:
            return f"{symbol} is currently at ${price:,.2f}"
        return f"Could not fetch price for {symbol}. Check the symbol and try again."
    except Exception as exc:
        return f"Price fetch error: {exc}"


# ── Code Execution ────────────────────────────────────────────────────────────

def execute_python_code(code: str, description: str = "") -> str:
    """
    Write and execute a Python script, returning its output.
    Use this to perform calculations, data processing, file operations,
    automation scripts, or any task that benefits from running code.
    For complex multi-file projects, call this multiple times to build
    and iterate. Friday will write the code, run it, and report results.

    code: valid Python source code to execute.
    description: brief description of what this code does (for logging).

    The code runs with a 60-second timeout. stdout and stderr are captured
    and returned. The working directory is the user's home folder.
    """
    import tempfile
    import subprocess as _sp

    if not code.strip():
        return "No code provided."

    desc_log = description or "user-requested script"
    logger = __import__("logging").getLogger(__name__)
    logger.info("Executing code: %s", desc_log)

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        result = _sp.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=os.path.expanduser("~"),
        )
        output = (result.stdout + result.stderr).strip()
        exit_code = result.returncode

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        if exit_code == 0:
            return output[:4000] if output else "(script completed with no output)"
        else:
            return f"Script exited with code {exit_code}:\n{output[:4000]}"

    except _sp.TimeoutExpired:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        return "Script timed out after 60 seconds."
    except Exception as exc:
        return f"Code execution error: {exc}"


def execute_shell_script(script: str, shell: str = "powershell") -> str:
    """
    Write and execute a shell script (PowerShell or CMD batch).
    Use this for Windows automation, system administration, or
    tasks that are cleaner in shell than in Python.

    script: the shell script content to execute.
    shell: 'powershell' (default) or 'cmd'.
    Returns stdout + stderr, capped at 4000 characters.
    """
    import tempfile
    import subprocess as _sp

    if not script.strip():
        return "No script provided."

    try:
        if shell == "cmd":
            suffix = ".bat"
            cmd = ["cmd", "/c"]
        else:
            suffix = ".ps1"
            cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File"]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(script)
            tmp_path = tmp.name

        result = _sp.run(
            cmd + [tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.path.expanduser("~"),
        )
        output = (result.stdout + result.stderr).strip()

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        return output[:4000] if output else "(no output)"

    except _sp.TimeoutExpired:
        return "Script timed out after 30 seconds."
    except Exception as exc:
        return f"Shell script error: {exc}"


# ── Document Intelligence ─────────────────────────────────────────────────────

def analyze_document(path: str, question: str = "Summarize this document.") -> str:
    """
    Read and analyze any document: PDF, Word (.docx), plain text, or image.
    Extracts the text content and sends it to Gemini for intelligent analysis.
    Use this when the user wants to: summarize a contract, read a report,
    extract key points from a PDF, analyze a Word document, or ask questions
    about any file's content.

    path: absolute path to the document file.
    question: what to ask about the document, e.g. 'What are the key terms?'
              Defaults to a full summary.
    """
    import pathlib

    path = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isfile(path):
        return f"File not found: {path}"

    suffix = pathlib.Path(path).suffix.lower()
    text   = ""

    try:
        # ── PDF ─────────────────────────────────────────────────────────
        if suffix == ".pdf":
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(path)
                pages = [page.get_text() for page in doc]
                text = "\n\n".join(pages)
                doc.close()
            except ImportError:
                return (
                    "PyMuPDF not installed — run: pip install pymupdf\n"
                    "Then retry."
                )

        # ── Word (.docx) ──────────────────────────────────────────────
        elif suffix == ".docx":
            try:
                import docx
                doc = docx.Document(path)
                text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            except ImportError:
                return (
                    "python-docx not installed — run: pip install python-docx\n"
                    "Then retry."
                )

        # ── Legacy Word (.doc) — binary format, not supported by python-docx ──
        elif suffix == ".doc":
            return (
                f"Legacy .doc format is not supported directly, Sir. "
                f"Please open '{os.path.basename(path)}' in Word and save it as .docx, "
                f"then ask me to analyze it again."
            )

        # ── Plain text / code ─────────────────────────────────────────
        elif suffix in (".txt", ".md", ".py", ".js", ".ts", ".json", ".csv",
                        ".html", ".xml", ".yaml", ".yml", ".log"):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read(40000)

        # ── Image — use Gemini Vision ─────────────────────────────────
        elif suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
            try:
                from PIL import Image as _Image
                import io
                img  = _Image.open(path)
                buf  = io.BytesIO()
                img.save(buf, format="PNG")
                img_bytes = buf.getvalue()

                client, model = _get_vision_client()
                if client is None:
                    return "Gemini Vision not available."

                from google.genai import types as _gt
                response = client.models.generate_content(
                    model=model,
                    contents=[
                        question,
                        _gt.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                    ],
                )
                return response.text.strip()
            except Exception as exc:
                return f"Image analysis error: {exc}"

        else:
            return f"Unsupported file type: {suffix}"

        if not text.strip():
            return "Document appears to be empty or could not be read."

        # ── Send extracted text to Gemini ─────────────────────────────
        client, model = _get_vision_client()
        if client is None:
            return f"Gemini not available. Extracted text (first 2000 chars):\n{text[:2000]}"

        # Cap at 30 000 chars to stay within token limits
        capped = text[:30000]
        prompt = (
            f"The following is the content of a document ({os.path.basename(path)}):\n\n"
            f"{capped}\n\n"
            f"---\n{question}"
        )
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text.strip()

    except Exception as exc:
        return f"Document analysis error: {exc}"


# ── Web Research ──────────────────────────────────────────────────────────────

def fetch_webpage_text(url: str, question: str = "") -> str:
    """
    Fetch the text content of a web page and optionally answer a question about it.
    url: full URL to fetch, e.g. 'https://en.wikipedia.org/wiki/Python'.
    question: optional question to answer based on the page content.
    Use this for research, reading articles, checking documentation, and web scraping.
    """
    if not HAS_REQUESTS:
        return "requests library not available."
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        try:
            resp = req_lib.get(url, headers=headers, timeout=12)
        except Exception:
            import warnings as _w
            with _w.catch_warnings():
                _w.simplefilter("ignore")
                resp = req_lib.get(url, headers=headers, timeout=12, verify=False)
        resp.raise_for_status()

        # Strip HTML tags
        html = resp.text
        try:
            from html.parser import HTMLParser

            class _StripHTML(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.parts: list[str] = []
                    self._skip = False

                def handle_starttag(self, tag, attrs):
                    if tag in ("script", "style", "nav", "footer", "header"):
                        self._skip = True

                def handle_endtag(self, tag):
                    if tag in ("script", "style", "nav", "footer", "header"):
                        self._skip = False

                def handle_data(self, data):
                    if not self._skip and data.strip():
                        self.parts.append(data.strip())

            parser = _StripHTML()
            parser.feed(html)
            text = " ".join(parser.parts)
        except Exception:
            import re
            text = re.sub(r"<[^>]+>", " ", html)

        # Collapse whitespace
        import re
        text = re.sub(r"\s+", " ", text).strip()[:20000]

        if not question:
            return text[:5000]

        # Ask Gemini about the page
        client, model = _get_vision_client()
        if client is None:
            return text[:5000]

        prompt = (
            f"Based on this web page content from {url}:\n\n"
            f"{text[:15000]}\n\n"
            f"---\nAnswer this question: {question}"
        )
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text.strip()

    except Exception as exc:
        return f"Web fetch error: {exc}"


def research_topic(goal: str, save_report: bool = False) -> str:
    """
    Autonomously research a topic by searching the web and synthesizing findings.
    Searches multiple sources, reads key pages, and produces a comprehensive report.
    Use for: 'Research the best laptops under $1000', 'Compare Python vs JavaScript',
    'What are the latest developments in AI?', 'Find me the top 3 X for Y'.

    goal: the research question or goal.
    save_report: if True, save the report to a file on the Desktop.
    """
    if not HAS_REQUESTS:
        return "requests library not available for web research."

    import re

    results_text: list[str] = []

    try:
        # Step 1: Get result URLs and snippets via duckduckgo_search package
        clean_urls: list[str] = []
        snippets: dict[str, str] = {}

        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                ddg_results = list(ddgs.text(goal, max_results=6))
            for r in ddg_results:
                url = r.get("href", "")
                if url:
                    clean_urls.append(url)
                    # Keep snippet as fallback if page fetch fails later
                    snippets[url] = f"{r.get('title', '')}: {r.get('body', '')}"
        except Exception:
            # Fallback: SearXNG public JSON API (no key required)
            _sx_headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                )
            }
            for _sx_base in [
                "https://searx.be",
                "https://search.sapti.me",
                "https://searx.tiekoetter.com",
            ]:
                try:
                    _sx_resp = req_lib.get(
                        f"{_sx_base}/search",
                        params={"q": goal, "format": "json", "language": "en"},
                        headers=_sx_headers,
                        timeout=10,
                    )
                    if _sx_resp.status_code == 200:
                        _sx_data = _sx_resp.json()
                        for _r in _sx_data.get("results", [])[:6]:
                            _u = _r.get("url", "")
                            if _u:
                                clean_urls.append(_u)
                                snippets[_u] = (
                                    f"{_r.get('title', '')}: {_r.get('content', '')}"
                                )
                        if clean_urls:
                            break
                except Exception:
                    continue

        if not clean_urls:
            return f"Could not find relevant sources for: {goal}"

        # Step 2: Fetch all pages in parallel — 6 threads, 20s total cap
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch_one(url: str):
            try:
                content = fetch_webpage_text(url)
                if content and len(content) > 200 and not content.startswith("Web fetch error"):
                    return url, content[:3500]
            except Exception:
                pass
            return url, None

        with ThreadPoolExecutor(max_workers=6) as _pool:
            _futures = {_pool.submit(_fetch_one, u): u for u in clean_urls}
            for _fut in as_completed(_futures, timeout=20):
                try:
                    _url, _content = _fut.result()
                    if _content:
                        results_text.append(f"Source: {_url}\n{_content}")
                    elif snippets.get(_url):
                        results_text.append(f"Source: {_url}\n{snippets[_url]}")
                except Exception:
                    pass

        if not results_text:
            return "Could not retrieve content from any sources."

        combined = "\n\n---\n\n".join(results_text)

        # Step 3: Ask Gemini to synthesize
        client, model = _get_vision_client()
        if client is None:
            return "Gemini not available for synthesis."

        prompt = (
            f"You are conducting research on behalf of the user. "
            f"Research goal: {goal}\n\n"
            f"Here is the content gathered from {len(results_text)} web sources:\n\n"
            f"{combined[:25000]}\n\n"
            f"---\n"
            f"Write a comprehensive, well-structured research report answering the goal. "
            f"Include key findings, comparisons, recommendations, and cite sources where relevant. "
            f"Be specific, practical, and useful."
        )
        response = client.models.generate_content(model=model, contents=prompt)
        report   = response.text.strip()

        if save_report:
            try:
                import datetime
                filename  = re.sub(r"[^\w\s-]", "", goal)[:40].strip().replace(" ", "_")
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
                filepath  = os.path.join(
                    os.path.expanduser("~"), "Desktop",
                    f"FRIDAY_Research_{filename}_{timestamp}.txt"
                )
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(f"Research Goal: {goal}\n")
                    f.write(f"Date: {datetime.datetime.now().strftime('%B %d, %Y %I:%M %p')}\n")
                    f.write(f"Sources consulted: {len(results_text)}\n\n")
                    f.write(report)
                return report + f"\n\n[Report saved to Desktop: {os.path.basename(filepath)}]"
            except Exception as exc:
                return report + f"\n\n(Could not save report: {exc})"

        return report

    except Exception as exc:
        return f"Research error: {exc}"


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOL_MAP: dict = {fn.__name__: fn for fn in [
    get_current_time,
    get_current_date,
    get_battery_status,
    get_cpu_usage,
    get_memory_usage,
    get_disk_usage,
    get_system_info,
    get_weather,
    open_application,
    open_file_explorer,
    take_screenshot,
    search_web,
    search_youtube,
    open_url,
    get_directions,
    search_maps,
    add_reminder,
    list_reminders,
    dismiss_reminder,
    add_task,
    list_tasks,
    complete_task,
    # Vision
    capture_and_analyze_screen,
    read_text_on_screen,
    find_on_screen,
    # Computer control
    click_screen,
    type_on_screen,
    press_keyboard_key,
    keyboard_shortcut,
    open_tradingview_chart,
    open_browser_to,
    # Volume & media
    get_volume,
    set_volume,
    mute_volume,
    unmute_volume,
    media_play_pause,
    media_next_track,
    media_previous_track,
    media_stop,
    # Window management
    list_open_windows,
    focus_window,
    close_window,
    minimize_window,
    maximize_window,
    minimize_all_windows,
    # File operations
    read_file_contents,
    open_file,
    create_file,
    delete_file,
    create_folder,
    move_file,
    list_directory,
    search_files,
    download_file,
    # Process management
    list_running_processes,
    kill_process,
    get_process_info,
    # Power & system
    lock_screen,
    sleep_computer,
    restart_computer,
    shutdown_computer,
    cancel_shutdown,
    get_network_info,
    set_brightness,
    # Clipboard
    read_clipboard,
    write_clipboard,
    # Notes
    take_note,
    list_notes,
    read_note,
    delete_note,
    # Memory
    remember_fact,
    forget_fact,
    # Shell
    run_shell_command,
    # Stock / Crypto watchlist
    add_to_watchlist,
    remove_from_watchlist,
    list_watchlist,
    get_price,
    # Code execution
    execute_python_code,
    execute_shell_script,
    # Document intelligence
    analyze_document,
    # Web research
    fetch_webpage_text,
    research_topic,
]}

ALL_TOOLS: list = list(TOOL_MAP.values())

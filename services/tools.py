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
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    webbrowser.open(url)
    return f"Opened Google search for: {query}"


def search_youtube(query: str) -> str:
    """Search YouTube for a video or topic and open results in the browser."""
    url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
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
    dest = destination.replace(' ', '+')
    if origin.strip():
        orig = origin.strip().replace(' ', '+')
        url  = f"https://www.google.com/maps/dir/{orig}/{dest}"
        desc = f"directions from {origin} to {destination}"
    else:
        url  = f"https://www.google.com/maps/dir//{dest}"
        desc = f"directions to {destination}"
    webbrowser.open(url)
    return f"Opened {desc} in your browser"


def search_maps(query: str) -> str:
    """Search Google Maps for a place, business, or address."""
    url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
    webbrowser.open(url)
    return f"Opened Google Maps search for: {query}"


# ── Reminders ─────────────────────────────────────────────────────────────────

def add_reminder(text: str, due_time: str = "") -> str:
    """
    Add a new reminder to the reminder list.
    text: what to be reminded about.
    due_time: optional time string such as '3:00 PM' or '2026-05-16 15:00'.
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
    try:
        from vision.analyzer import ScreenAnalyzer
        import config as _cfg
        from google import genai as _genai
        client = _genai.Client(api_key=_cfg.GEMINI_API_KEY)
        analyzer = ScreenAnalyzer(client, _cfg.GEMINI_MODEL)
        result = analyzer.analyze(question)
        _try_annotate_from_vision(question, result)
        return result
    except Exception as exc:
        return f"Screen analysis error: {exc}"


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
    try:
        from vision.analyzer import ScreenAnalyzer
        import config as _cfg
        from google import genai as _genai
        client   = _genai.Client(api_key=_cfg.GEMINI_API_KEY)
        analyzer = ScreenAnalyzer(client, _cfg.GEMINI_MODEL)
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
        return f"Screen element search error: {exc}"


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
]}

ALL_TOOLS: list = list(TOOL_MAP.values())

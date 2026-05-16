"""
F.R.I.D.A.Y. — Mouse & Keyboard Automation
Thin, safe wrappers around PyAutoGUI for computer control.
All functions return a plain string result for Gemini tool responses.
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

try:
    import pyautogui
    pyautogui.FAILSAFE = True   # Move mouse to top-left corner to abort
    pyautogui.PAUSE    = 0.05   # Small pause between actions for stability
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False
    logger.warning("PyAutoGUI not installed — computer control unavailable")

_UNAVAILABLE = "Computer control unavailable — PyAutoGUI not installed."


# ── Mouse ─────────────────────────────────────────────────────────────────

def move_mouse(x: int, y: int) -> str:
    """Move the mouse cursor to screen coordinates (x, y)."""
    if not HAS_PYAUTOGUI:
        return _UNAVAILABLE
    try:
        pyautogui.moveTo(x, y, duration=0.3)
        return f"Mouse moved to ({x}, {y})"
    except Exception as exc:
        return f"Mouse move failed: {exc}"


def click(x: int, y: int) -> str:
    """Click the left mouse button at screen coordinates (x, y)."""
    if not HAS_PYAUTOGUI:
        return _UNAVAILABLE
    try:
        pyautogui.click(x, y)
        return f"Clicked at ({x}, {y})"
    except Exception as exc:
        return f"Click failed: {exc}"


def double_click(x: int, y: int) -> str:
    """Double-click the left mouse button at screen coordinates (x, y)."""
    if not HAS_PYAUTOGUI:
        return _UNAVAILABLE
    try:
        pyautogui.doubleClick(x, y)
        return f"Double-clicked at ({x}, {y})"
    except Exception as exc:
        return f"Double-click failed: {exc}"


def right_click(x: int, y: int) -> str:
    """Right-click at screen coordinates (x, y) to open context menu."""
    if not HAS_PYAUTOGUI:
        return _UNAVAILABLE
    try:
        pyautogui.rightClick(x, y)
        return f"Right-clicked at ({x}, {y})"
    except Exception as exc:
        return f"Right-click failed: {exc}"


def scroll(x: int, y: int, amount: int) -> str:
    """
    Scroll at screen position (x, y).
    amount: positive scrolls up, negative scrolls down.
    """
    if not HAS_PYAUTOGUI:
        return _UNAVAILABLE
    try:
        pyautogui.scroll(amount, x=x, y=y)
        direction = "up" if amount > 0 else "down"
        return f"Scrolled {direction} at ({x}, {y})"
    except Exception as exc:
        return f"Scroll failed: {exc}"


def get_screen_size() -> str:
    """Return the current screen resolution."""
    if not HAS_PYAUTOGUI:
        return _UNAVAILABLE
    try:
        w, h = pyautogui.size()
        return f"Screen resolution: {w}x{h}"
    except Exception as exc:
        return f"Screen size check failed: {exc}"


def get_mouse_position() -> str:
    """Return the current mouse cursor position."""
    if not HAS_PYAUTOGUI:
        return _UNAVAILABLE
    try:
        x, y = pyautogui.position()
        return f"Mouse is at ({x}, {y})"
    except Exception as exc:
        return f"Position check failed: {exc}"


# ── Keyboard ──────────────────────────────────────────────────────────────

def type_text(text: str) -> str:
    """
    Type the given text at the current cursor position, character by character.
    Use for filling in forms, writing in text editors, etc.
    """
    if not HAS_PYAUTOGUI:
        return _UNAVAILABLE
    try:
        pyautogui.write(text, interval=0.04)
        return f"Typed: {text[:60]}{'...' if len(text) > 60 else ''}"
    except Exception as exc:
        return f"Type failed: {exc}"


def press_key(key: str) -> str:
    """
    Press a single keyboard key.
    Supported keys: enter, tab, escape, backspace, delete, space, up, down,
    left, right, home, end, pageup, pagedown, f1-f12, printscreen, insert,
    win, alt, ctrl, shift, capslock, numlock, scrolllock, and any letter/number.
    """
    if not HAS_PYAUTOGUI:
        return _UNAVAILABLE
    try:
        pyautogui.press(key.lower())
        return f"Pressed key: {key}"
    except Exception as exc:
        return f"Key press failed: {exc}"


def hotkey(*keys: str) -> str:
    """
    Press a keyboard shortcut with multiple keys held simultaneously.
    Examples: hotkey('ctrl', 'c'), hotkey('ctrl', 'alt', 'delete'),
              hotkey('win', 'd'), hotkey('alt', 'f4').
    Pass each key as a separate argument.
    """
    if not HAS_PYAUTOGUI:
        return _UNAVAILABLE
    try:
        pyautogui.hotkey(*keys)
        return f"Hotkey: {'+'.join(keys)}"
    except Exception as exc:
        return f"Hotkey failed: {exc}"

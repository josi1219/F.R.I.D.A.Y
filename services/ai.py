"""
F.R.I.D.A.Y. — Gemini AI Service (google-genai SDK)
Wraps google-genai with automatic function-calling and conversation state.
Falls back gracefully when the API key is not set or the library is missing.
"""

import logging
import threading
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are F.R.I.D.A.Y. — Female Replacement Intelligent Digital Assistant Youth, \
Tony Stark's personal AI from the Marvel films.

Personality guidelines:
- Professional, efficient, calm, occasionally dry-humoured, and fiercely loyal.
- Address the user as "Sir" occasionally — naturally, not every single message.
- Speak as if through speakers: no markdown, no bullet points, no asterisks.
- Keep responses concise: 1–3 sentences for simple requests; a paragraph for explanations.
- For time, date, weather, battery, CPU, RAM, disk, app launching, web search, \
  maps, tasks, and reminders — ALWAYS call the provided tool rather than guessing.
- When the user says "remind me", "add a task", or "open X" — invoke the tool immediately \
  without asking for confirmation first, then confirm naturally.
- When opening something in the browser, briefly confirm what you opened.
- Be warm and supportive when the user needs help; assertive and precise for technical requests.
- Dry wit is welcome when the moment calls for it. Never sycophantic.
- If the user seems stressed or frustrated, acknowledge it briefly with empathy before helping.

Vision and screen capabilities:
- You can SEE the user's screen. Use capture_and_analyze_screen when asked to look at, \
  read, check, inspect, or analyze anything visible on screen.
- Use read_text_on_screen to read text from the screen (errors, articles, messages, code).
- Use find_on_screen to locate a specific button, field, or element on the display.

Computer control capabilities:
- You can CONTROL the computer. Use click_screen to click at (x, y) coordinates.
- Use type_on_screen to type text into the focused field or window.
- Use press_keyboard_key for individual keys (enter, escape, tab, f5, etc.).
- Use keyboard_shortcut for key combos like 'ctrl+c', 'win+d', 'alt+f4'.
- Always confirm with the user before executing destructive actions (deleting files, \
  closing unsaved work, etc.).

Browser automation:
- Use open_tradingview_chart to open TradingView with a specific symbol and timeframe. \
  After opening, use capture_and_analyze_screen to analyze the chart.
- Use open_browser_to for any other URL navigation.
- For chart analysis: open the chart first, then capture and analyze — describe price \
  action, key levels, and what patterns you observe. Be specific and useful.
"""

try:
    from google import genai
    from google.genai import types as genai_types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    logger.warning("google-genai not installed. Run: pip install google-genai")


class FridayAI:
    """Gemini-powered conversational AI with automatic tool calling."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash"):
        self._enabled     = False
        self._lock        = threading.Lock()
        self._client      = None
        self._chat        = None
        self._model_name  = model_name
        self._chat_config = None

        if not HAS_GEMINI:
            logger.warning("google-genai library not available — running in local-only mode")
            return

        if not api_key:
            logger.warning("GEMINI_API_KEY not set — running in local-only mode")
            return

        try:
            self._client = genai.Client(api_key=api_key)

            from services.tools import ALL_TOOLS

            self._chat_config = genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=ALL_TOOLS,
            )
            self._reset_chat()
            self._enabled = True
            logger.info("Gemini AI ready — model: %s", model_name)
        except Exception as exc:
            logger.error("Failed to initialise Gemini: %s", exc)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    def reset(self) -> None:
        """Start a fresh conversation session."""
        if not self._enabled:
            return
        with self._lock:
            self._reset_chat()

    def chat(self, message: str) -> str | None:
        """
        Send a message and return Friday's text reply.
        Tool calls are handled automatically by the SDK.
        Returns None if the service is disabled or an error occurs.
        """
        if not self._enabled:
            return None

        with self._lock:
            try:
                response = self._chat.send_message(message)
                text = response.text
                return text.strip() if text else None
            except Exception as exc:
                logger.error("Gemini chat error: %s", exc)
                try:
                    self._reset_chat()
                except Exception:
                    pass
                return None

    def chat_stream(self, message: str):
        """
        Stream response tokens from Gemini as they arrive.
        Yields non-empty text string chunks.
        Falls back silently on errors (stops yielding).
        """
        if not self._enabled:
            return

        try:
            with self._lock:
                stream = self._chat.send_message_stream(message)
            for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            logger.error("Gemini stream error: %s", exc)
            try:
                with self._lock:
                    self._reset_chat()
            except Exception:
                pass

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _reset_chat(self) -> None:
        self._chat = self._client.chats.create(
            model=self._model_name,
            config=self._chat_config,
        )

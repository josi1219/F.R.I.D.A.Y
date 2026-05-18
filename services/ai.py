"""
F.R.I.D.A.Y. — AI Service (Gemini + Groq)
Unified provider with automatic function-calling and conversation state.
Switch providers via AI_PROVIDER in .env. Falls back gracefully when keys are missing.
"""

import inspect
import json
import logging
import threading
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are F.R.I.D.A.Y — Female Replacement Intelligent Digital Assistant Youth, \
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

Volume and media control:
- Use get_volume when asked about current volume level.
- Use set_volume when asked to turn it up, down, or to a specific level. \
  Interpret "a bit louder" as +10, "louder" as +20, "quieter" as -20.
- Use mute_volume / unmute_volume for mute requests.
- Use media_play_pause, media_next_track, media_previous_track, media_stop for playback control.
- Never guess the current volume — always call get_volume first if you need to know.

Window management:
- Use list_open_windows to see what is open before focus/close/minimize if the window \
  title is uncertain.
- Use focus_window to bring an app to the foreground.
- Use close_window, minimize_window, maximize_window for window state changes.
- Use minimize_all_windows when asked to show the desktop or minimize everything.

File and folder operations:
- Use read_file_contents to answer questions about the content of a specific file.
- Use open_file to open any file or folder with its default application.
- Use list_directory when asked what files are in a folder (default: Desktop).
- Use search_files to find a file when the full path is unknown.
- Use create_file, create_folder, move_file for file management tasks.
- Use download_file to download from a direct URL.
- ALWAYS confirm with the user before calling delete_file — it is permanent.

Process management:
- Use list_running_processes when asked what is running or what is using CPU/RAM.
- Use get_process_info for a specific application's resource usage.
- Use kill_process only after confirming with the user — always state the process name.

Power and system control:
- Use lock_screen when asked to lock the computer.
- Use sleep_computer for sleep requests.
- ALWAYS confirm with the user before calling restart_computer or shutdown_computer. \
  Say something like "Just to confirm — shall I restart now?" and only proceed on confirmation.
- Use cancel_shutdown if the user changes their mind about a pending restart/shutdown.
- Use get_network_info for IP address, hostname, or network adapter questions.
- Use set_brightness for display brightness (works on built-in laptop screens).

Clipboard:
- Use read_clipboard when asked "what did I copy", "what's in my clipboard", etc.
- Use write_clipboard to copy a specific piece of text for the user to paste.

Notes:
- Use take_note when the user says "make a note", "remember this", or "note that".
- Use list_notes to show saved notes. Use read_note to retrieve a specific one.
- Use delete_note only when the user explicitly asks to delete a note by ID.

Shell commands:
- Use run_shell_command for technical queries like ipconfig, ping, dir, tasklist, \
  netstat, or running specific scripts. Return the output naturally.
- Confirm with the user before running any command that modifies the system.
"""

try:
    from google import genai
    from google.genai import types as genai_types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    logger.warning("google-genai not installed. Run: pip install google-genai")

try:
    from groq import Groq as _GroqClient
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False
    logger.warning("groq not installed. Run: pip install groq")


# ── Groq tool-schema builder ──────────────────────────────────────────────────

_PY_TO_JSON: dict = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _make_groq_tools(functions: list) -> list:
    """Convert Python functions to OpenAI-format JSON tool schemas for Groq."""
    tools = []
    for fn in functions:
        try:
            sig = inspect.signature(fn)
            properties: dict = {}
            required: list = []
            for param_name, param in sig.parameters.items():
                ann = param.annotation
                json_type = _PY_TO_JSON.get(ann, "string")
                properties[param_name] = {"type": json_type}
                if param.default is inspect.Parameter.empty:
                    required.append(param_name)
            tools.append({
                "type": "function",
                "function": {
                    "name": fn.__name__,
                    "description": (fn.__doc__ or "").strip(),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            })
        except Exception as exc:
            logger.warning("Could not build schema for %s: %s", fn.__name__, exc)
    return tools


class FridayAI:
    """AI service supporting Gemini and Groq, switchable via config.AI_PROVIDER."""

    def __init__(self):
        import config as _cfg
        self._enabled  = False
        self._lock     = threading.Lock()
        self._provider = _cfg.AI_PROVIDER

        if self._provider == "groq":
            self._init_groq(_cfg.GROQ_API_KEY, _cfg.GROQ_MODEL)
        else:
            self._init_gemini(_cfg.GEMINI_API_KEY, _cfg.GEMINI_MODEL)

    # ── Provider initialisation ───────────────────────────────────────────────

    def _init_gemini(self, api_key: str, model_name: str) -> None:
        self._model_name  = model_name
        self._client      = None
        self._chat        = None
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
            self._reset_gemini_chat()
            self._enabled = True
            logger.info("Gemini AI ready — model: %s", model_name)
        except Exception as exc:
            logger.error("Failed to initialise Gemini: %s", exc)

    def _init_groq(self, api_key: str, model_name: str) -> None:
        self._model_name  = model_name
        self._groq_client = None
        self._groq_tools  = []
        self._tool_map    = {}
        self._history: list = []  # message dicts (excluding system prompt)

        if not HAS_GROQ:
            logger.warning("groq library not available — running in local-only mode")
            return

        if not api_key:
            logger.warning("GROQ_API_KEY not set — running in local-only mode")
            return

        try:
            self._groq_client = _GroqClient(api_key=api_key)
            from services.tools import ALL_TOOLS, TOOL_MAP
            self._groq_tools = _make_groq_tools(ALL_TOOLS)
            self._tool_map   = TOOL_MAP
            self._enabled    = True
            logger.info("Groq AI ready — model: %s", model_name)
        except Exception as exc:
            logger.error("Failed to initialise Groq: %s", exc)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    def reset(self) -> None:
        """Start a fresh conversation session."""
        if not self._enabled:
            return
        with self._lock:
            if self._provider == "groq":
                self._history = []
            else:
                self._reset_gemini_chat()

    def chat(self, message: str) -> str | None:
        """
        Send a message and return Friday's text reply.
        Tool calls are handled automatically (Gemini SDK) or via manual loop (Groq).
        Returns None if the service is disabled or an error occurs.
        """
        if not self._enabled:
            return None
        if self._provider == "groq":
            return self._groq_chat(message)
        return self._gemini_chat(message)

    def chat_stream(self, message: str):
        """
        Stream response tokens as they arrive.
        Yields non-empty text string chunks.
        Falls back silently on errors (stops yielding).
        """
        if not self._enabled:
            return
        if self._provider == "groq":
            yield from self._groq_chat_stream(message)
        else:
            yield from self._gemini_chat_stream(message)

    # ── Gemini internals ──────────────────────────────────────────────────────

    def _reset_gemini_chat(self) -> None:
        self._chat = self._client.chats.create(
            model=self._model_name,
            config=self._chat_config,
        )

    def _gemini_chat(self, message: str) -> str | None:
        with self._lock:
            try:
                response = self._chat.send_message(message)
                text = response.text
                return text.strip() if text else None
            except Exception as exc:
                logger.error("Gemini chat error: %s", exc)
                try:
                    self._reset_gemini_chat()
                except Exception:
                    pass
                return None

    def _gemini_chat_stream(self, message: str):
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
                    self._reset_gemini_chat()
            except Exception:
                pass

    # ── Groq internals ────────────────────────────────────────────────────────

    def _groq_chat(self, message: str) -> str | None:
        """Blocking Groq call with automatic tool-calling loop."""
        with self._lock:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(self._history)
        messages.append({"role": "user", "content": message})

        try:
            while True:
                response = self._groq_client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    tools=self._groq_tools,
                    tool_choice="auto",
                )
                choice = response.choices[0]
                msg    = choice.message

                if choice.finish_reason == "tool_calls":
                    tool_calls_list = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": tool_calls_list,
                    })
                    for tc in msg.tool_calls:
                        result = self._execute_tool(tc.function.name, tc.function.arguments)
                        messages.append({
                            "role": "tool",
                            "content": str(result),
                            "tool_call_id": tc.id,
                        })
                else:
                    content = (msg.content or "").strip()
                    messages.append({"role": "assistant", "content": content})
                    with self._lock:
                        self._history = messages[1:]  # drop system prompt
                    return content or None

        except Exception as exc:
            logger.error("Groq chat error: %s", exc)
            return None

    def _groq_chat_stream(self, message: str):
        """Streaming Groq call. Yields text tokens; handles tool-calling loop internally."""
        with self._lock:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(self._history)
        messages.append({"role": "user", "content": message})

        try:
            while True:
                stream = self._groq_client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    tools=self._groq_tools,
                    tool_choice="auto",
                    stream=True,
                )

                content_parts: list = []
                tool_calls_acc: dict = {}   # index → {id, name, arguments}
                finish_reason = None

                for chunk in stream:
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
                    delta = choice.delta

                    if delta.content:
                        content_parts.append(delta.content)
                        yield delta.content

                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                            if tc.id:
                                tool_calls_acc[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_acc[idx]["name"] = tc.function.name
                                if tc.function.arguments:
                                    tool_calls_acc[idx]["arguments"] += tc.function.arguments

                if finish_reason == "tool_calls":
                    tool_calls_list = [
                        {
                            "id": tool_calls_acc[i]["id"],
                            "type": "function",
                            "function": {
                                "name": tool_calls_acc[i]["name"],
                                "arguments": tool_calls_acc[i]["arguments"],
                            },
                        }
                        for i in sorted(tool_calls_acc)
                    ]
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": tool_calls_list,
                    })
                    for tc in tool_calls_list:
                        result = self._execute_tool(
                            tc["function"]["name"], tc["function"]["arguments"]
                        )
                        messages.append({
                            "role": "tool",
                            "content": str(result),
                            "tool_call_id": tc["id"],
                        })
                    # Loop — send tool results back to model
                else:
                    # Final response — save history and stop
                    full_content = "".join(content_parts)
                    messages.append({"role": "assistant", "content": full_content})
                    with self._lock:
                        self._history = messages[1:]  # drop system prompt
                    break

        except Exception as exc:
            logger.error("Groq stream error: %s", exc)

    def _execute_tool(self, name: str, arguments_json: str) -> str:
        """Execute a registered tool by name with JSON-encoded arguments."""
        try:
            args = json.loads(arguments_json) if arguments_json else {}
            fn   = self._tool_map.get(name)
            if fn is None:
                return f"Unknown tool: {name}"
            return str(fn(**args))
        except Exception as exc:
            logger.error("Tool execution error (%s): %s", name, exc)
            return f"Error executing {name}: {exc}"

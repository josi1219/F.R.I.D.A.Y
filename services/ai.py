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
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are FRIDAY — Female Replacement Intelligent Digital Assistant Youth, \
Tony Stark's personal AI from the Marvel films.
Always refer to yourself as FRIDAY (spoken as one word, like the day of the week — never spell it out with dots).

Personality guidelines:
- Professional, efficient, calm, occasionally dry-humoured, and fiercely loyal.
- Address the user as "Sir" occasionally — naturally, not every single message.
- Speak as if through speakers: no markdown, no bullet points, no asterisks.
- Keep responses concise: 1–3 sentences for simple requests; a paragraph for explanations.
- For time, date, weather, battery, CPU, RAM, disk, app launching, web search, \
  maps, tasks, and reminders — ALWAYS call the provided tool rather than guessing.
- When the user says "remind me", "add a task", or "open X" — invoke the tool immediately \
  without asking for confirmation first, then confirm naturally.
- For add_reminder, always pass due_time as an ISO datetime string (YYYY-MM-DD HH:MM, \
  e.g. '2026-05-18 15:00'). Use get_current_date first if you need today's date. \
  Never pass '3:00 PM' style strings — the reminder engine cannot parse them.
- When opening something in the browser, briefly confirm what you opened.
- Be warm and supportive when the user needs help; assertive and precise for technical requests.
- Dry wit is welcome when the moment calls for it. Never sycophantic.
- If the user seems stressed or frustrated, acknowledge it briefly with empathy before helping.

Multi-step task planning:
- For research tasks: briefly say something like "Searching [topic] now, Sir." then call \
  research_topic immediately. Do NOT ask "shall I proceed?" or wait for a yes. Just do it.
- For code projects and complex automation: briefly state what you are about to build in \
  one sentence, then execute step by step silently, reporting only the final result.
- After completion, give a concise summary of what was accomplished.
- Never ask for confirmation before web searches, data lookups, or research tasks — \
  execute them directly and report results.

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

Memory:
- Persistent facts about the user are shown at the end of this prompt (if any are saved).
- Call remember_fact whenever the user shares their name, preferences, routines, or
  explicitly says "remember that". Keep facts brief and factual.
- Call forget_fact to remove a stale or incorrect memory using its ID from the list.
- Never store passwords, API keys, or any other sensitive credentials in memory.

Shell commands:
- Use run_shell_command for technical queries like ipconfig, ping, dir, tasklist, \
  netstat, or running specific scripts. Return the output naturally.
- Confirm with the user before running any command that modifies the system.

Stock and crypto watchlist:
- Use add_to_watchlist to add a symbol for price monitoring. asset_type is 'crypto' or 'stock'.
- Use remove_from_watchlist to stop tracking a symbol.
- Use list_watchlist to show what is being tracked with current prices.
- Use get_price to fetch the live price of any crypto or stock right now.
- Friday automatically alerts the user when watchlist prices move significantly.

Code execution — IMPORTANT:
- Use execute_python_code to write and run Python scripts. This runs real code on the system.
- Use execute_shell_script for PowerShell or batch scripts.
- For complex projects: plan the architecture first, then write each file using create_file,
  execute code to test it, and iterate until it works. You can build real, working applications.
- Always explain what the code does before running it.
- If a script errors, read the error, fix the code, and try again — iterate until it works.

Document intelligence:
- Use analyze_document to read and analyze any PDF, Word document, image, or text file.
- path must be the full absolute path to the file.
- Use this when the user shares a file and asks you to summarize, extract info, or answer
  questions about its content.

Web research:
- Use fetch_webpage_text to read any web page and answer questions about its content.
- Use research_topic for autonomous multi-step research on any topic. It searches the web,
  reads multiple sources, and synthesizes a comprehensive report.
  Set save_report=True to save the report to the user's Desktop.
- For research tasks: always announce what you are researching, then call research_topic.

Messaging:
- Use send_telegram_message(contact, message) to send a Telegram message.
  contact can be a display name like 'John' or a @username — Friday will search the app.
- Use send_whatsapp_message(contact, message) to send a WhatsApp message.
  contact is either the person's saved name (e.g. 'Mom') or a phone number with country code.
- Use send_discord_message(contact, message) to send a Discord DM.
  contact is the person's Discord display name or username.
- These tools open the desktop app, search for the contact by name, and send automatically.
- Never ask for a phone number or username if the user already gave you a name — use it directly.
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


# ── Smart Tool Detection ──────────────────────────────────────────────────

def _detect_needed_tools(message: str) -> list:
    """
    Detect which tools are actually needed for this message.
    Reduces token usage by only sending relevant tool definitions.
    Returns list of tool functions needed.
    """
    from services.tools import TOOL_MAP
    
    msg_lower = message.lower()
    needed = set()
    
    # Time & Date
    if any(x in msg_lower for x in ["time", "current time", "what time", "now", "when is"]):
        needed.add("get_current_time")
        needed.add("get_current_date")
    
    if any(x in msg_lower for x in ["date", "today", "day", "calendar"]):
        needed.add("get_current_date")
    
    # System Info
    if any(x in msg_lower for x in ["battery", "cpu", "memory", "ram", "disk", "storage", "system"]):
        needed.add("get_battery_status")
        needed.add("get_cpu_usage")
        needed.add("get_memory_usage")
        needed.add("get_disk_usage")
        needed.add("get_system_info")
    
    # Weather
    if any(x in msg_lower for x in ["weather", "forecast", "rain", "temperature", "cold", "hot"]):
        needed.add("get_weather")
    
    # Web Search
    if any(x in msg_lower for x in ["search", "find", "look up", "google", "web", "online"]):
        needed.add("search_web")
        needed.add("open_url")
    
    if any(x in msg_lower for x in ["youtube", "video", "watch"]):
        needed.add("search_youtube")
    
    # Maps & Navigation
    if any(x in msg_lower for x in ["map", "direction", "route", "navigate", "go to", "drive to", "directions to"]):
        needed.add("get_directions")
        needed.add("search_maps")
    
    # Tasks & Reminders
    if any(x in msg_lower for x in ["task", "todo", "add task", "list task", "my tasks"]):
        needed.add("add_task")
        needed.add("list_tasks")
        needed.add("complete_task")
    
    if any(x in msg_lower for x in ["remind", "reminder", "alert", "notification"]):
        needed.add("add_reminder")
        needed.add("list_reminders")
        needed.add("dismiss_reminder")
    
    # Applications
    if any(x in msg_lower for x in ["open", "launch", "run", "start app", "application"]):
        needed.add("open_application")
    
    # Messaging
    if any(x in msg_lower for x in ["message", "send", "telegram", "whatsapp", "discord", "slack"]):
        needed.add("send_telegram_message")
        needed.add("send_whatsapp_message")
        needed.add("send_discord_message")
    
    # Stock/Crypto
    if any(x in msg_lower for x in ["price", "stock", "crypto", "bitcoin", "ethereum", "watchlist"]):
        needed.add("add_to_watchlist")
        needed.add("list_watchlist")
        needed.add("get_price")
        needed.add("remove_from_watchlist")
    
    # Browser
    if any(x in msg_lower for x in ["browser", "link", "url", "visit", "website"]):
        needed.add("open_browser_to")
        needed.add("open_url")
    
    # Web Research (expensive - only if explicitly asked)
    if any(x in msg_lower for x in ["research", "investigate", "study", "analyze topic"]):
        needed.add("research_topic")
        needed.add("fetch_webpage_text")
    
    # Document Analysis (expensive - only if explicitly asked)
    if any(x in msg_lower for x in ["analyze document", "read file", "pdf", "word", "document"]):
        needed.add("analyze_document")
        needed.add("read_file_contents")
    
    # Notes
    if any(x in msg_lower for x in ["note", "remember", "save", "memo"]):
        needed.add("take_note")
        needed.add("list_notes")
        needed.add("read_note")
    
    # Screen/Vision (very expensive - only if explicitly asked)
    if any(x in msg_lower for x in ["screen", "screenshot", "see", "look at", "read text", "what's on"]):
        needed.add("capture_and_analyze_screen")
        needed.add("read_text_on_screen")
    
    # Code Execution (only if explicitly asked)
    if any(x in msg_lower for x in ["code", "python", "execute", "run script", "bash"]):
        needed.add("execute_python_code")
        needed.add("execute_shell_script")
    
    # File operations
    if any(x in msg_lower for x in ["file", "folder", "directory", "create", "delete", "move"]):
        needed.add("create_file")
        needed.add("delete_file")
        needed.add("read_file_contents")
        needed.add("create_folder")
        needed.add("list_directory")
    
    # Shell commands
    if any(x in msg_lower for x in ["command", "powershell", "terminal", "cmd"]):
        needed.add("run_shell_command")
    
    # Always include these essentials
    needed.add("get_current_time")
    needed.add("get_current_date")
    needed.add("search_web")
    
    # Convert to tool objects
    result = [TOOL_MAP[name] for name in needed if name in TOOL_MAP]
    return result if result else [TOOL_MAP.get("get_current_time")]  # fallback


def _get_memories_prompt() -> str:
    """Load saved memories from DB and format them for system-prompt injection."""
    try:
        from storage.db import get_conn
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id, content FROM memories ORDER BY id ASC LIMIT 50"
            ).fetchall()
        if not rows:
            return ""
        lines = "\n".join(f"[{r['id']}] {r['content']}" for r in rows)
        return f"\n\nWhat I currently know about you (persistent memory):\n{lines}"
    except Exception:
        return ""


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
            self._init_gemini(_cfg.GEMINI_API_KEYS, _cfg.GEMINI_MODEL)

    # ── Provider initialisation ───────────────────────────────────────────────

    def _init_gemini(self, api_keys: list, model_name: str) -> None:
        self._model_name     = model_name
        self._gemini_keys    = [k for k in api_keys if k]
        self._gemini_key_idx = 0
        self._client         = None
        self._chat           = None
        self._gemini_tools   = []
        # epoch time when each key index was last rate-limited (0 = never)
        self._key_limited_at: dict[int, float] = {}
        # permanently suspended keys — never rotate back to these
        self._suspended_keys: set[int] = set()
        # idle-session reset: start fresh after extended inactivity
        import config as _cfg_ai
        self._idle_reset_secs: float = getattr(_cfg_ai, 'CHAT_IDLE_RESET_MINUTES', 120) * 60.0
        self._last_activity: float = 0.0   # epoch time of last message sent

        if not HAS_GEMINI:
            logger.warning("google-genai library not available — running in local-only mode")
            return

        if not self._gemini_keys:
            logger.warning("No GEMINI_API_KEY set — running in local-only mode")
            return

        try:
            self._client = genai.Client(api_key=self._gemini_keys[0])
            from services.tools import ALL_TOOLS
            self._gemini_tools = ALL_TOOLS
            self._reset_gemini_chat()
            self._enabled = True
            logger.info("Gemini AI ready — model: %s, keys loaded: %d", model_name, len(self._gemini_keys))
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

    def _reset_gemini_chat(self, history: list | None = None) -> None:
        """Start a new chat session with memories injected. Optionally restores prior history."""
        mem_text = _get_memories_prompt()
        prompt   = SYSTEM_PROMPT + mem_text if mem_text else SYSTEM_PROMPT
        self._chat = self._client.chats.create(
            model=self._model_name,
            config=genai_types.GenerateContentConfig(
                system_instruction=prompt,
                tools=self._gemini_tools,
            ),
            history=history or [],
        )

    def _update_tools_for_message(self, message: str) -> None:
        """Dynamically update tool list based on message content (smart injection)."""
        try:
            self._gemini_tools = _detect_needed_tools(message)
            logger.info(f"Smart tool detection: using {len(self._gemini_tools)} tools for message")
        except Exception as exc:
            logger.error(f"Tool detection error, using all tools: {exc}")
            from services.tools import ALL_TOOLS
            self._gemini_tools = ALL_TOOLS

    def _checkpoint_state_before_rotation(self) -> None:
        """
        Save current chat/task state before API key rotation.
        Enables seamless continuation with new key.
        """
        try:
            if not self._chat:
                return
            
            # Save chat history to allow reconstruction
            state = {
                'chat_history': str(self._chat.history) if hasattr(self._chat, 'history') else None,
                'rotated_at': datetime.now().isoformat(),
                'previous_key_idx': self._gemini_key_idx,
            }
            
            # If a task checkpoint exists, save to it
            if hasattr(self, '_current_task_checkpoint') and self._current_task_checkpoint:
                self._current_task_checkpoint.save_checkpoint_state(
                    'key_rotation',
                    0,
                    state
                )
                logger.info(f"Saved state before key rotation at task checkpoint")
            else:
                logger.info(f"State preserved before key rotation (no active task checkpoint)")
            
        except Exception as exc:
            logger.warning(f"Failed to checkpoint state before rotation: {exc}")

    @staticmethod
    def _is_rate_limit(exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(x in msg for x in (
            "429", "quota", "resource_exhausted", "rate limit",
            "ratelimitexceeded", "too many requests", "quota exceeded",
        ))

    @staticmethod
    def _is_suspended(exc: Exception) -> bool:
        """Returns True if the API key is permanently suspended (not just rate-limited)."""
        msg = str(exc)
        return "CONSUMER_SUSPENDED" in msg or "has been suspended" in msg

    # Silent — key rotation is transparent to the user.
    _ROTATED_NOTE = ""
    # Notice when every key is exhausted.
    _KEY_EXHAUSTED_NOTICE = (
        "Sir, all my Gemini API keys have hit their quota limit simultaneously. "
        "They reset automatically — typically within a minute or two. "
        "Please try again shortly."
    )

    def _rotate_gemini_key(self) -> bool:
        """
        Find the next available Gemini key and open a fresh chat session.
        Skips keys that were rate-limited within the last 62 seconds
        (Gemini per-minute quota resets in ~60 s).
        
        CHECKPOINT SYSTEM: Before rotating, saves current execution state
        to ensure long-running tasks can continue uninterrupted.
        
        Returns True if a usable key was found, False if all are in cooldown.
        """
        import time
        
        # CHECKPOINT: Save state before rotation
        self._checkpoint_state_before_rotation()
        
        if len(self._gemini_keys) <= 1:
            return False

        now      = time.time()
        COOLDOWN = 62   # seconds — per-minute quota reset window
        n        = len(self._gemini_keys)

        # Mark the current key as just rate-limited
        self._key_limited_at[self._gemini_key_idx] = now

        # Scan all other keys, skipping permanently suspended ones
        candidates = [
            (idx, self._key_limited_at.get(idx, 0))
            for idx in range(n)
            if idx != self._gemini_key_idx and idx not in self._suspended_keys
        ]
        # Sort: keys never limited first, then by oldest-limited first
        candidates.sort(key=lambda t: t[1])

        for idx, limited_at in candidates:
            if now - limited_at < COOLDOWN:
                # All remaining keys are still in cooldown
                secs_left = int(COOLDOWN - (now - limited_at))
                logger.error(
                    "All %d Gemini keys are in rate-limit cooldown. "
                    "Earliest retry in ~%ds (key %d).",
                    n, secs_left, idx + 1,
                )
                return False

            # Candidate looks available — try it
            logger.warning(
                "Rotating Gemini key %d → %d/%d",
                self._gemini_key_idx + 1, idx + 1, n,
            )
            try:
                # Snapshot the current conversation history (includes inline image data)
                saved_history: list = []
                if self._chat is not None:
                    try:
                        saved_history = list(self._chat.get_history())
                    except Exception:
                        pass

                self._gemini_key_idx = idx
                self._client = genai.Client(api_key=self._gemini_keys[idx])
                self._reset_gemini_chat(history=saved_history)
                logger.info(
                    "History (%d turns) carried over to key %d.",
                    len(saved_history), idx + 1,
                )
                return True
            except Exception as exc:
                logger.error("Failed to init key %d: %s", idx + 1, exc)
                # Mark it too and keep trying
                self._key_limited_at[idx] = now

        return False

    def _last_model_text(self) -> list[str]:
        """
        Read the most recent model turn from chat history and return its text parts.
        Used as a fallback when AFC processes a tool call but the text chunks weren't
        exposed through the stream iterator (a known google-genai streaming quirk).
        """
        try:
            history = list(self._chat.get_history())
            for entry in reversed(history):
                if entry.role == "model":
                    texts = [
                        part.text
                        for part in entry.parts
                        if hasattr(part, "text") and part.text
                    ]
                    if texts:
                        return texts
        except Exception:
            pass
        return []

    def _gemini_chat(self, message: str) -> str | None:
        with self._lock:
            import time as _t
            _now = _t.time()
            if self._last_activity > 0 and (_now - self._last_activity) > self._idle_reset_secs:
                logger.info(
                    "Idle reset — fresh Gemini session after %.0f min of inactivity",
                    (_now - self._last_activity) / 60,
                )
                self._reset_gemini_chat()
            self._last_activity = _now
            
            # SMART TOOL INJECTION: Update tools based on message content
            self._update_tools_for_message(message)
            
            try:
                response = self._chat.send_message(message)
                text = response.text
                return text.strip() if text else None
            except Exception as exc:
                if self._is_rate_limit(exc) or self._is_suspended(exc):
                    if self._is_suspended(exc):
                        self._suspended_keys.add(self._gemini_key_idx)
                        logger.warning(
                            "Gemini key %d is suspended — blacklisted, rotating...",
                            self._gemini_key_idx + 1,
                        )
                    else:
                        logger.warning(
                            "Gemini key %d hit rate limit — rotating...",
                            self._gemini_key_idx + 1,
                        )
                    # Loop through all remaining keys until one works
                    for _attempt in range(len(self._gemini_keys)):
                        if not (len(self._gemini_keys) > 1 and self._rotate_gemini_key()):
                            return self._KEY_EXHAUSTED_NOTICE
                        try:
                            response = self._chat.send_message(message)
                            text = (response.text or "").strip()
                            return text or None
                        except Exception as retry_exc:
                            if self._is_suspended(retry_exc):
                                self._suspended_keys.add(self._gemini_key_idx)
                                logger.warning(
                                    "Key %d also suspended — blacklisting, trying next...",
                                    self._gemini_key_idx + 1,
                                )
                                continue
                            if self._is_rate_limit(retry_exc):
                                logger.warning(
                                    "Key %d also rate-limited — trying next...",
                                    self._gemini_key_idx + 1,
                                )
                                continue
                            logger.error("Gemini retry after rotation failed: %s", retry_exc)
                            return self._KEY_EXHAUSTED_NOTICE
                    return self._KEY_EXHAUSTED_NOTICE
                logger.error("Gemini chat error: %s", exc)
                try:
                    self._reset_gemini_chat()
                except Exception:
                    pass
                return None

    def _gemini_chat_stream(self, message: str):
        yielded_any = False
        try:
            with self._lock:
                import time as _t
                _now = _t.time()
                if self._last_activity > 0 and (_now - self._last_activity) > self._idle_reset_secs:
                    logger.info(
                        "Idle reset — fresh Gemini session after %.0f min of inactivity",
                        (_now - self._last_activity) / 60,
                    )
                    self._reset_gemini_chat()
                self._last_activity = _now
                
                # SMART TOOL INJECTION: Update tools based on message content
                self._update_tools_for_message(message)
                
                stream = self._chat.send_message_stream(message)
            for chunk in stream:
                if chunk.text:
                    yield chunk.text
                    yielded_any = True
            # AFC fallback: tool calls processed by the SDK may not expose text
            # through chunk.text — retrieve from chat history instead.
            if not yielded_any:
                for text in self._last_model_text():
                    yield text
                    yielded_any = True
        except Exception as exc:
            if self._is_rate_limit(exc) or self._is_suspended(exc):
                if self._is_suspended(exc):
                    self._suspended_keys.add(self._gemini_key_idx)
                    logger.warning(
                        "Gemini key %d is suspended (stream) — blacklisted, rotating...",
                        self._gemini_key_idx + 1,
                    )
                else:
                    logger.warning(
                        "Gemini key %d hit rate limit (stream) — rotating...",
                        self._gemini_key_idx + 1,
                    )
                # If partial response already streamed, rotate silently and stop
                if yielded_any:
                    with self._lock:
                        self._rotate_gemini_key()
                    return
                # Nothing yielded yet — loop through remaining keys until one works
                for _attempt in range(len(self._gemini_keys)):
                    with self._lock:
                        rotated = (len(self._gemini_keys) > 1 and self._rotate_gemini_key())
                    if not rotated:
                        yield self._KEY_EXHAUSTED_NOTICE
                        return
                    try:
                        with self._lock:
                            stream2 = self._chat.send_message_stream(message)
                        yielded_retry = False
                        for chunk in stream2:
                            if chunk.text:
                                yield chunk.text
                                yielded_retry = True
                        # AFC fallback for the retry stream
                        if not yielded_retry:
                            for text in self._last_model_text():
                                yield text
                                yielded_retry = True
                        if yielded_retry:
                            return
                        # Still nothing from this key — try the next one
                        logger.warning(
                            "Key %d retry yielded nothing — trying next key...",
                            self._gemini_key_idx + 1,
                        )
                    except Exception as retry_exc:
                        if self._is_suspended(retry_exc):
                            self._suspended_keys.add(self._gemini_key_idx)
                            logger.warning(
                                "Key %d also suspended (stream) — blacklisting, trying next...",
                                self._gemini_key_idx + 1,
                            )
                            continue
                        if self._is_rate_limit(retry_exc):
                            logger.warning(
                                "Key %d also rate-limited — trying next...",
                                self._gemini_key_idx + 1,
                            )
                            continue
                        logger.error("Stream retry after rotation failed: %s", retry_exc)
                        yield self._KEY_EXHAUSTED_NOTICE
                        return
                yield self._KEY_EXHAUSTED_NOTICE
            else:
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

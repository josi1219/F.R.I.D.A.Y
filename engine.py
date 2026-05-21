"""
F.R.I.D.A.Y. — Core Engine
Orchestrates the full voice pipeline:
  IDLE → (wake word OR hotkey) → LISTENING → THINKING → SPEAKING → IDLE

Wires together:
  VoiceListener, VoiceSpeaker, FridayAI, FridayOverlay, AnnotationOverlay
"""

import logging
import queue
import threading
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

logger = logging.getLogger(__name__)

try:
    import keyboard as kb
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False
    logger.warning("keyboard library not installed — hotkey activation unavailable")


class FridayEngine:
    """
    Central orchestrator for the F.R.I.D.A.Y. voice assistant.

    Usage:
        engine = FridayEngine(ai, overlay, annotation_overlay)
        engine.start()          # launches background threads
        ...
        engine.stop()           # clean shutdown
    """

    def __init__(self, ai, overlay, annotation_overlay=None):
        from voice.listener import VoiceListener
        from voice.speaker  import VoiceSpeaker

        self._ai          = ai
        self._overlay     = overlay
        self._ann_overlay = annotation_overlay

        self._listener    = VoiceListener()
        self._speaker     = VoiceSpeaker()

        self._stop_event  = threading.Event()
        self._listen_q: queue.Queue = queue.Queue()  # hotkey puts True here
        self._active_lock = threading.Lock()
        self._is_active   = False   # True while LISTENING/THINKING/SPEAKING
        self._proactive_q: queue.Queue = queue.Queue()  # queued proactive speech
        self._pre_duck_volume: int | None = None        # saved level before ducking
        self._conversation_mode = False  # True = stay listening after each response
        self._is_sleeping       = False  # True = sleep mode, waiting for wake word/hotkey

        # Import TTS here to avoid circular imports
        try:
            from services.tts import synthesize
            self._synthesize = synthesize
        except Exception as exc:
            logger.error("Could not import TTS: %s", exc)
            self._synthesize = None

    # ── Public API ─────────────────────────────────────────────────────────

    def start(self):
        """Start all background threads."""
        self._stop_event.clear()

        # Register global hotkey (Ctrl+Alt+F)
        if HAS_KEYBOARD:
            hotkey = getattr(config, "HOTKEY_ACTIVATE", "ctrl+alt+f")
            try:
                kb.add_hotkey(hotkey, self._hotkey_triggered)
                logger.info("Hotkey registered: %s", hotkey)
            except Exception as exc:
                logger.warning("Could not register hotkey '%s': %s", hotkey, exc)

        # Start voice loop thread
        t = threading.Thread(target=self._voice_loop, name="FridayEngine", daemon=True)
        t.start()

        # Start reminder polling thread
        r = threading.Thread(target=self._reminder_poll_loop, name="ReminderPoller", daemon=True)
        r.start()

        # Start proactive speech queue processor
        p = threading.Thread(target=self._proactive_loop, name="ProactiveLoop", daemon=True)
        p.start()

        # Start proactive background monitor (CPU/RAM/battery/stocks/work-timer)
        try:
            from services.monitor import ProactiveMonitor
            self._monitor = ProactiveMonitor(self)
            self._monitor.start()
        except Exception as exc:
            logger.warning("ProactiveMonitor failed to start: %s", exc)
            self._monitor = None

        # Morning briefing — fires 4 seconds after start if within briefing hours
        if getattr(config, "MORNING_BRIEFING_ENABLED", True):
            mb = threading.Thread(target=self._morning_briefing, name="MorningBriefing", daemon=True)
            mb.start()

        logger.info("FridayEngine started")

    def stop(self):
        """Signal all threads to stop cleanly."""
        self._stop_event.set()
        self._listener.stop()
        self._speaker.stop()
        if HAS_KEYBOARD:
            try:
                kb.unhook_all()
            except Exception:
                pass
        if getattr(self, "_monitor", None):
            self._monitor.stop()
        logger.info("FridayEngine stopped")

    def trigger_listen(self):
        """Programmatically trigger one listen cycle (same as pressing hotkey)."""
        self._hotkey_triggered()

    # ── Morning Briefing ────────────────────────────────────────────────────

    def _morning_briefing(self) -> None:
        """
        Fires once at startup if the local time is within the briefing window
        (default 05:00–11:00). Compiles a spoken briefing: time, weather, tasks,
        reminders, and any watched assets that moved overnight.
        """
        import time
        import datetime
        time.sleep(4)  # Let the engine fully boot first

        if self._stop_event.is_set():
            return

        hour = datetime.datetime.now().hour
        start_h = getattr(config, "MORNING_BRIEFING_START_HOUR", 5)
        end_h   = getattr(config, "MORNING_BRIEFING_END_HOUR",  11)
        if not (start_h <= hour < end_h):
            return

        try:
            parts: list[str] = []

            # Time & greeting
            now_str = datetime.datetime.now().strftime("%I:%M %p").lstrip("0")
            greeting = "Good morning" if hour < 12 else "Good afternoon"
            parts.append(f"{greeting}, Sir. It's {now_str}.")

            # Weather (reuse existing tool)
            try:
                from services.tools import get_weather
                weather = get_weather()
                if weather and "error" not in weather.lower():
                    # strip verbose prefix if present
                    w = weather.split(":", 1)[-1].strip()
                    parts.append(w)
            except Exception:
                pass

            # Pending tasks
            try:
                from storage.db import get_conn
                with get_conn() as conn:
                    task_count = conn.execute(
                        "SELECT COUNT(*) FROM tasks WHERE done = 0"
                    ).fetchone()[0]
                if task_count:
                    parts.append(
                        f"You have {task_count} pending task{'s' if task_count != 1 else ''}."
                    )
            except Exception:
                pass

            # Upcoming reminders (next 24 h)
            try:
                from storage.db import get_conn
                cutoff = (datetime.datetime.now() + datetime.timedelta(hours=24)).strftime(
                    "%Y-%m-%d %H:%M"
                )
                with get_conn() as conn:
                    reminders = conn.execute(
                        "SELECT text, due_time FROM reminders WHERE done = 0 "
                        "AND due_time IS NOT NULL AND due_time <= ? "
                        "ORDER BY due_time LIMIT 3",
                        (cutoff,),
                    ).fetchall()
                if reminders:
                    rem_list = "; ".join(
                        f"{r['text']} at {r['due_time'][-5:]}" for r in reminders
                    )
                    parts.append(f"Upcoming reminder{'s' if len(reminders) > 1 else ''}: {rem_list}.")
            except Exception:
                pass

            # Stock/crypto snapshot
            try:
                from services.monitor import _get_watchlist, _fetch_price
                watchlist = _get_watchlist()
                if watchlist:
                    snippets = []
                    for item in watchlist[:3]:  # top 3 to keep briefing short
                        price = _fetch_price(item["symbol"], item["asset_type"])
                        if price:
                            snippets.append(f"{item['symbol']} at ${price:,.2f}")
                    if snippets:
                        parts.append("Watchlist: " + ", ".join(snippets) + ".")
            except Exception:
                pass

            parts.append("Shall I go over anything in detail?")

            briefing = " ".join(parts)
            logger.info("Morning briefing: %s", briefing)
            self._proactive_q.put(briefing)

        except Exception as exc:
            logger.error("Morning briefing error: %s", exc)

    # ── Internal ───────────────────────────────────────────────────────────

    def _hotkey_triggered(self):
        """Called on hotkey press — interrupt speaking, start listening."""
        if self._speaker.is_playing:
            self._speaker.stop()
            logger.info("Interrupted playback via hotkey")

        with self._active_lock:
            if self._is_active:
                return  # Already in a cycle
            self._is_active = True

        self._listen_q.put(True)

    def _voice_loop(self):
        """
        Main loop:
          - Waits for wake word in background (if available)
          - OR waits for hotkey signal via _listen_q
          - Whichever comes first triggers a listen → respond cycle
        """
        if not self._listener.ready:
            logger.warning("VoiceListener not ready — running hotkey-only mode")
            self._hotkey_only_loop()
            return

        wake_available = (
            self._listener._wake_model is not None        # model already loaded
            or bool(getattr(config, "WAKE_WORD_MODEL", ""))  # model configured (may still be loading)
            or (bool(getattr(config, "WAKE_KEYWORD", "")) and self._listener.ready)
        )

        if wake_available:
            # Launch wake-word detector in its own thread; it posts to _listen_q
            ww_thread = threading.Thread(
                target=self._wake_word_watcher,
                name="WakeWordWatcher",
                daemon=True,
            )
            ww_thread.start()

        while not self._stop_event.is_set():
            try:
                # Block until a trigger arrives (hotkey or wake word)
                self._listen_q.get(timeout=0.5)
            except queue.Empty:
                continue

            # Any trigger enters conversation mode — keep listening until sleep phrase
            self._is_sleeping = False
            self._conversation_mode = True
            logger.info("Conversation mode: active")

            while not self._stop_event.is_set() and self._conversation_mode:
                got_speech = self._run_cycle()
                if not got_speech:
                    # Timed out waiting for speech — exit conversation mode silently
                    self._conversation_mode = False
                    logger.info("Conversation mode ended — no speech detected")
                    break
                if self._conversation_mode:
                    import time as _ct
                    _ct.sleep(0.5)  # brief gap so mic doesn't re-capture FRIDAY's voice
                    # Drain any queued hotkey/wake-word triggers that arrived mid-conversation
                    while not self._listen_q.empty():
                        try:
                            self._listen_q.get_nowait()
                        except queue.Empty:
                            break
                    # Re-claim active slot for the next turn
                    with self._active_lock:
                        if not self._is_active:
                            self._is_active = True

    def _hotkey_only_loop(self):
        """Fallback loop when voice input is unavailable — hotkey triggers only."""
        while not self._stop_event.is_set():
            try:
                self._listen_q.get(timeout=0.5)
            except queue.Empty:
                continue
            # No voice input — overlay just blinks
            self._set_state("listening")
            self._set_text("Voice input unavailable — check microphone")
            import time
            time.sleep(2)
            self._set_state("idle")
            with self._active_lock:
                self._is_active = False

    def _wake_word_watcher(self):
        """Continuously listen for the wake word and post to _listen_q."""
        import time
        while not self._stop_event.is_set():
            try:
                # Don't open a second mic stream while already in conversation mode
                if self._conversation_mode:
                    time.sleep(0.05)
                    continue
                detected = self._listener.wait_for_wake_word()
                if not detected:
                    # Model not ready yet or stop event fired — back off before retrying
                    time.sleep(1.0)
                    continue
                if detected and not self._stop_event.is_set():
                    with self._active_lock:
                        if not self._is_active:
                            self._is_active = True
                            self._listen_q.put(True)
                    # Wait until the triggered cycle fully finishes before re-opening
                    # the mic for wake-word detection — prevents two simultaneous
                    # sounddevice streams on the same device.
                    while not self._stop_event.is_set():
                        time.sleep(0.15)
                        with self._active_lock:
                            if not self._is_active:
                                break
                    # Brief cooldown before re-opening the stream so any residual
                    # mic audio from the just-finished cycle drains away.
                    time.sleep(0.4)
            except Exception as exc:
                logger.error("Wake word watcher error: %s", exc)
                import time as _time
                _time.sleep(1)

    def _run_cycle(self) -> bool:
        """
        Execute one full listen → think → speak cycle.
        Returns True if speech was detected and processed, False if timed out.
        """
        import time
        got_speech = False

        try:
            # ── LISTENING ─────────────────────────────────────────────────
            self._set_state("listening")
            self._set_text("Listening...")
            self._listener.reset_stop()

            text = self._listener.listen_once(timeout=12.0)

            if not text.strip():
                logger.info("No speech detected or empty transcription")
                return False  # finally will still run

            got_speech = True
            logger.info("User: %s", text)

            # Reset monitor session timer — user is active
            if getattr(self, "_monitor", None):
                self._monitor.reset_session_timer()

            # ── Sleep phrase check ─────────────────────────────────────────
            sleep_phrase = getattr(config, "SLEEP_PHRASE", "friday sleep").lower()
            if sleep_phrase in text.lower():
                logger.info("Sleep phrase detected — exiting conversation mode")
                self._conversation_mode = False
                self._is_sleeping = True
                goodbye = "Going to sleep."
                if self._synthesize:
                    try:
                        self._set_state("speaking")
                        self._duck_system_volume()
                        audio = self._synthesize(goodbye)
                        self._speaker.speak(audio)
                    except Exception as exc:
                        logger.error("TTS error on sleep: %s", exc)
                    finally:
                        self._restore_system_volume()
                return True  # finally will still run

            self._set_state("thinking")
            self._set_text(text)

            # ── STREAM THINK + SPEAK ───────────────────────────────────────
            # Gemini tokens stream in → split into sentences → each sentence
            # synthesized immediately → played as ready. First audio arrives
            # ~800ms after speech ends instead of waiting for full response.
            self._stream_respond(text)

        except Exception as exc:
            logger.error("Voice cycle error: %s", exc)
        finally:
            if self._is_sleeping:
                self._set_state("sleeping")
                hotkey = getattr(config, "HOTKEY_ACTIVATE", "ctrl+alt+f")
                self._set_text(f"Sleeping... say 'hey Jarvis' or press {hotkey}")
            else:
                self._set_state("idle")
                self._set_text("F.R.I.D.A.Y. ready")
            with self._active_lock:
                self._is_active = False

        return got_speech

    # ── Streaming respond ───────────────────────────────────────────────────

    def _stream_respond(self, user_text: str) -> None:
        """
        Pipeline: stream Gemini tokens → split into sentences → synthesize each
        sentence immediately → play as ready.
        First audio plays ~800ms after speech ends (vs 2-4s with blocking path).
        Falls back to blocking chat() if streaming yields no text (tool calls).
        """
        import re
        import queue as _queue

        SENT_END = re.compile(r'(?<=[.!?])\s+')
        sentence_q: _queue.Queue = _queue.Queue()
        audio_q: _queue.Queue = _queue.Queue(maxsize=3)
        full_parts: list = []

        def _stream_and_split():
            buf = ""
            try:
                for token in self._ai.chat_stream(user_text):
                    buf += token
                    full_parts.append(token)
                    parts = SENT_END.split(buf)
                    if len(parts) > 1:
                        for s in parts[:-1]:
                            if s.strip():
                                sentence_q.put(s.strip())
                        buf = parts[-1]
                if buf.strip():
                    sentence_q.put(buf.strip())
            except Exception as exc:
                logger.error("Stream thread error: %s", exc)
            finally:
                sentence_q.put(None)  # always send sentinel to unblock synthesizer

        def _synthesize_loop():
            while True:
                sentence = sentence_q.get()
                if sentence is None:
                    audio_q.put(None)
                    return
                try:
                    audio = self._synthesize(sentence)
                    audio_q.put(audio)
                except Exception as exc:
                    logger.error("TTS error: %s", exc)

        t_stream = threading.Thread(target=_stream_and_split, daemon=True)
        t_synth  = threading.Thread(target=_synthesize_loop, daemon=True)
        t_stream.start()
        t_synth.start()

        first = True
        while True:
            audio = audio_q.get()
            if audio is None:
                break
            if first:
                self._set_state("speaking")
                self._duck_system_volume()
                first = False
            self._speaker.speak(audio)
        self._restore_system_volume()

        t_stream.join(timeout=30)
        full_response = "".join(full_parts)

        if full_response.strip():
            logger.info("Friday: %s", full_response)
            self._set_text(full_response[:120])
        else:
            # Streaming yielded nothing — transient error (chat was already reset).
            # Do NOT re-send the same message; just let the user know.
            logger.warning("Stream yielded nothing for: %s", user_text)
            response = "I'm sorry, Sir — my connection dropped mid-response. Could you repeat that?"
            logger.info("Friday: %s", response)
            self._set_state("speaking")
            self._set_text(response[:120])
            if self._synthesize:
                try:
                    self._duck_system_volume()
                    audio = self._synthesize(response)
                    self._speaker.speak(audio)
                except Exception as exc:
                    logger.error("TTS error: %s", exc)
                finally:
                    self._restore_system_volume()

    # ── Helpers ────────────────────────────────────────────────────────────

    def _set_state(self, state: str):
        try:
            self._overlay.set_state(state)
        except Exception:
            pass

    def _set_text(self, text: str):
        try:
            self._overlay.set_text(text)
        except Exception:
            pass

    # ── Volume ducking ──────────────────────────────────────────────

    def _duck_system_volume(self) -> None:
        """Lower system volume before FRIDAY speaks. Saves the original level."""
        duck_amount = getattr(config, "VOLUME_DUCK_AMOUNT", 40)
        if not duck_amount:
            self._pre_duck_volume = None
            return
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices   = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol       = cast(interface, POINTER(IAudioEndpointVolume))
            current   = int(round(vol.GetMasterVolumeLevelScalar() * 100))
            target    = max(0, current - duck_amount)
            self._pre_duck_volume = current
            if target < current:
                vol.SetMasterVolumeLevelScalar(target / 100.0, None)
        except Exception:
            self._pre_duck_volume = None

    def _restore_system_volume(self) -> None:
        """Restore the volume saved by _duck_system_volume."""
        level = self._pre_duck_volume
        self._pre_duck_volume = None
        if level is None:
            return
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices   = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            cast(interface, POINTER(IAudioEndpointVolume)).SetMasterVolumeLevelScalar(
                level / 100.0, None
            )
        except Exception:
            pass

    # ── Proactive speaking ────────────────────────────────────────────

    def _proactive_loop(self) -> None:
        """
        Drain the proactive speech queue without overlapping an active voice cycle.
        Waits for any in-progress cycle to finish, then claims the active slot
        before playing so no new cycle can start during proactive speech.
        """
        import time
        while not self._stop_event.is_set():
            try:
                text = self._proactive_q.get(timeout=1.0)
            except queue.Empty:
                continue
            # Wait for any active cycle to finish
            while not self._stop_event.is_set():
                with self._active_lock:
                    if not self._is_active:
                        break
                time.sleep(0.2)
            if self._stop_event.is_set():
                break
            # Claim the active slot
            with self._active_lock:
                if self._is_active:
                    # A new cycle snuck in — requeue and try again later
                    self._proactive_q.put(text)
                    continue
                self._is_active = True
            try:
                self._speak_proactive(text)
            finally:
                with self._active_lock:
                    self._is_active = False

    def _speak_proactive(self, text: str) -> None:
        """Speak a message outside of the normal voice cycle (e.g. reminder alerts)."""
        import time
        try:
            self._set_state("speaking")
            self._set_text(text[:120])
            if self._synthesize:
                self._duck_system_volume()
                try:
                    audio = self._synthesize(text)
                    self._speaker.speak(audio)
                finally:
                    self._restore_system_volume()
        except Exception as exc:
            logger.error("Proactive speech error: %s", exc)
        finally:
            time.sleep(0.5)
            self._set_state("idle")
            self._set_text("F.R.I.D.A.Y. ready")

    # ── Reminder polling ───────────────────────────────────────────────────

    def _reminder_poll_loop(self) -> None:
        """
        Background daemon: every 30 seconds check for reminders whose due_time
        has passed and speak them to the user.
        """
        import time
        import datetime
        # Stagger start so it doesn't fire immediately on launch
        time.sleep(10)
        while not self._stop_event.is_set():
            try:
                self._fire_due_reminders()
            except Exception as exc:
                logger.error("Reminder poll error: %s", exc)
            # Sleep in 1-second increments so stop_event is checked promptly
            for _ in range(30):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

    def _fire_due_reminders(self) -> None:
        """Check the DB and fire any reminders whose due_time has passed."""
        import datetime
        from storage.db import get_conn
        now = datetime.datetime.now()
        try:
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT id, text, due_time FROM reminders "
                    "WHERE done=0 AND due_time IS NOT NULL AND due_time != ''",
                ).fetchall()
        except Exception as exc:
            logger.error("Reminder DB read error: %s", exc)
            return

        for row in rows:
            try:
                due = datetime.datetime.fromisoformat(row["due_time"])
            except (ValueError, TypeError):
                continue  # unparseable timestamp — skip

            if due <= now:
                # Mark done immediately so it never fires twice
                try:
                    with get_conn() as conn:
                        conn.execute("UPDATE reminders SET done=1 WHERE id=?", (row["id"],))
                        conn.commit()
                except Exception as exc:
                    logger.error("Reminder mark-done error: %s", exc)
                    continue

                logger.info("Reminder fired: %s", row["text"])
                self._proactive_q.put(f"Sir, just a reminder: {row['text']}")

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
        logger.info("FridayEngine stopped")

    def trigger_listen(self):
        """Programmatically trigger one listen cycle (same as pressing hotkey)."""
        self._hotkey_triggered()

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

        wake_available = self._listener._wake_model is not None

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

            self._run_cycle()

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
        while not self._stop_event.is_set():
            try:
                detected = self._listener.wait_for_wake_word()
                if detected and not self._stop_event.is_set():
                    with self._active_lock:
                        if not self._is_active:
                            self._is_active = True
                            self._listen_q.put(True)
            except Exception as exc:
                logger.error("Wake word watcher error: %s", exc)
                import time
                time.sleep(1)

    def _run_cycle(self):
        """Execute one full listen → think → speak cycle."""
        import time

        try:
            # ── LISTENING ─────────────────────────────────────────────────
            self._set_state("listening")
            self._set_text("Listening...")
            self._listener.reset_stop()

            text = self._listener.listen_once(timeout=12.0)

            if not text.strip():
                logger.info("No speech detected or empty transcription")
                self._set_state("idle")
                self._set_text("F.R.I.D.A.Y. ready")
                with self._active_lock:
                    self._is_active = False
                return

            logger.info("User: %s", text)
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
            self._set_state("idle")
            self._set_text("F.R.I.D.A.Y. ready")
            with self._active_lock:
                self._is_active = False

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
            sentence_q.put(None)  # sentinel

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
                first = False
            self._speaker.speak(audio)

        t_stream.join(timeout=30)
        full_response = "".join(full_parts)

        if full_response.strip():
            logger.info("Friday: %s", full_response)
            self._set_text(full_response[:120])
        else:
            # Streaming yielded nothing — tool calls were made (AFC handles them
            # in non-streaming mode). Re-send via blocking chat().
            logger.info("Stream empty — falling back to blocking chat (tool call path)")
            response = self._ai.chat(user_text) or \
                "My AI uplink is unavailable at the moment, Sir."
            logger.info("Friday: %s", response)
            self._set_state("speaking")
            self._set_text(response[:120])
            if self._synthesize:
                try:
                    audio = self._synthesize(response)
                    self._speaker.speak(audio)
                except Exception as exc:
                    logger.error("TTS error: %s", exc)

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

    # ── Proactive speaking ─────────────────────────────────────────────────

    def _speak_proactive(self, text: str) -> None:
        """Speak a message outside of the normal voice cycle (e.g. reminder alerts)."""
        try:
            self._set_state("speaking")
            self._set_text(text[:120])
            if self._synthesize:
                audio = self._synthesize(text)
                self._speaker.speak(audio)
        except Exception as exc:
            logger.error("Proactive speech error: %s", exc)
        finally:
            import time
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
                self._speak_proactive(f"Sir, just a reminder: {row['text']}")

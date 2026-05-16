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

            # ── THINKING ──────────────────────────────────────────────────
            response = self._ai.chat(text)
            if not response:
                response = (
                    "My AI uplink is unavailable at the moment, Sir. "
                    "I can still handle local commands."
                )

            logger.info("Friday: %s", response)

            # ── SPEAKING ──────────────────────────────────────────────────
            self._set_state("speaking")
            self._set_text(response[:120])

            if self._synthesize:
                try:
                    audio = self._synthesize(response)
                    self._speaker.speak(audio)
                except Exception as exc:
                    logger.error("TTS error: %s", exc)

        except Exception as exc:
            logger.error("Voice cycle error: %s", exc)
        finally:
            self._set_state("idle")
            self._set_text("F.R.I.D.A.Y. ready")
            with self._active_lock:
                self._is_active = False

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

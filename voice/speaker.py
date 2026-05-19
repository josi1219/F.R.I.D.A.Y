"""
F.R.I.D.A.Y. — Voice Speaker
Plays TTS audio (mp3 BytesIO from edge-tts) via pygame.mixer.
Supports interruption: calling speak() while already speaking stops the
previous audio and starts the new one immediately.
"""

import io
import logging
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

try:
    import pygame
    pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=512)
    pygame.mixer.init()
    HAS_PYGAME = True
    logger.info("pygame.mixer ready")
except Exception as exc:
    HAS_PYGAME = False
    logger.warning("pygame not available — audio playback disabled: %s", exc)


class VoiceSpeaker:
    """
    Thread-safe audio player backed by pygame.mixer.
    Accepts a BytesIO mp3 buffer (from services.tts.synthesize) and plays it.
    """

    def __init__(self):
        self._lock      = threading.Lock()
        self._playing   = False
        self._stop_flag = threading.Event()

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def is_playing(self) -> bool:
        if not HAS_PYGAME:
            return False
        return self._playing and pygame.mixer.music.get_busy()

    def speak(self, audio: io.BytesIO) -> None:
        """
        Play the given mp3 BytesIO buffer.
        Stops any currently-playing audio first.
        Blocks until playback completes (call in a thread to keep it async).
        """
        if not HAS_PYGAME:
            logger.warning("pygame unavailable — cannot play audio")
            return

        self.stop()
        self._stop_flag.clear()

        with self._lock:
            tmp_path = None
            try:
                # Write to a named temp file — pygame.mixer.music.load needs a file
                audio.seek(0)
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp.write(audio.read())
                    tmp_path = tmp.name

                pygame.mixer.music.load(tmp_path)
                pygame.mixer.music.set_volume(1.0)
                pygame.mixer.music.play()
                self._playing = True

                # Wait for playback to finish or stop signal
                clock = pygame.time.Clock()
                while pygame.mixer.music.get_busy():
                    if self._stop_flag.is_set():
                        pygame.mixer.music.stop()
                        break
                    clock.tick(20)

            except Exception as exc:
                logger.error("Playback error: %s", exc)
            finally:
                self._playing = False
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

    def speak_async(self, audio: io.BytesIO) -> threading.Thread:
        """
        Non-blocking version — starts playback in a daemon thread.
        Returns the thread so caller can join if needed.
        """
        t = threading.Thread(target=self.speak, args=(audio,), daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        """Interrupt any current playback immediately."""
        if not HAS_PYGAME:
            return
        self._stop_flag.set()
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        except Exception:
            pass
        self._playing = False

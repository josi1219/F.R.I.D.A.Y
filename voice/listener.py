"""
F.R.I.D.A.Y. — Voice Listener
Continuous microphone input pipeline:
  sounddevice stream → VAD (energy threshold) → faster-whisper STT
  Optional: OpenWakeWord wake word detection ("hey_jarvis")
"""

import logging
import queue
import threading
import time
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

# ── Dependency guards ──────────────────────────────────────────────────────

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False
    logger.warning("sounddevice not installed — voice input unavailable")

try:
    from faster_whisper import WhisperModel
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False
    logger.warning("faster-whisper not installed — voice input unavailable")

try:
    import openwakeword
    from openwakeword.model import Model as WakeWordModel
    HAS_WAKE_WORD = True
except ImportError:
    HAS_WAKE_WORD = False
    logger.info("openwakeword not available — using hotkey only for activation")


# ── Constants ─────────────────────────────────────────────────────────────

SAMPLE_RATE   = 16000     # Hz — required by Whisper
CHANNELS      = 1
DTYPE         = "float32"
CHUNK_FRAMES  = 1024      # frames per sounddevice callback

# VAD parameters
VAD_THRESHOLD     = 0.015  # RMS energy level to detect speech start
SILENCE_THRESHOLD = 0.008  # RMS level considered silence
SPEECH_PAD_SECS   = 0.4    # seconds of audio to include before detected speech
SILENCE_SECS      = 1.2    # consecutive silence seconds to stop recording
MIN_SPEECH_SECS   = 0.3    # minimum speech duration to bother transcribing
MAX_SPEECH_SECS   = 30.0   # cap recording at 30 seconds


class VoiceListener:
    """
    Wraps a sounddevice input stream with:
      - Continuous VAD to detect when the user starts / stops speaking
      - faster-whisper transcription on each utterance
      - Optional OpenWakeWord wake-word detection before starting to listen
    """

    def __init__(self):
        self._whisper: "WhisperModel | None" = None
        self._wake_model: "WakeWordModel | None" = None
        self._ready = False
        self._stop_event = threading.Event()

        if not HAS_SOUNDDEVICE or not HAS_WHISPER:
            logger.error("Voice listener cannot start — missing dependencies")
            return

        self._load_whisper()
        self._load_wake_word()
        self._ready = True

    # ── Setup ──────────────────────────────────────────────────────────────

    def _load_whisper(self):
        model_name = getattr(config, "WHISPER_MODEL", "base.en")
        logger.info("Loading faster-whisper model '%s' (first run downloads ~74 MB)...", model_name)
        try:
            self._whisper = WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8",
            )
            logger.info("faster-whisper ready")
        except Exception as exc:
            logger.error("Failed to load Whisper model: %s", exc)
            self._whisper = None

    def _load_wake_word(self):
        if not HAS_WAKE_WORD:
            return
        model_name = getattr(config, "WAKE_WORD_MODEL", "hey_jarvis")
        try:
            logger.info("Loading OpenWakeWord model '%s'...", model_name)
            self._wake_model = WakeWordModel(
                wakeword_models=[model_name],
                inference_framework="onnx",
            )
            logger.info("Wake word '%s' ready", model_name)
        except Exception as exc:
            logger.warning("Wake word model failed to load (%s) — hotkey only", exc)
            self._wake_model = None

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def ready(self) -> bool:
        return self._ready and self._whisper is not None

    def stop(self):
        """Signal any blocking listen call to abort."""
        self._stop_event.set()

    def reset_stop(self):
        self._stop_event.clear()

    def listen_once(self, timeout: float = 15.0) -> str:
        """
        Record one utterance and return the transcribed text.
        Blocks until speech is detected and the user stops speaking,
        or until timeout seconds have elapsed.
        Returns empty string if nothing was captured.
        """
        if not self.ready:
            return ""

        self._stop_event.clear()
        audio_buffer = []
        pre_buffer   = []  # ring buffer for audio before speech detected
        pre_max      = int(SAMPLE_RATE * SPEECH_PAD_SECS / CHUNK_FRAMES) + 1

        state = "waiting"  # waiting | recording | done
        silence_chunks = 0
        silence_limit  = int(SILENCE_SECS * SAMPLE_RATE / CHUNK_FRAMES)
        max_chunks     = int(MAX_SPEECH_SECS * SAMPLE_RATE / CHUNK_FRAMES)
        chunk_q: queue.Queue = queue.Queue()

        def callback(indata, frames, time_info, status):
            chunk_q.put(indata.copy())

        start = time.time()
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=CHUNK_FRAMES,
            callback=callback,
        )

        with stream:
            while not self._stop_event.is_set():
                if time.time() - start > timeout:
                    break
                try:
                    chunk = chunk_q.get(timeout=0.1)
                except queue.Empty:
                    continue

                mono = chunk[:, 0] if chunk.ndim > 1 else chunk
                rms  = float(np.sqrt(np.mean(mono ** 2)))

                if state == "waiting":
                    pre_buffer.append(mono)
                    if len(pre_buffer) > pre_max:
                        pre_buffer.pop(0)
                    if rms > VAD_THRESHOLD:
                        state = "recording"
                        audio_buffer = list(pre_buffer)
                        audio_buffer.append(mono)
                        silence_chunks = 0

                elif state == "recording":
                    audio_buffer.append(mono)
                    if rms < SILENCE_THRESHOLD:
                        silence_chunks += 1
                        if silence_chunks >= silence_limit:
                            state = "done"
                            break
                    else:
                        silence_chunks = 0
                    if len(audio_buffer) >= max_chunks:
                        state = "done"
                        break

        if state not in ("recording", "done") or not audio_buffer:
            return ""

        duration = len(audio_buffer) * CHUNK_FRAMES / SAMPLE_RATE
        if duration < MIN_SPEECH_SECS:
            return ""

        return self._transcribe(np.concatenate(audio_buffer))

    def wait_for_wake_word(self, timeout: float = 0.0) -> bool:
        """
        Block until the configured wake word is detected.
        Returns True when wake word is heard, False on timeout/stop.
        timeout=0 means wait forever.
        """
        if not self.ready or self._wake_model is None:
            # No wake word model — caller falls back to hotkey
            return False

        self._stop_event.clear()
        chunk_q: queue.Queue = queue.Queue()
        start = time.time()

        # Wake word model expects 16-bit int16 chunks of exactly 1280 samples
        WAKE_CHUNK = 1280

        def callback(indata, frames, time_info, status):
            chunk_q.put(indata.copy())

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=WAKE_CHUNK,
            callback=callback,
        )

        with stream:
            while not self._stop_event.is_set():
                if timeout > 0 and time.time() - start > timeout:
                    return False
                try:
                    chunk = chunk_q.get(timeout=0.2)
                except queue.Empty:
                    continue

                mono = chunk[:, 0] if chunk.ndim > 1 else chunk
                try:
                    preds = self._wake_model.predict(mono)
                    model_name = getattr(config, "WAKE_WORD_MODEL", "hey_jarvis")
                    score = preds.get(model_name, 0.0)
                    if score > 0.5:
                        logger.info("Wake word detected (score=%.2f)", score)
                        return True
                except Exception:
                    pass
        return False

    def listen_continuous(self, callback, use_wake_word: bool = True):
        """
        Run a background thread that continuously listens.
        Calls callback(text: str) on each detected utterance.
        Stops when stop() is called.
        """
        if not self.ready:
            logger.warning("VoiceListener not ready — continuous mode skipped")
            return

        def _loop():
            self._stop_event.clear()
            while not self._stop_event.is_set():
                if use_wake_word and self._wake_model is not None:
                    detected = self.wait_for_wake_word()
                    if not detected:
                        continue
                text = self.listen_once(timeout=12.0)
                if text.strip():
                    logger.info("Transcribed: %s", text)
                    try:
                        callback(text.strip())
                    except Exception as exc:
                        logger.error("Voice callback error: %s", exc)

        t = threading.Thread(target=_loop, name="VoiceListener", daemon=True)
        t.start()
        return t

    # ── Internal ────────────────────────────────────────────────────────────

    def _transcribe(self, audio: np.ndarray) -> str:
        """Run faster-whisper on a float32 numpy array at 16kHz."""
        try:
            segments, info = self._whisper.transcribe(
                audio,
                language="en",
                beam_size=3,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
            )
            text = " ".join(seg.text.strip() for seg in segments)
            return text.strip()
        except Exception as exc:
            logger.error("Whisper transcription error: %s", exc)
            return ""

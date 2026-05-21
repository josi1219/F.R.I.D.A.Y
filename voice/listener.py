"""
F.R.I.D.A.Y. — Voice Listener
Continuous microphone input pipeline:
  sounddevice stream → VAD (energy threshold) → faster-whisper STT
  Optional: OpenWakeWord wake word detection ("hey_jarvis")
"""

import io
import logging
import queue
import threading
import time
import wave
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
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logger.warning("requests not installed — online STT unavailable")

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

# VAD parameters — defaults from config (tunable via .env)
VAD_THRESHOLD     = getattr(config, "VAD_THRESHOLD",         0.005)  # RMS energy level to detect speech start
SILENCE_THRESHOLD = getattr(config, "VAD_SILENCE_THRESHOLD", 0.003)  # RMS level considered silence
SPEECH_PAD_SECS   = 0.4    # seconds of audio to include before detected speech
SILENCE_SECS      = 0.7    # consecutive silence seconds to stop recording
MIN_SPEECH_SECS   = 0.15   # minimum speech duration to bother transcribing
MAX_SPEECH_SECS   = 60.0   # cap recording at 60 seconds

# Wake keyword spotter parameters
WAKE_KEYWORD       = getattr(config, "WAKE_KEYWORD",       "friday").lower()
WAKE_VAD_THRESHOLD = getattr(config, "WAKE_VAD_THRESHOLD", 0.001)   # ultra-sensitive for wake detection


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
        self._stt_provider = getattr(config, "STT_PROVIDER", "whisper").lower()

        if not HAS_SOUNDDEVICE:
            logger.error("Voice listener cannot start — sounddevice not installed")
            return

        if self._stt_provider == "whisper":
            if not HAS_WHISPER:
                logger.error("Voice listener cannot start — faster-whisper not installed")
                return
            self._load_whisper()
        else:
            logger.info("STT provider: %s (online mode)", self._stt_provider)

        self._load_wake_word()
        self._ready = True

    # ── Setup ──────────────────────────────────────────────────────────────

    def _load_whisper(self):
        model_name   = getattr(config, "WHISPER_MODEL",  "tiny.en")
        device       = getattr(config, "WHISPER_DEVICE", "cpu")
        compute_type = "int8"  # best quantisation for CPU
        logger.info("Loading faster-whisper '%s' on %s...", model_name, device)
        try:
            self._whisper = WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
            )
            logger.info("faster-whisper ready (%s / %s)", model_name, device)
        except Exception as exc:
            logger.error("Failed to load Whisper model: %s", exc)
            self._whisper = None

    def _load_wake_word(self):
        if not HAS_WAKE_WORD:
            return
        model_name = getattr(config, "WAKE_WORD_MODEL", "hey_jarvis")

        def _try_load():
            return WakeWordModel(
                wakeword_models=[model_name],
                inference_framework="onnx",
            )

        def _download_and_load():
            """Background thread: download model then swap it in."""
            try:
                logger.info("Wake word model not found — downloading '%s' in background...", model_name)
                import openwakeword as _oww
                # Download all models (no-arg call) so the shared embedding_model.onnx
                # is included — downloading only by model name skips it.
                _oww.utils.download_models()
                self._wake_model = _try_load()
                logger.info("Wake word '%s' downloaded and ready", model_name)
            except Exception as dl_exc:
                logger.warning("Wake word model download failed (%s) — hotkey only", dl_exc)

        try:
            logger.info("Loading OpenWakeWord model '%s'...", model_name)
            self._wake_model = _try_load()
            logger.info("Wake word '%s' ready", model_name)
        except Exception as exc:
            exc_str = str(exc).lower()
            # Model file missing — kick off a background download so startup isn't blocked
            if any(x in exc_str for x in ("no_suchfile", "no such file", "file doesn't exist", "doesn't exist")):
                logger.warning("Wake word model missing — starting background download (hotkey active meanwhile)")
                t = threading.Thread(target=_download_and_load, daemon=True)
                t.start()
            else:
                logger.warning("Wake word model failed to load (%s) — hotkey only", exc)
            self._wake_model = None

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def ready(self) -> bool:
        if self._stt_provider == "whisper":
            return self._ready and self._whisper is not None
        return self._ready

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
        Block until the wake keyword is heard in any phrase.
        Uses STT-based keyword spotter when WAKE_KEYWORD is set —
        any phrase containing the keyword triggers wake-up, e.g.:
          'hey friday', 'chop chop friday', 'yo friday', just 'friday'.
        Falls back to OpenWakeWord model if no keyword / STT is available.
        Returns True when detected, False on timeout/stop.
        """
        if not self.ready:
            return False

        # Use STT keyword spotter when WAKE_KEYWORD is set and STT is available
        stt_ok = (
            (self._whisper is not None)                           # local Whisper loaded
            or (bool(getattr(config, "GROQ_API_KEY", "")) and HAS_REQUESTS)  # Groq online
            or bool(getattr(config, "DEEPGRAM_API_KEY", ""))      # Deepgram online
        )
        if WAKE_KEYWORD and stt_ok:
            self._stop_event.clear()
            return self._wait_for_keyword(timeout)

        # Fallback: OpenWakeWord model
        if self._wake_model is None:
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
            # ── Flush stale mic buffer on stream open ──────────────────────
            # Without this, audio buffered while _is_active was True (the user
            # saying "hey jarvis" repeatedly while Friday was busy) feeds into
            # the model the instant the stream opens → immediate false trigger.
            flush_chunks = int(0.75 * SAMPLE_RATE / WAKE_CHUNK)  # ~9 chunks
            flushed = 0
            while flushed < flush_chunks and not self._stop_event.is_set():
                try:
                    chunk_q.get(timeout=0.1)
                    flushed += 1
                except queue.Empty:
                    break

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
                    # Use max score across all models — robust against key name variations
                    # (e.g. "hey_jarvis" vs "hey_jarvis_v0.1")
                    score = max(preds.values()) if preds else 0.0
                    if score > 0.6:
                        logger.info("Wake word detected (score=%.2f)", score)
                        return True
                except Exception:
                    pass
        return False

    def _wait_for_keyword(self, timeout: float = 0.0) -> bool:
        """
        Ultra-sensitive STT-based keyword spotter.
        Continuously records audio bursts above WAKE_VAD_THRESHOLD and checks
        whether Groq Whisper's transcription contains WAKE_KEYWORD.
        Any phrase with the keyword wakes FRIDAY regardless of surrounding words.
        """
        min_chunks    = int(0.40 * SAMPLE_RATE / CHUNK_FRAMES)   # skip clips < 0.4s  (noise/echo)
        max_chunks    = int(2.5  * SAMPLE_RATE / CHUNK_FRAMES)   # cap at 2.5s for fast turnaround
        silence_limit = int(0.4  * SAMPLE_RATE / CHUNK_FRAMES)   # 0.4s silence = end of clip
        # Minimum average RMS for the full clip — below this it's ambient noise, not real speech
        MIN_CLIP_RMS  = 0.004

        start   = time.time()
        chunk_q: queue.Queue = queue.Queue()

        def callback(indata, frames, time_info, status):
            chunk_q.put(indata.copy())

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=CHUNK_FRAMES,
            callback=callback,
        )

        with stream:
            # ── Flush 1 second of stale audio on startup ──────────────────
            # Prevents re-triggering on residual mic audio from the previous
            # utterance (e.g. "friday sleep" echoing into the new stream).
            flush_target = int(1.0 * SAMPLE_RATE / CHUNK_FRAMES)
            flushed = 0
            while flushed < flush_target and not self._stop_event.is_set():
                try:
                    chunk_q.get(timeout=0.1)
                    flushed += 1
                except queue.Empty:
                    break

            while not self._stop_event.is_set():
                if timeout > 0 and time.time() - start > timeout:
                    return False

                # Wait for an energy burst above the ultra-sensitive wake threshold
                try:
                    chunk = chunk_q.get(timeout=0.1)
                except queue.Empty:
                    continue

                mono = chunk[:, 0] if chunk.ndim > 1 else chunk
                rms  = float(np.sqrt(np.mean(mono ** 2)))

                if rms < WAKE_VAD_THRESHOLD:
                    continue  # silence — keep scanning

                # Energy detected — collect the full burst
                audio_buf      = [mono]
                silence_chunks = 0

                while not self._stop_event.is_set() and len(audio_buf) < max_chunks:
                    try:
                        chunk = chunk_q.get(timeout=0.1)
                    except queue.Empty:
                        break
                    mono = chunk[:, 0] if chunk.ndim > 1 else chunk
                    rms  = float(np.sqrt(np.mean(mono ** 2)))
                    audio_buf.append(mono)
                    if rms < SILENCE_THRESHOLD:
                        silence_chunks += 1
                        if silence_chunks >= silence_limit:
                            break
                    else:
                        silence_chunks = 0

                # Skip clips that are too short — likely noise bursts
                if len(audio_buf) < min_chunks:
                    continue

                # Skip clips with insufficient average energy — ambient noise, not speech
                audio = np.concatenate(audio_buf)
                if float(np.sqrt(np.mean(audio ** 2))) < MIN_CLIP_RMS:
                    continue

                # Transcribe with configured STT provider (Whisper / Groq / Deepgram)
                try:
                    text = self._transcribe(audio).lower().strip()
                except Exception:
                    continue

                if WAKE_KEYWORD in text:
                    logger.info("Wake keyword %r detected in: %r", WAKE_KEYWORD, text)
                    return True

                # Not a match — drain stale queue backlog and keep listening
                while not chunk_q.empty():
                    try:
                        chunk_q.get_nowait()
                    except queue.Empty:
                        break

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
        """Route transcription to the configured STT provider."""
        if self._stt_provider == "groq":
            return self._transcribe_groq(audio)
        elif self._stt_provider == "deepgram":
            return self._transcribe_deepgram(audio)
        return self._transcribe_whisper(audio)

    def _transcribe_whisper(self, audio: np.ndarray) -> str:
        """Run faster-whisper locally on a float32 numpy array at 16kHz."""
        try:
            segments, _info = self._whisper.transcribe(
                audio,
                language="en",
                beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 200},
            )
            text = " ".join(seg.text.strip() for seg in segments)
            return text.strip()
        except Exception as exc:
            logger.error("Whisper transcription error: %s", exc)
            return ""

    def _to_wav_bytes(self, audio: np.ndarray) -> io.BytesIO:
        """Convert float32 numpy audio to a WAV BytesIO buffer."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes((audio * 32767).astype(np.int16).tobytes())
        buf.seek(0)
        return buf

    def _transcribe_groq(self, audio: np.ndarray) -> str:
        """Send audio to Groq Whisper API and return transcript."""
        if not HAS_REQUESTS:
            logger.error("requests not installed — cannot use Groq STT")
            return ""
        api_key = getattr(config, "GROQ_API_KEY", "")
        if not api_key:
            logger.error("GROQ_API_KEY not set — cannot use Groq STT")
            return ""
        model = getattr(config, "GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
        buf = self._to_wav_bytes(audio)
        try:
            resp = _requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": ("audio.wav", buf, "audio/wav")},
                data={"model": model, "language": "en"},
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json().get("text", "").strip()
        except Exception as exc:
            logger.error("Groq STT error: %s", exc)
            return ""

    def _transcribe_deepgram(self, audio: np.ndarray) -> str:
        """Send audio to Deepgram Nova API and return transcript."""
        if not HAS_REQUESTS:
            logger.error("requests not installed — cannot use Deepgram STT")
            return ""
        api_key = getattr(config, "DEEPGRAM_API_KEY", "")
        if not api_key:
            logger.error("DEEPGRAM_API_KEY not set — cannot use Deepgram STT")
            return ""
        model = getattr(config, "DEEPGRAM_MODEL", "nova-3")
        buf = self._to_wav_bytes(audio)
        try:
            resp = _requests.post(
                f"https://api.deepgram.com/v1/listen?model={model}&language=en&smart_format=true",
                headers={
                    "Authorization": f"Token {api_key}",
                    "Content-Type": "audio/wav",
                },
                data=buf.read(),
                timeout=20,
            )
            resp.raise_for_status()
            channels = resp.json()["results"]["channels"]
            return channels[0]["alternatives"][0]["transcript"].strip()
        except Exception as exc:
            logger.error("Deepgram STT error: %s", exc)
            return ""

"""
F.R.I.D.A.Y. — Screen Analyzer
Sends a screenshot to Gemini Vision and returns the analysis.
Uses the same google-genai client that powers the AI conversation.
"""

import io
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vision.capture import capture_screen

logger = logging.getLogger(__name__)

try:
    from google.genai import types as genai_types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


class ScreenAnalyzer:
    """
    Analyzes the current screen using Gemini Vision.
    Requires a google-genai Client instance and a model that supports multimodal input.
    """

    def __init__(self, client, model_name: str = "gemini-2.0-flash"):
        self._client     = client
        self._model_name = model_name
        self._enabled    = client is not None and HAS_GENAI

    # ── Helpers ────────────────────────────────────────────────────────────

    def _capture_jpeg_bytes(self) -> bytes | None:
        """Capture the screen and return raw JPEG bytes (no base64), or None on failure."""
        img = capture_screen()
        if img is None:
            return None
        max_dim = 1280
        if max(img.width, img.height) > max_dim:
            from PIL import Image
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    def _build_content(self, img_bytes: bytes, text: str):
        """Wrap image + text into a single user Content turn (required for SDK 1.x)."""
        image_part = genai_types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
        text_part  = genai_types.Part.from_text(text=text)
        return genai_types.Content(role="user", parts=[image_part, text_part])

    # ── Public API ─────────────────────────────────────────────────────────

    def analyze(self, question: str = "Describe in detail what you see on the screen.") -> str:
        """
        Capture the current screen and ask Gemini Vision the given question.
        Returns Gemini's text response.
        Raises on API errors so the caller can handle key rotation.
        """
        if not self._enabled:
            return "Screen vision is unavailable — Gemini client not initialised."

        img_bytes = self._capture_jpeg_bytes()
        if img_bytes is None:
            return "Screen capture failed — mss or Pillow may not be installed."

        prompt = (
            "You are FRIDAY, analyzing a screenshot of the user's PC screen. "
            f"Answer this question about the screen: {question}\n"
            "Be concise and factual. Describe what is actually visible. "
            "No markdown, no bullet points."
        )
        content = self._build_content(img_bytes, prompt)
        # No try/except — let API errors propagate for key rotation in tools.py
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=[content],
        )
        return (response.text or "").strip()

    def find_element(self, description: str) -> dict:
        """
        Ask Gemini Vision to locate a described UI element on screen.
        Returns a dict with 'x', 'y', 'w', 'h', 'found' keys.
        Raises on API errors so the caller can handle key rotation.
        """
        if not self._enabled:
            return {"found": False, "error": "Vision unavailable"}

        # Single capture — reuse for both bytes and dimension reporting
        img = capture_screen()
        if img is None:
            return {"found": False, "error": "Capture failed"}
        sw, sh = img.width, img.height
        buf = io.BytesIO()
        max_dim = 1280
        if max(sw, sh) > max_dim:
            from PIL import Image as _PIL
            img.thumbnail((max_dim, max_dim), _PIL.LANCZOS)
        img.save(buf, format="JPEG", quality=85)
        img_bytes = buf.getvalue()

        prompt = (
            f"Look at this screenshot ({sw}x{sh} pixels). "
            f"Find the UI element described as: '{description}'. "
            'Respond with ONLY a JSON object: {"found": true, "x": <px>, "y": <px>, "w": <px>, "h": <px>} '
            'or {"found": false} if not visible. No other text.'
        )
        content = self._build_content(img_bytes, prompt)
        # No try/except — let API errors propagate for key rotation in tools.py
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=[content],
        )
        raw = (response.text or "").strip().strip("`").replace("json", "", 1).strip()
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            # Gemini returned prose instead of JSON (e.g. element not found)
            return {"found": False}

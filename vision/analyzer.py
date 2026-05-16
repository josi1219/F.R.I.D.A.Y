"""
F.R.I.D.A.Y. — Screen Analyzer
Sends a screenshot to Gemini Vision and returns the analysis.
Uses the same google-genai client that powers the AI conversation.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vision.capture import capture_screen, image_to_base64

logger = logging.getLogger(__name__)

try:
    from google.genai import types as genai_types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


class ScreenAnalyzer:
    """
    Analyzes the current screen using Gemini Vision.
    Requires a google-genai Client instance and a model that supports multimodal input
    (e.g. gemini-2.0-flash).
    """

    def __init__(self, client, model_name: str = "gemini-2.0-flash"):
        self._client     = client
        self._model_name = model_name
        self._enabled    = client is not None and HAS_GENAI

    # ── Public API ─────────────────────────────────────────────────────────

    def analyze(self, question: str = "Describe in detail what you see on the screen.") -> str:
        """
        Capture the current screen and ask Gemini Vision the given question.
        Returns Gemini's text response, or an error string.
        """
        if not self._enabled:
            return "Screen vision is unavailable — Gemini client not initialised."

        img = capture_screen()
        if img is None:
            return "Screen capture failed — mss or Pillow may not be installed."

        b64 = image_to_base64(img)

        try:
            image_part = genai_types.Part.from_bytes(
                data=__import__("base64").b64decode(b64),
                mime_type="image/jpeg",
            )
            text_part = genai_types.Part.from_text(
                text=(
                    "You are F.R.I.D.A.Y., analyzing a screenshot of the user's PC screen. "
                    f"Answer this question about the screen: {question}\n"
                    "Be concise and factual. Describe what is actually visible. "
                    "No markdown, no bullet points."
                )
            )
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=[image_part, text_part],
            )
            return (response.text or "").strip()
        except Exception as exc:
            logger.error("Gemini Vision error: %s", exc)
            return f"Screen analysis failed: {exc}"

    def find_element(self, description: str) -> dict:
        """
        Ask Gemini Vision to locate a described UI element on screen.
        Returns a dict with 'x', 'y', 'w', 'h', 'found' keys.
        Coordinates are absolute screen pixels.
        """
        if not self._enabled:
            return {"found": False, "error": "Vision unavailable"}

        img = capture_screen()
        if img is None:
            return {"found": False, "error": "Capture failed"}

        b64 = image_to_base64(img)
        sw, sh = img.width, img.height

        prompt = (
            f"Look at this screenshot ({sw}x{sh} pixels). "
            f"Find the UI element described as: '{description}'. "
            "Respond with ONLY a JSON object in this exact format: "
            '{"found": true, "x": <left_px>, "y": <top_px>, "w": <width_px>, "h": <height_px>} '
            "or {\"found\": false} if not visible. No other text."
        )

        try:
            image_part = genai_types.Part.from_bytes(
                data=__import__("base64").b64decode(b64),
                mime_type="image/jpeg",
            )
            text_part = genai_types.Part.from_text(text=prompt)
            response  = self._client.models.generate_content(
                model=self._model_name,
                contents=[image_part, text_part],
            )
            raw = (response.text or "").strip()
            # Strip markdown fences if present
            raw = raw.strip("`").replace("json", "", 1).strip()
            import json
            return json.loads(raw)
        except Exception as exc:
            logger.error("Element find error: %s", exc)
            return {"found": False, "error": str(exc)}

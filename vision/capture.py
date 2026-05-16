"""
F.R.I.D.A.Y. — Screen Capture
Uses mss for fast full-screen capture, outputs PIL Images and base64 strings.
"""

import base64
import io
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

try:
    import mss
    import mss.tools
    HAS_MSS = True
except ImportError:
    HAS_MSS = False
    logger.warning("mss not installed — screen capture unavailable")

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    logger.warning("Pillow not installed — screen capture unavailable")


def capture_screen() -> "Image.Image | None":
    """
    Capture the entire primary screen.
    Returns a PIL Image, or None on failure.
    """
    if not HAS_MSS or not HAS_PIL:
        return None
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]   # index 1 = primary monitor
            raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        return img
    except Exception as exc:
        logger.error("Screen capture failed: %s", exc)
        return None


def capture_region(x: int, y: int, w: int, h: int) -> "Image.Image | None":
    """
    Capture a specific rectangular region of the screen.
    Returns a PIL Image, or None on failure.
    """
    if not HAS_MSS or not HAS_PIL:
        return None
    try:
        with mss.mss() as sct:
            region = {"top": y, "left": x, "width": w, "height": h}
            raw = sct.grab(region)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        return img
    except Exception as exc:
        logger.error("Region capture failed: %s", exc)
        return None


def image_to_base64(img: "Image.Image", quality: int = 85) -> str:
    """
    Encode a PIL Image to a JPEG base64 string suitable for Gemini Vision.
    """
    buf = io.BytesIO()
    # Resize if very large to keep API payload manageable
    max_dim = 1280
    if max(img.width, img.height) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def save_temp_screenshot() -> str:
    """
    Capture the screen and save it to a temp file.
    Returns the file path, or empty string on failure.
    """
    img = capture_screen()
    if img is None:
        return ""
    try:
        tmp = tempfile.NamedTemporaryFile(
            suffix=".jpg", delete=False, prefix="friday_screen_"
        )
        img.save(tmp.name, format="JPEG", quality=85)
        tmp.close()
        return tmp.name
    except Exception as exc:
        logger.error("Failed to save screenshot: %s", exc)
        return ""

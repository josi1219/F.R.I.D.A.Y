"""
F.R.I.D.A.Y. — Overlay Launcher
Replaces run_desktop.py for the full voice + vision + overlay experience.

What it does:
  1. Starts Flask in a background thread (existing chat UI at :5000 still works)
  2. Starts the PyQt6 application
  3. Creates the transparent overlay and annotation layer
  4. Boots FridayEngine (voice pipeline, hotkey, wake word)
  5. Enters the Qt event loop

Hotkey: Ctrl+Alt+F  →  activate Friday to listen
Wake word: "hey jarvis"  →  activate Friday to listen (if openwakeword installed)
"""

import logging
import sys
import threading
import time
import os

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)

import config
from app import app as flask_app
from services.ai import FridayAI
from storage import init_db

PORT = 5000


# ── Flask thread ──────────────────────────────────────────────────────────

def _run_flask():
    flask_app.run(
        host='127.0.0.1',
        port=PORT,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("  F.R.I.D.A.Y.  —  Voice + Vision + Overlay Edition")
    print("  Hotkey : Ctrl+Alt+F  (activate listening)")
    print("  Wake   : 'hey jarvis' (if openwakeword installed)")
    print("  Web UI : http://127.0.0.1:5000")
    print("=" * 60 + "\n")

    # ── Init storage ─────────────────────────────────────────────────────
    init_db()

    # ── Init Gemini AI ───────────────────────────────────────────────────
    ai = FridayAI(api_key=config.GEMINI_API_KEY, model_name=config.GEMINI_MODEL)

    # ── Start Flask in background ─────────────────────────────────────────
    flask_thread = threading.Thread(target=_run_flask, name="Flask", daemon=True)
    flask_thread.start()
    time.sleep(1.0)   # give Flask time to bind
    logger.info("Flask running on http://127.0.0.1:%d", PORT)

    # ── Boot PyQt6 ───────────────────────────────────────────────────────
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QTimer
    except ImportError:
        logger.error(
            "PyQt6 not installed.\n"
            "Run:  .\\venv\\Scripts\\pip install PyQt6\n"
            "Then restart run_overlay.py"
        )
        sys.exit(1)

    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)

    # ── Create overlay windows ───────────────────────────────────────────
    from overlay.window import FridayOverlay, AnnotationOverlay, HAS_QT

    if not HAS_QT:
        logger.error("PyQt6 import failed inside overlay/window.py — aborting")
        sys.exit(1)

    overlay      = FridayOverlay()
    ann_overlay  = AnnotationOverlay()
    overlay.show()
    ann_overlay.show()

    # ── Start engine ─────────────────────────────────────────────────────
    from engine import FridayEngine

    engine = FridayEngine(ai=ai, overlay=overlay, annotation_overlay=ann_overlay)

    # Expose engine + ann_overlay to tools so they can trigger annotations
    import services.tools as tools_module
    tools_module._engine        = engine
    tools_module._ann_overlay   = ann_overlay

    # Delay engine start slightly so Qt event loop is running first
    QTimer.singleShot(500, engine.start)

    logger.info("Overlay ready — press Ctrl+Alt+F or say 'hey jarvis' to activate")

    # ── Qt event loop (blocks until window is closed) ────────────────────
    ret = qt_app.exec()

    engine.stop()
    sys.exit(ret)

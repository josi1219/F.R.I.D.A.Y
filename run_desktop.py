"""
F.R.I.D.A.Y. — Desktop Launcher
Wraps the Flask app in a native window using pywebview.
Run this instead of run_friday.bat for a native desktop app feel.
"""

import threading
import time
import webview
from app import app

PORT = 5000


def _run_server():
    app.run(host='127.0.0.1', port=PORT, debug=False, use_reloader=False, threaded=True)


if __name__ == '__main__':
    t = threading.Thread(target=_run_server, daemon=True)
    t.start()
    # Give Flask a moment to bind
    time.sleep(1.2)

    webview.create_window(
        title='F.R.I.D.A.Y.',
        url=f'http://127.0.0.1:{PORT}',
        width=1280,
        height=820,
        resizable=True,
        min_size=(900, 600),
    )
    webview.start()

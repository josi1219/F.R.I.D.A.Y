"""
F.R.I.D.A.Y. — Windows Toast Notifications
Thin wrapper over win11toast with a graceful fallback.
Usage:
    from services.toast import toast
    toast("Reminder", "Stand up and stretch, Sir.")
"""

import logging
import threading

logger = logging.getLogger(__name__)

try:
    from win11toast import toast as _win11toast, notify as _win11notify
    HAS_WIN11TOAST = True
except ImportError:
    HAS_WIN11TOAST = False
    logger.warning("win11toast not installed — toast notifications disabled. Run: pip install win11toast")


def toast(title: str, body: str, icon: str | None = None, duration: str = "short") -> None:
    """
    Fire-and-forget Windows 11 toast notification.
    Non-blocking — runs in a daemon thread.
    Falls back silently if win11toast is unavailable.
    """
    if not HAS_WIN11TOAST:
        return

    def _send():
        try:
            kwargs: dict = {"duration": duration}
            if icon:
                kwargs["icon"] = icon
            _win11toast(title, body, **kwargs)
        except Exception as exc:
            logger.debug("Toast failed: %s", exc)

    t = threading.Thread(target=_send, daemon=True)
    t.start()


def toast_reminder(text: str) -> None:
    toast("F.R.I.D.A.Y. — Reminder", text, duration="long")


def toast_alert(text: str) -> None:
    toast("F.R.I.D.A.Y. — Alert", text, duration="long")


def toast_info(text: str) -> None:
    toast("F.R.I.D.A.Y.", text, duration="short")

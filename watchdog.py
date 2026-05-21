"""
F.R.I.D.A.Y. — Watchdog
Keeps run_overlay.py alive indefinitely for 24/7 operation.

Usage:
    python watchdog.py          # foreground, Ctrl+C to stop
    pythonw watchdog.py         # background (no console window)

Behaviour:
  - Launches run_overlay.py as a child process and waits for it
  - Clean exit (code 0): FRIDAY was intentionally closed — watchdog stops too
  - Any other exit code: wait RESTART_DELAY seconds, then restart
  - Crash-loop protection: if it crashes MAX_RESTARTS_PER_HOUR times in an hour,
    the watchdog pauses 5 minutes before retrying (then clears the counter)
  - All events are logged to friday_watchdog.log next to this file
"""

import logging
import os
import subprocess
import sys
import time

# ── Config ────────────────────────────────────────────────────────────────────
_BASE               = os.path.dirname(os.path.abspath(__file__))
SCRIPT              = os.path.join(_BASE, "run_overlay.py")
LOG_FILE            = os.path.join(_BASE, "friday_watchdog.log")
RESTART_DELAY_SECS  = 5
MAX_RESTARTS_PER_HOUR = 10
CRASH_PAUSE_SECS    = 300  # 5 minutes

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("friday.watchdog")


def run() -> None:
    restart_times: list[float] = []
    attempt = 0

    while True:
        # ── Crash-loop protection ─────────────────────────────────────────────
        now = time.time()
        restart_times = [t for t in restart_times if now - t < 3600]

        if len(restart_times) >= MAX_RESTARTS_PER_HOUR:
            logger.error(
                "FRIDAY crashed %d times in the last hour — "
                "pausing %d s before retrying.",
                MAX_RESTARTS_PER_HOUR, CRASH_PAUSE_SECS,
            )
            try:
                time.sleep(CRASH_PAUSE_SECS)
            except KeyboardInterrupt:
                logger.info("Watchdog stopped by user during pause.")
                return
            restart_times.clear()
            continue

        # ── Launch ────────────────────────────────────────────────────────────
        attempt += 1
        logger.info("Starting FRIDAY (attempt #%d): %s", attempt, SCRIPT)

        exit_code = -1
        try:
            proc = subprocess.Popen(
                [sys.executable, SCRIPT],
                cwd=_BASE,
            )
            proc.wait()
            exit_code = proc.returncode
        except KeyboardInterrupt:
            logger.info("Watchdog stopped by user (Ctrl+C).")
            try:
                proc.terminate()
            except Exception:
                pass
            return
        except Exception as exc:
            logger.error("Failed to launch FRIDAY: %s", exc)

        # ── React to exit ─────────────────────────────────────────────────────
        if exit_code == 0:
            logger.info("FRIDAY exited cleanly (code 0) — watchdog stopping.")
            return

        restart_times.append(time.time())
        logger.warning(
            "FRIDAY exited with code %d — restarting in %d s …",
            exit_code, RESTART_DELAY_SECS,
        )
        try:
            time.sleep(RESTART_DELAY_SECS)
        except KeyboardInterrupt:
            logger.info("Watchdog stopped by user during restart delay.")
            return


if __name__ == "__main__":
    print("=" * 60)
    print("  F.R.I.D.A.Y. Watchdog  —  24/7 Auto-Restart Monitor")
    print(f"  Log : {LOG_FILE}")
    print("  Stop: Ctrl+C")
    print("=" * 60 + "\n")
    run()

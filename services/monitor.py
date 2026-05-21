"""
F.R.I.D.A.Y. — Proactive Background Monitor
Runs silently in a daemon thread, watching for conditions that warrant
interrupting the user with a spoken alert + toast notification.

Monitors:
  - CPU / RAM spikes
  - Active work session duration → break suggestions
  - Stock / crypto watchlist price movements
  - Reminder firing (enhanced — toast + voice)
  - Low battery warning

The monitor is started by FridayEngine.start() and calls back into the engine's
proactive speech queue so alerts are spoken at the right time (not mid-sentence).
"""

import logging
import threading
import time
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

# ── Optional dependencies ─────────────────────────────────────────────────────
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import requests as _req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class ProactiveMonitor:
    """
    Background agent that fires spoken + toast alerts when thresholds are crossed.
    One instance is created and started by FridayEngine.
    """

    # ── Thresholds (overridable via config) ───────────────────────────────────
    CPU_SPIKE_THRESHOLD    = getattr(config, "MONITOR_CPU_THRESHOLD",    90)   # %
    RAM_SPIKE_THRESHOLD    = getattr(config, "MONITOR_RAM_THRESHOLD",    90)   # %
    CPU_SPIKE_COOLDOWN     = getattr(config, "MONITOR_CPU_COOLDOWN",    300)   # seconds
    BATTERY_LOW_THRESHOLD  = getattr(config, "MONITOR_BATTERY_LOW",      20)   # %
    BATTERY_COOLDOWN       = getattr(config, "MONITOR_BATTERY_COOLDOWN", 600)  # seconds
    WORK_SESSION_LIMIT     = getattr(config, "MONITOR_WORK_SESSION_MIN", 120)  # minutes
    WORK_BREAK_COOLDOWN    = getattr(config, "MONITOR_WORK_BREAK_CDN",   60)   # minutes between nags
    POLL_INTERVAL          = getattr(config, "MONITOR_POLL_INTERVAL",    30)   # seconds
    STOCK_POLL_INTERVAL    = getattr(config, "MONITOR_STOCK_INTERVAL",  300)   # seconds (5 min)
    STOCK_ALERT_THRESHOLD  = getattr(config, "MONITOR_STOCK_THRESHOLD",   5.0) # % change to alert

    def __init__(self, engine):
        self._engine      = engine          # FridayEngine — for proactive speech
        self._stop_event  = threading.Event()

        # Cooldown trackers
        self._last_cpu_alert    = 0.0
        self._last_battery_alert = 0.0
        self._last_break_alert  = 0.0

        # Work session tracking
        self._session_start = time.time()

        # Stock tracking: symbol → last price
        self._stock_prices: dict[str, float] = {}
        self._stock_price_at_alert: dict[str, float] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Launch all monitor threads."""
        self._stop_event.clear()
        self._session_start = time.time()

        t_sys = threading.Thread(target=self._system_loop, name="SysMonitor", daemon=True)
        t_sys.start()

        t_stock = threading.Thread(target=self._stock_loop, name="StockMonitor", daemon=True)
        t_stock.start()

        logger.info("ProactiveMonitor started")

    def stop(self) -> None:
        self._stop_event.set()

    def reset_session_timer(self) -> None:
        """Call when user is active — resets the work session clock."""
        self._session_start = time.time()

    # ── System monitor loop ───────────────────────────────────────────────────

    def _system_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._check_system()
            except Exception as exc:
                logger.error("System monitor error: %s", exc)
            self._stop_event.wait(self.POLL_INTERVAL)

    def _check_system(self) -> None:
        now = time.time()

        # ── CPU spike ─────────────────────────────────────────────────────
        if HAS_PSUTIL and (now - self._last_cpu_alert) > self.CPU_SPIKE_COOLDOWN:
            cpu = psutil.cpu_percent(interval=2)
            if cpu >= self.CPU_SPIKE_THRESHOLD:
                # Find top CPU hog
                top_proc = _top_process_by("cpu_percent")
                culprit  = f"{top_proc} is the culprit." if top_proc else ""
                msg = (
                    f"Sir, system CPU is at {cpu:.0f}%. "
                    f"{culprit} "
                    f"Want me to kill it?"
                )
                self._alert(msg, toast_msg=f"CPU at {cpu:.0f}% — {top_proc or 'unknown process'}")
                self._last_cpu_alert = now

        # ── RAM spike ─────────────────────────────────────────────────────
        if HAS_PSUTIL and (now - self._last_cpu_alert) > self.CPU_SPIKE_COOLDOWN:
            ram = psutil.virtual_memory().percent
            if ram >= self.RAM_SPIKE_THRESHOLD:
                top_proc = _top_process_by("memory_percent")
                culprit  = f"{top_proc} is consuming the most." if top_proc else ""
                msg = (
                    f"Heads up, Sir — RAM usage is at {ram:.0f}%. "
                    f"{culprit}"
                )
                self._alert(msg, toast_msg=f"RAM at {ram:.0f}%")

        # ── Battery low ───────────────────────────────────────────────────
        if HAS_PSUTIL and (now - self._last_battery_alert) > self.BATTERY_COOLDOWN:
            batt = psutil.sensors_battery()
            if batt and not batt.power_plugged and batt.percent <= self.BATTERY_LOW_THRESHOLD:
                msg = (
                    f"Battery is at {batt.percent:.0f}%, Sir. "
                    f"You may want to plug in."
                )
                self._alert(msg, toast_msg=f"Battery low: {batt.percent:.0f}%")
                self._last_battery_alert = now

        # ── Work session timer ─────────────────────────────────────────────
        session_minutes = (now - self._session_start) / 60
        if (
            session_minutes >= self.WORK_SESSION_LIMIT
            and (now - self._last_break_alert) > (self.WORK_BREAK_COOLDOWN * 60)
        ):
            hours = int(session_minutes // 60)
            mins  = int(session_minutes % 60)
            duration_str = f"{hours}h {mins}m" if hours else f"{mins} minutes"
            msg = (
                f"Sir, you've been at it for {duration_str} straight. "
                f"Consider taking a short break — your focus will thank you."
            )
            self._alert(msg, toast_msg=f"Work session: {duration_str} — time for a break")
            self._last_break_alert = now

    # ── Stock / crypto monitor loop ───────────────────────────────────────────

    def _stock_loop(self) -> None:
        # Initial delay so startup doesn't slam APIs
        self._stop_event.wait(60)
        while not self._stop_event.is_set():
            try:
                self._check_stocks()
            except Exception as exc:
                logger.error("Stock monitor error: %s", exc)
            self._stop_event.wait(self.STOCK_POLL_INTERVAL)

    def _check_stocks(self) -> None:
        if not HAS_REQUESTS:
            return
        watchlist = _get_watchlist()
        if not watchlist:
            return

        for item in watchlist:
            symbol   = item["symbol"].upper()
            asset    = item["asset_type"]   # "crypto" or "stock"
            try:
                price = _fetch_price(symbol, asset)
                if price is None:
                    continue

                prev = self._stock_prices.get(symbol)
                self._stock_prices[symbol] = price

                if prev is None or prev == 0:
                    continue  # First observation — no change to compare

                pct_change = (price - prev) / prev * 100
                if abs(pct_change) >= self.STOCK_ALERT_THRESHOLD:
                    direction = "up" if pct_change > 0 else "down"
                    msg = (
                        f"Sir, {symbol} is {direction} {abs(pct_change):.1f}% "
                        f"to ${price:,.2f} in the last {self.STOCK_POLL_INTERVAL // 60} minutes."
                    )
                    self._alert(msg, toast_msg=f"{symbol} {direction} {abs(pct_change):.1f}% → ${price:,.2f}")
                    # Reset baseline to current so we don't spam
                    self._stock_prices[symbol] = price

            except Exception as exc:
                logger.debug("Price fetch error for %s: %s", symbol, exc)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _alert(self, speech: str, toast_msg: str | None = None) -> None:
        """Queue speech + fire toast."""
        from services.toast import toast_alert
        if toast_msg:
            toast_alert(toast_msg)
        # Queue into proactive speech queue
        try:
            self._engine._proactive_q.put(speech)
        except Exception as exc:
            logger.error("Could not queue proactive speech: %s", exc)


# ── Price fetching ─────────────────────────────────────────────────────────────

def _fetch_price(symbol: str, asset_type: str) -> float | None:
    """Fetch current price from CoinGecko (crypto) or Yahoo Finance (stocks)."""
    try:
        import requests
        if asset_type == "crypto":
            # CoinGecko free tier
            cg_id = _COINGECKO_IDS.get(symbol.upper(), symbol.lower())
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd"
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            data = r.json()
            return data.get(cg_id, {}).get("usd")
        else:
            # Yahoo Finance unofficial quote endpoint
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=8)
            r.raise_for_status()
            data = r.json()
            meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
            return meta.get("regularMarketPrice")
    except Exception as exc:
        logger.debug("_fetch_price error for %s: %s", symbol, exc)
        return None


# Common CoinGecko IDs for popular symbols
_COINGECKO_IDS: dict[str, str] = {
    "BTC":  "bitcoin",
    "ETH":  "ethereum",
    "SOL":  "solana",
    "BNB":  "binancecoin",
    "XRP":  "ripple",
    "DOGE": "dogecoin",
    "ADA":  "cardano",
    "MATIC": "matic-network",
    "AVAX": "avalanche-2",
    "DOT":  "polkadot",
    "LINK": "chainlink",
    "UNI":  "uniswap",
    "LTC":  "litecoin",
}


def _top_process_by(attr: str) -> str | None:
    """Return the name of the top process by a given psutil attribute."""
    if not HAS_PSUTIL:
        return None
    try:
        procs = []
        for p in psutil.process_iter(["name", attr]):
            try:
                val = p.info[attr] or 0
                procs.append((val, p.info["name"]))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if procs:
            procs.sort(reverse=True)
            name = procs[0][1]
            return name
    except Exception:
        pass
    return None


def _get_watchlist() -> list[dict]:
    """Load the stock/crypto watchlist from the database."""
    try:
        from storage.db import get_conn
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT symbol, asset_type FROM stock_watchlist WHERE active = 1"
            ).fetchall()
            return [{"symbol": r["symbol"], "asset_type": r["asset_type"]} for r in rows]
    except Exception as exc:
        logger.debug("Could not load watchlist: %s", exc)
        return []

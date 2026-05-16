"""
F.R.I.D.A.Y. — Browser Automation
Uses Playwright (sync API) for reliable browser control.
Manages a single persistent Chromium instance.
All functions return plain strings for Gemini tool responses.
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import sync_playwright, Browser, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    logger.warning("playwright not installed — browser automation unavailable")

_UNAVAILABLE = "Browser automation unavailable — playwright not installed. Run: playwright install chromium"

# Interval code mapping for TradingView
_TV_INTERVALS = {
    "1m":  "1",
    "2m":  "2",
    "3m":  "3",
    "5m":  "5",
    "10m": "10",
    "15m": "15",
    "30m": "30",
    "45m": "45",
    "1h":  "60",
    "2h":  "120",
    "3h":  "180",
    "4h":  "240",
    "1d":  "D",
    "1w":  "W",
    "1M":  "M",
    # also accept raw numbers
    "60":  "60",
    "240": "240",
}


class _BrowserSingleton:
    """
    Singleton that holds a Playwright browser instance.
    Lazy-initialized on first use, reused across tool calls.
    Thread-safe via a lock.
    """

    def __init__(self):
        self._lock       = threading.Lock()
        self._playwright = None
        self._browser: "Browser | None" = None
        self._page:    "Page | None"    = None

    def _ensure(self):
        """Ensure Playwright browser is running. Called before every action."""
        if not HAS_PLAYWRIGHT:
            return False

        with self._lock:
            try:
                # Check if existing page is still alive
                if self._page and not self._page.is_closed():
                    return True
            except Exception:
                pass

            # Launch fresh
            try:
                if self._playwright is None:
                    self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(
                    headless=False,
                    args=[
                        "--start-maximized",
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
                context      = self._browser.new_context(no_viewport=True)
                self._page   = context.new_page()
                logger.info("Playwright Chromium launched")
                return True
            except Exception as exc:
                logger.error("Failed to launch Playwright: %s", exc)
                return False

    def navigate(self, url: str, wait_ms: int = 3000, timeout_ms: int = 45000) -> str:
        """Navigate to a URL. Returns status string."""
        if not self._ensure():
            return _UNAVAILABLE
        try:
            with self._lock:
                self._page.goto(url, wait_until="commit", timeout=timeout_ms)
                self._page.wait_for_timeout(wait_ms)
                title = self._page.title()
            return f"Navigated to: {url} — Page: {title}"
        except Exception as exc:
            logger.error("Navigation error: %s", exc)
            return f"Navigation failed: {exc}"

    def click_selector(self, selector: str) -> str:
        """Click a CSS selector on the current page."""
        if not self._ensure():
            return _UNAVAILABLE
        try:
            with self._lock:
                self._page.click(selector, timeout=5000)
            return f"Clicked selector: {selector}"
        except Exception as exc:
            return f"Click failed for '{selector}': {exc}"

    def get_title(self) -> str:
        if not self._ensure():
            return _UNAVAILABLE
        try:
            with self._lock:
                return self._page.title()
        except Exception as exc:
            return f"Could not get title: {exc}"

    def get_url(self) -> str:
        if not self._ensure():
            return _UNAVAILABLE
        try:
            with self._lock:
                return self._page.url
        except Exception as exc:
            return f"Could not get URL: {exc}"

    def close(self):
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._browser    = None
        self._page       = None
        self._playwright = None


# Global singleton instance
_browser = _BrowserSingleton()


# ── Tool functions ────────────────────────────────────────────────────────

def open_browser_url(url: str) -> str:
    """
    Open a URL in the Playwright-controlled browser.
    Provide the full URL including https://.
    Examples: https://www.google.com, https://finance.yahoo.com
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return _browser.navigate(url)


def open_tradingview_chart(symbol: str, timeframe: str = "1h") -> str:
    """
    Open TradingView with a specific trading symbol and timeframe.
    symbol: e.g. 'XAUUSD', 'EURUSD', 'BTCUSDT', 'AAPL', 'SPY'
    timeframe: '1m', '5m', '15m', '1h', '4h', '1d', '1w'
    """
    interval = _TV_INTERVALS.get(timeframe.lower(), timeframe)
    symbol_upper = symbol.upper().strip()
    url = f"https://www.tradingview.com/chart/?symbol={symbol_upper}&interval={interval}"
    result = _browser.navigate(url, wait_ms=4000)
    return f"Opened TradingView — {symbol_upper} on {timeframe} chart. {result}"


def browser_click(selector: str) -> str:
    """
    Click an element on the current browser page using a CSS selector.
    Examples: 'button[data-name=go-to-date]', '#search-input', '.menu-item'
    """
    return _browser.click_selector(selector)


def get_browser_title() -> str:
    """Get the title of the currently open browser page."""
    return _browser.get_title()


def get_browser_url() -> str:
    """Get the URL of the currently open browser page."""
    return _browser.get_url()

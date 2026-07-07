"""Shared headless-Chromium fetch helper for scrapers that a plain `requests`
call can no longer get past — Amazon returns a flat 503 and Qoo10 Japan
returns its block page with an HTTP 200 (see collect_amazon.py / collect_qoo10.py
module docstrings for the specifics observed). A real (if headless) browser
carries a genuine TLS/JS fingerprint and executes the page like a normal
visitor, which a bare HTTP client cannot fake with headers alone.

Used identically by both collect_amazon.py and collect_qoo10.py, so the
browser-launch/stealth/teardown boilerplate lives here once rather than
duplicated in each.

Callers keep using BeautifulSoup exactly as before — only the fetch layer
changed. Pass the fully rendered HTML (`fetch()`'s return value) into
BeautifulSoup like `_get()` used to return.
"""

import logging

from playwright.sync_api import Browser, BrowserContext, Playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1366, "height": 768}
NAV_TIMEOUT_MS = 30000
SELECTOR_WAIT_TIMEOUT_MS = 8000
SETTLE_TIMEOUT_MS = 1500  # brief wait when no specific selector to wait for

# A stock headless Chromium leaves a few tells (navigator.webdriver=true,
# empty navigator.plugins, missing window.chrome) that bot-detection scripts
# specifically probe for, on top of whatever IP/rate-limit signal is used.
# This is a minimal, well-known countermeasure set — not a guarantee.
_STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
"""


class RenderedPageFetcher:
    """Context manager wrapping one headless-Chromium browser + context.

    Launch once per collect_*_data() run and reuse across every product in
    that run — launching a fresh browser per request would be slow and is
    unnecessary since the context (UA/viewport/locale/stealth) is the same
    for every page in a run.

    Usage:
        with RenderedPageFetcher(locale="ja-JP") as fetcher:
            html = fetcher.fetch(url, wait_selector="script[type='application/ld+json']")
    """

    def __init__(self, locale: str = "en-US"):
        self._locale = locale
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    def __enter__(self) -> "RenderedPageFetcher":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = self._browser.new_context(
            user_agent=USER_AGENT,
            viewport=VIEWPORT,
            locale=self._locale,
        )
        self._context.add_init_script(_STEALTH_INIT_SCRIPT)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def fetch(self, url: str, wait_selector: str | None = None) -> str | None:
        """Navigate to url, wait for it to render, return the full HTML.

        Returns None on navigation failure or an HTTP error status — callers
        should treat that exactly like the old requests-based _get()'s None.
        """
        if self._context is None:
            raise RuntimeError("RenderedPageFetcher used outside a `with` block")

        page = self._context.new_page()
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            if response is not None and response.status >= 400:
                logger.warning("Playwright navigation to %s returned HTTP %d", url, response.status)
                return None

            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=SELECTOR_WAIT_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    logger.debug(
                        "wait_for_selector(%r) timed out on %s — proceeding with whatever rendered",
                        wait_selector, url,
                    )
            else:
                page.wait_for_timeout(SETTLE_TIMEOUT_MS)

            return page.content()
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            logger.warning("Playwright navigation failed for %s: %s", url, exc)
            return None
        finally:
            page.close()

"""Headless-browser fetch fallback for pages that block plain HTTP clients.

Indeed's Cloudflare bot-management returns a 403 challenge to `httpx`/`curl`
(confirmed while researching this feature) but a real (headless) browser gets
through fine. This is the fallback path — only used when a direct fetch fails.

Sync (Playwright's sync API), blocking — callers run it via
`reflex.utils.misc.run_in_thread`. Pure module — no Reflex imports.
"""

from __future__ import annotations

from .. import config

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class BrowserFetchError(RuntimeError):
    """Raised when the headless browser fails to load or render the page."""


def fetch_rendered_html(url: str) -> str:
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(user_agent=_USER_AGENT)
                page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=config.BROWSER_FETCH_TIMEOUT_MS,
                )
                return page.content()
            finally:
                browser.close()
    except Exception as e:  # noqa: BLE001 - surface any failure uniformly
        raise BrowserFetchError(f"Headless browser fetch failed for {url}: {e}") from e

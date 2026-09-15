"""
Optional JS-rendering fetch path (Phase 2).

books.toscrape.com serves plain static HTML, so fetch_html() in scrape.py
(requests + BeautifulSoup) is all it needs — there is nothing to render.
This module exists as the pattern to reach for on a *different* site where
the data you want isn't in the raw HTML because JavaScript builds it in the
browser after the page loads (infinite-scroll feeds, client-side rendered
React/Vue apps, etc). requests can't run JavaScript; Playwright drives a
real (headless) browser, so it sees the same DOM you'd see in DevTools.

Not wired into the pipeline and not covered by CI tests here (it needs a
real browser binary) — copy this pattern into a new scraper module only when
a target site actually requires it.
"""
from __future__ import annotations

USER_AGENT = "data-scraping-tool-tutorial/0.1 (+https://github.com/; learning project)"


def fetch_rendered_html(url: str, wait_selector: str | None = None, timeout_ms: int = 15000) -> str:
    """Fetch a page's HTML *after* its JavaScript has run.

    wait_selector: a CSS selector to wait for before reading the page,
    e.g. "article.product_pod" — waits until the JS-rendered content you
    actually want has appeared, instead of grabbing the page too early.
    """
    from playwright.sync_api import sync_playwright  # imported lazily: optional dependency

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        try:
            page.goto(url, timeout=timeout_ms)
            if wait_selector:
                page.wait_for_selector(wait_selector, timeout=timeout_ms)
            return page.content()
        finally:
            browser.close()

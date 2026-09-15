"""
Shared HTTP fetching (Phase 2's retry/backoff + robots.txt logic), used by
both the books_toscrape scraper and the generic config-driven scraper
(the "add any site" feature). Site-specific code should never re-implement
retry/backoff -- import it from here.
"""
from __future__ import annotations

from urllib.robotparser import RobotFileParser

import requests
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

DEFAULT_USER_AGENT = "data-scraping-tool-tutorial/0.1 (+https://github.com/; learning project)"


# Requests that failed for a reason worth retrying (network hiccup, server
# overloaded, rate-limited). The caller should back off and try again.
class TransientFetchError(Exception):
    pass


# Requests that failed for a reason that will never change on retry (page
# genuinely doesn't exist, we're blocked). Retrying is pointless / rude.
class PermanentFetchError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _fetch_once(url: str, user_agent: str) -> str:
    try:
        resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=10)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise TransientFetchError(f"network error fetching {url}: {exc}") from exc

    if resp.status_code == 404:
        raise PermanentFetchError(f"404 Not Found: {url}", status_code=404)
    if resp.status_code == 403:
        raise PermanentFetchError(f"403 Forbidden (blocked?): {url}", status_code=403)
    if resp.status_code == 429 or 500 <= resp.status_code < 600:
        raise TransientFetchError(f"HTTP {resp.status_code} from {url}")

    resp.raise_for_status()
    return resp.text


def fetch_html(
    url: str,
    *,
    max_attempts: int = 4,
    base_delay: float = 1.0,
    user_agent: str = DEFAULT_USER_AGENT,
) -> str:
    """Download one page's raw HTML, retrying transient failures with
    exponential backoff. Permanent failures (404/403) raise immediately,
    with no retry."""
    retryer = Retrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=base_delay, min=base_delay, max=base_delay * 8),
        retry=retry_if_exception_type(TransientFetchError),
        reraise=True,
    )
    return retryer(_fetch_once, url, user_agent)


def is_allowed(robots_txt: str, path: str, user_agent: str = DEFAULT_USER_AGENT) -> bool:
    """Pure function: given robots.txt content, is this path allowed?"""
    rp = RobotFileParser()
    rp.parse(robots_txt.splitlines())
    return rp.can_fetch(user_agent, path)


def fetch_robots_txt(base_url: str, **kwargs) -> str:
    """robots.txt content for base_url. A 404 (no robots.txt file at all)
    is the standard crawler convention for "no restrictions specified" --
    most sites, including books.toscrape.com, simply don't publish one --
    so it returns an empty ruleset (is_allowed() then permits everything)
    instead of raising. Other permanent errors (403, etc.) still raise:
    those usually mean "you're blocked," not "there happen to be no rules."
    """
    try:
        return fetch_html(base_url.rstrip("/") + "/robots.txt", **kwargs)
    except PermanentFetchError as exc:
        if exc.status_code == 404:
            return ""
        raise

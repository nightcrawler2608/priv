"""
Generic pagination over a site's list_url_template, reusing the same
retry/backoff/robots.txt logic as books_toscrape (Phase 2) via
scrapers.common.fetch -- no retry logic is duplicated here.
"""
from __future__ import annotations

import time

from ..common.fetch import PermanentFetchError, fetch_html
from .models import SiteDefinition


def iter_list_pages(site: SiteDefinition, delay_seconds: float = 1.0, max_attempts: int = 4, base_delay: float = 1.0):
    """Yield (page_number, html, page_url) for each list page, stopping
    cleanly once pagination runs off the end (404) -- same contract as
    books_toscrape's iter_catalogue_pages."""
    for page_num in range(1, site.max_pages + 1):
        url = site.list_url_template.format(page=page_num)
        try:
            html = fetch_html(url, max_attempts=max_attempts, base_delay=base_delay)
        except PermanentFetchError:
            break
        yield page_num, html, url
        if page_num < site.max_pages:
            time.sleep(delay_seconds)

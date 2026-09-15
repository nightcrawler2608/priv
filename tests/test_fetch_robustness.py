"""Phase 2 tests: retries, backoff, pagination cutoff, robots.txt — all
offline. `responses` intercepts requests at the transport level, so these
never touch the real network."""
import responses

from scrapers.books_toscrape.scrape import (
    BASE_URL,
    PermanentFetchError,
    TransientFetchError,
    fetch_html,
    is_allowed,
    iter_catalogue_pages,
)

PAGE_URL = BASE_URL + "catalogue/page-1.html"


@responses.activate
def test_fetch_html_retries_after_transient_500_then_succeeds():
    responses.add(responses.GET, PAGE_URL, status=500)
    responses.add(responses.GET, PAGE_URL, status=200, body="<html>ok</html>")

    html = fetch_html(PAGE_URL, max_attempts=4, base_delay=0.01)

    assert html == "<html>ok</html>"
    assert len(responses.calls) == 2


@responses.activate
def test_fetch_html_gives_up_cleanly_after_exhausting_retries():
    for _ in range(4):
        responses.add(responses.GET, PAGE_URL, status=503)

    try:
        fetch_html(PAGE_URL, max_attempts=4, base_delay=0.01)
        assert False, "expected TransientFetchError"
    except TransientFetchError:
        pass

    assert len(responses.calls) == 4


@responses.activate
def test_fetch_html_404_is_permanent_and_not_retried():
    responses.add(responses.GET, PAGE_URL, status=404)

    try:
        fetch_html(PAGE_URL, max_attempts=4, base_delay=0.01)
        assert False, "expected PermanentFetchError"
    except PermanentFetchError:
        pass

    # only one call made -- a 404 must not trigger retries
    assert len(responses.calls) == 1


@responses.activate
def test_iter_catalogue_pages_stops_cleanly_at_end_of_pagination():
    responses.add(responses.GET, BASE_URL + "catalogue/page-1.html", status=200, body="<html>page1</html>")
    responses.add(responses.GET, BASE_URL + "catalogue/page-2.html", status=200, body="<html>page2</html>")
    responses.add(responses.GET, BASE_URL + "catalogue/page-3.html", status=404)

    pages = list(iter_catalogue_pages(max_pages=50, delay_seconds=0, base_delay=0.01))

    assert [p for p, _ in pages] == [1, 2]
    assert pages[0][1] == "<html>page1</html>"
    assert pages[1][1] == "<html>page2</html>"


ROBOTS_TXT = """
User-agent: *
Disallow: /admin/
Allow: /catalogue/
"""


def test_is_allowed_permits_catalogue_paths():
    assert is_allowed(ROBOTS_TXT, "/catalogue/page-1.html") is True


def test_is_allowed_blocks_disallowed_paths():
    assert is_allowed(ROBOTS_TXT, "/admin/secret.html") is False

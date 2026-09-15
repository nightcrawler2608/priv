"""
Regression test for a real bug found by running the app against the real
internet (this sandbox blocks that, so it slipped past every prior test):
books.toscrape.com has no /robots.txt file at all, which returns a genuine
404. The crawler convention is that a missing robots.txt means "no
restrictions specified" -- most real sites don't publish one -- so this
must be treated as "everything allowed," not as a fatal error. Before the
fix, every real job against books.toscrape.com failed immediately with
"404 Not Found: https://books.toscrape.com/robots.txt".
"""
import responses

from scrapers.books_toscrape.scrape import fetch_robots_txt, is_allowed
from scrapers.common.fetch import PermanentFetchError
from scrapers.common.fetch import fetch_robots_txt as common_fetch_robots_txt

BASE_URL = "https://example.com/"
ROBOTS_URL = BASE_URL + "robots.txt"


@responses.activate
def test_missing_robots_txt_is_treated_as_no_restrictions():
    responses.add(responses.GET, ROBOTS_URL, status=404)

    robots_txt = common_fetch_robots_txt(BASE_URL)

    assert robots_txt == ""
    assert is_allowed(robots_txt, "/any/path/at/all") is True


@responses.activate
def test_books_toscrape_fetch_robots_txt_wrapper_handles_404_too():
    """The books_toscrape module's own fetch_robots_txt() -- what
    api/tasks.py actually calls -- must behave the same way, not just the
    shared scrapers.common.fetch implementation underneath it."""
    responses.add(responses.GET, "https://books.toscrape.com/robots.txt", status=404)

    robots_txt = fetch_robots_txt()

    assert robots_txt == ""
    assert is_allowed(robots_txt, "/catalogue/page-1.html") is True


@responses.activate
def test_other_permanent_errors_on_robots_txt_still_raise():
    """A 404 means "no rules published" -- but a 403 means "you're
    blocked," which is a real reason to stop, not proceed as if allowed."""
    responses.add(responses.GET, ROBOTS_URL, status=403)

    try:
        common_fetch_robots_txt(BASE_URL)
        assert False, "expected PermanentFetchError"
    except PermanentFetchError as exc:
        assert exc.status_code == 403

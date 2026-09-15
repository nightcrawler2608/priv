"""
Regression test for a real bug found on an actual scrape (this sandbox
has no live internet, so it could never have surfaced here either):
books.toscrape.com's prices came through as "Â51.77" instead of "£51.77",
which then failed float() conversion and crashed every job.

Root cause: `requests` defaults to ISO-8859-1 when a server's Content-Type
header doesn't declare a charset -- true of books.toscrape.com, which
(like most real sites) only declares UTF-8 via an HTML <meta charset> tag,
not the HTTP header. Decoding UTF-8 bytes as ISO-8859-1 turns "£"
(bytes 0xC2 0xA3) into "Â£". `responses` reproduces this exactly: pass raw
UTF-8 bytes with a charset-less Content-Type and requests decodes with its
default unless corrected.
"""
import responses

from scrapers.common.fetch import fetch_html

URL = "https://example.com/page.html"


@responses.activate
def test_fetch_html_correctly_decodes_utf8_with_no_declared_charset():
    html = "<html><body><p>Price: £51.77</p></body></html>"
    responses.add(responses.GET, URL, body=html.encode("utf-8"), status=200, content_type="text/html")

    result = fetch_html(URL)

    assert "£51.77" in result
    assert "Â" not in result  # the mojibake character that broke float() conversion


@responses.activate
def test_fetch_html_respects_an_explicitly_declared_non_utf8_charset():
    """Only override when the server didn't say -- a real explicit charset
    (even a non-UTF-8 one) should still be trusted."""
    html = "<html><body>caf\xe9</body></html>"  # 'é' as a single Latin-1 byte
    responses.add(
        responses.GET, URL,
        body=html.encode("latin-1"), status=200,
        content_type="text/html; charset=iso-8859-1",
    )

    result = fetch_html(URL)

    assert "café" in result

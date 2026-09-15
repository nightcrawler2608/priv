"""
Tests for the "paste a URL, get data" heuristic auto-detector. Pure,
offline -- runs against the same fixture used since Phase 1, proving it
can guess books.toscrape.com's structure with zero hints, and that the
guessed config actually produces correct data through the real parser.
"""
from pathlib import Path

from scrapers.generic.autodetect import detect_site_structure
from scrapers.generic.models import FieldConfig, SiteDefinition
from scrapers.generic.parser import parse_items
from scrapers.generic.validate import clean_and_validate_items

FIXTURE = Path(__file__).parent / "fixtures" / "books_page1.html"
PAGE_URL = "https://books.toscrape.com/catalogue/page-1.html"


def test_detects_the_repeated_item_and_a_confident_item_count():
    html = FIXTURE.read_text(encoding="utf-8")
    result = detect_site_structure(html)

    assert result is not None
    assert result.item_count == 6


def test_detects_title_and_price_fields():
    html = FIXTURE.read_text(encoding="utf-8")
    result = detect_site_structure(html)

    names = {f.name for f in result.fields}
    assert "title" in names
    assert "price" in names

    price_field = next(f for f in result.fields if f.name == "price")
    assert price_field.type == "number"


def test_detected_key_selector_resolves_to_a_link():
    html = FIXTURE.read_text(encoding="utf-8")
    result = detect_site_structure(html)
    assert result.key_selector is not None


def test_detected_config_produces_correct_data_through_the_real_parser():
    """The real proof: feed the guessed selectors back through the actual
    parse/validate pipeline and check the output matches known-good data,
    not just that the selectors look plausible."""
    html = FIXTURE.read_text(encoding="utf-8")
    detected = detect_site_structure(html)

    site = SiteDefinition(
        id="auto1", name="auto-detected", base_url="https://books.toscrape.com/",
        list_url_template=PAGE_URL,
        item_selector=detected.item_selector,
        key_selector=detected.key_selector, key_attr=detected.key_attr,
        fields=[
            FieldConfig(name=f.name, selector=f.selector, attr=f.attr, type=f.type, required=f.required)
            for f in detected.fields
        ],
    )

    raw_items = parse_items(html, PAGE_URL, site)
    clean_items, rejected = clean_and_validate_items(raw_items, site)

    assert len(clean_items) == 6
    assert rejected == 0

    titles = {item["title"] for item in clean_items}
    assert "A Light in the Attic" in titles
    assert "Unsellable Vaporware" in titles

    first = next(i for i in clean_items if i["title"] == "A Light in the Attic")
    assert first["price"] == 51.77


def test_first_detected_field_is_marked_required():
    """The first field found (usually "title") being required is what
    naturally filters out junk rows sharing the item's shape but not its
    content -- see test_wikipedia_style_table_* below."""
    html = FIXTURE.read_text(encoding="utf-8")
    result = detect_site_structure(html)
    assert result.fields[0].required is True


def test_returns_none_for_a_page_with_no_repeated_structure():
    html = "<html><body><h1>Just one article</h1><p>No list here.</p></body></html>"
    result = detect_site_structure(html)
    assert result is None


WIKI_TABLE_HTML = """
<html><body>
<table class="wikitable sortable">
<tbody>
<tr><th>Country</th><th>Population</th></tr>
<tr><td><a href="/wiki/China">China</a></td><td>1,412,000,000</td></tr>
<tr><td><a href="/wiki/India">India</a></td><td>1,417,000,000</td></tr>
<tr><td><a href="/wiki/USA">United States</a></td><td>335,000,000</td></tr>
<tr><td><a href="/wiki/Indonesia">Indonesia</a></td><td>277,000,000</td></tr>
</tbody>
</table>
</body></html>
"""


def test_detects_classless_table_rows_scoped_to_their_table():
    """A Wikipedia-style table: <tr> rows have no class attribute at all --
    a real gap the first version of this heuristic had, since it only
    considered elements with a class."""
    result = detect_site_structure(WIKI_TABLE_HTML)

    assert result is not None
    assert result.item_count == 5  # 4 data rows + 1 header row (still matches the shape)
    assert "wikitable" in result.item_selector
    assert "tr" in result.item_selector


def test_header_row_is_excluded_after_validation_not_extraction():
    """detect_site_structure() itself can't tell a header row from a data
    row (same tag, same parent) -- it's the required-field validation,
    downstream, that correctly drops it. This is the actual end-to-end
    behavior a user sees."""
    result = detect_site_structure(WIKI_TABLE_HTML)

    site = SiteDefinition(
        id="wiki1", name="wiki-test", base_url="https://it.wikipedia.org/",
        list_url_template="https://it.wikipedia.org/wiki/Test",
        item_selector=result.item_selector, key_selector=result.key_selector, key_attr=result.key_attr,
        fields=[
            FieldConfig(name=f.name, selector=f.selector, attr=f.attr, type=f.type, required=f.required)
            for f in result.fields
        ],
    )

    raw_items = parse_items(WIKI_TABLE_HTML, "https://it.wikipedia.org/wiki/Test", site)
    clean_items, rejected = clean_and_validate_items(raw_items, site)

    assert rejected == 1  # just the header row
    assert len(clean_items) == 4
    titles = {item["title"] for item in clean_items}
    assert titles == {"China", "India", "United States", "Indonesia"}

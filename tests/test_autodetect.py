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
            FieldConfig(name=f.name, selector=f.selector, attr=f.attr, type=f.type, required=False)
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


def test_returns_none_for_a_page_with_no_repeated_structure():
    html = "<html><body><h1>Just one article</h1><p>No list here.</p></body></html>"
    result = detect_site_structure(html)
    assert result is None

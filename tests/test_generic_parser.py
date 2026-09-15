"""Config-driven sites: generic parser tests. Pure, offline -- proves the
same fixture used since Phase 1 can be scraped with nothing but CSS
selectors in a config, no site-specific Python."""
from pathlib import Path

from scrapers.generic.models import FieldConfig, SiteDefinition
from scrapers.generic.parser import parse_items

FIXTURE = Path(__file__).parent / "fixtures" / "books_page1.html"
PAGE_URL = "https://books.toscrape.com/catalogue/page-1.html"


def _books_site(**overrides) -> SiteDefinition:
    defaults = dict(
        id="site1",
        name="books_toscrape_generic",
        base_url="https://books.toscrape.com/",
        list_url_template="https://books.toscrape.com/catalogue/page-{page}.html",
        item_selector="article.product_pod",
        key_selector="h3 a",
        key_attr="href",
        fields=[
            FieldConfig(name="title", selector="h3 a", attr="title"),
            FieldConfig(name="price", selector="p.price_color", type="number"),
            FieldConfig(name="availability", selector=".availability"),
        ],
        max_pages=1,
    )
    defaults.update(overrides)
    return SiteDefinition(**defaults)


def test_parse_items_extracts_expected_count_and_fields():
    html = FIXTURE.read_text(encoding="utf-8")
    items = parse_items(html, PAGE_URL, _books_site())

    assert len(items) == 6
    first = items[0]
    assert first["title"] == "A Light in the Attic"
    assert first["price"] == "£51.77"  # coercion to float happens in validate.py, not here
    assert first["availability"] == "In stock"


def test_parse_items_resolves_key_to_absolute_url():
    html = FIXTURE.read_text(encoding="utf-8")
    items = parse_items(html, PAGE_URL, _books_site())

    assert items[0]["_key"] == "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"


def test_parse_items_falls_back_to_hash_key_without_key_selector():
    html = FIXTURE.read_text(encoding="utf-8")
    site = _books_site(key_selector=None)
    items = parse_items(html, PAGE_URL, site)

    assert all(item["_key"] for item in items)
    assert len({item["_key"] for item in items}) == 6  # all distinct given distinct field values


def test_parse_items_missing_selector_yields_none_not_a_crash():
    html = FIXTURE.read_text(encoding="utf-8")
    site = _books_site(fields=[FieldConfig(name="nonexistent", selector=".does-not-exist", required=False)])
    items = parse_items(html, PAGE_URL, site)

    assert len(items) == 6
    assert all(item["nonexistent"] is None for item in items)

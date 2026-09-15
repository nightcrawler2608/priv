"""Config-driven sites: generic validation tests. Pure, offline."""
from scrapers.generic.models import FieldConfig, SiteDefinition
from scrapers.generic.validate import clean_and_validate_items, item_row_hash

SITE = SiteDefinition(
    id="s1", name="test", base_url="https://x/", list_url_template="https://x/{page}",
    item_selector="div", fields=[
        FieldConfig(name="title", selector="h1"),
        FieldConfig(name="price", selector=".p", type="number"),
        FieldConfig(name="note", selector=".n", required=False),
    ],
)


def test_coerces_currency_text_to_float():
    raw = [{"_key": "k1", "title": "Book", "price": "£51.77", "note": None}]
    clean, rejected = clean_and_validate_items(raw, SITE)
    assert rejected == 0
    assert clean[0]["price"] == 51.77


def test_rejects_row_missing_required_field():
    raw = [{"_key": "k1", "title": "  ", "price": "£10", "note": None}]
    clean, rejected = clean_and_validate_items(raw, SITE)
    assert clean == []
    assert rejected == 1


def test_rejects_unparseable_number():
    raw = [{"_key": "k1", "title": "Book", "price": "N/A", "note": None}]
    clean, rejected = clean_and_validate_items(raw, SITE)
    assert clean == []
    assert rejected == 1


def test_optional_field_can_be_blank():
    raw = [{"_key": "k1", "title": "Book", "price": "£10", "note": None}]
    clean, rejected = clean_and_validate_items(raw, SITE)
    assert rejected == 0
    assert clean[0]["note"] is None


def test_row_hash_stable_for_identical_values_and_changes_on_price():
    row1 = {"title": "Book", "price": 10.0, "note": None, "_key": "k1"}
    row2 = {"title": "Book", "price": 10.0, "note": None, "_key": "k1"}
    row3 = {"title": "Book", "price": 12.0, "note": None, "_key": "k1"}

    assert item_row_hash(row1, SITE) == item_row_hash(row2, SITE)
    assert item_row_hash(row1, SITE) != item_row_hash(row3, SITE)

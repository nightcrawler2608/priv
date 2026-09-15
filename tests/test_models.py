"""Phase 3 tests: validation/cleaning. Pure, offline, no I/O."""
import logging

from scrapers.books_toscrape.models import Book, BookRecord, clean_and_validate


def _book(**overrides) -> Book:
    defaults = dict(url="https://example.com/b1", title="Good Book", price=10.0, rating=3, availability="In stock")
    defaults.update(overrides)
    return Book(**defaults)


def test_clean_and_validate_keeps_good_rows():
    result = clean_and_validate([_book()])
    assert len(result) == 1
    assert isinstance(result[0], BookRecord)
    assert result[0].title == "Good Book"


def test_clean_and_validate_rejects_negative_price(caplog):
    with caplog.at_level(logging.WARNING):
        result = clean_and_validate([_book(price=-5.0)])
    assert result == []
    assert "rejected row" in caplog.text


def test_clean_and_validate_rejects_blank_title(caplog):
    with caplog.at_level(logging.WARNING):
        result = clean_and_validate([_book(title="   ")])
    assert result == []


def test_clean_and_validate_rejects_out_of_range_rating(caplog):
    with caplog.at_level(logging.WARNING):
        result = clean_and_validate([_book(rating=9)])
    assert result == []


def test_clean_and_validate_keeps_good_rows_and_drops_bad_ones_in_same_batch():
    books = [_book(url="u1"), _book(url="u2", price=-1), _book(url="u3", rating=3)]
    result = clean_and_validate(books)
    assert [r.url for r in result] == ["u1", "u3"]


def test_row_hash_same_for_identical_fields():
    r1 = BookRecord(url="u1", title="A", price=10.0, rating=3, availability="In stock")
    r2 = BookRecord(url="u1", title="A", price=10.0, rating=3, availability="In stock")
    assert r1.row_hash() == r2.row_hash()


def test_row_hash_changes_when_price_changes():
    r1 = BookRecord(url="u1", title="A", price=10.0, rating=3, availability="In stock")
    r2 = BookRecord(url="u1", title="A", price=12.0, rating=3, availability="In stock")
    assert r1.row_hash() != r2.row_hash()


def test_in_stock_property():
    assert BookRecord(url="u", title="A", price=1.0, rating=1, availability="In stock").in_stock is True
    assert BookRecord(url="u", title="A", price=1.0, rating=1, availability="Out of stock").in_stock is False

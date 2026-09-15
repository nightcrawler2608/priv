"""Offline test: parses a saved HTML fixture, never hits the live site."""
from pathlib import Path

from scrapers.books_toscrape.scrape import parse_books

FIXTURE = Path(__file__).parent / "fixtures" / "books_page1.html"


def test_parse_books_returns_expected_count():
    html = FIXTURE.read_text(encoding="utf-8")
    books = parse_books(html)
    assert len(books) == 6


def test_parse_books_extracts_known_row():
    html = FIXTURE.read_text(encoding="utf-8")
    books = parse_books(html)
    first = books[0]
    assert first.title == "A Light in the Attic"
    assert first.price == 51.77
    assert first.rating == 3
    assert first.availability == "In stock"


def test_parse_books_handles_out_of_stock_and_zero_rating():
    html = FIXTURE.read_text(encoding="utf-8")
    books = parse_books(html)
    edge_case = next(b for b in books if b.title == "Unsellable Vaporware")
    assert edge_case.availability == "Out of stock"
    assert edge_case.rating == 0
    assert edge_case.price == 5.00


def test_all_prices_are_positive_floats():
    html = FIXTURE.read_text(encoding="utf-8")
    books = parse_books(html)
    assert all(isinstance(b.price, float) and b.price >= 0 for b in books)

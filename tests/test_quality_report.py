"""Phase 7 tests: per-run data quality report. Pure, offline."""
from scrapers.books_toscrape.models import Book, BookRecord
from scrapers.books_toscrape.quality import build_quality_report


def test_report_on_a_fully_healthy_run():
    raw = [Book(url="u1", title="A", price=10.0, rating=3, availability="In stock")]
    clean = [BookRecord(url="u1", title="A", price=10.0, rating=3, availability="In stock")]

    report = build_quality_report(raw, clean, current_row_count=1, previous_row_count=1)

    assert report["total_parsed"] == 1
    assert report["rejected"] == 0
    assert report["reject_ratio_pct"] == 0.0
    assert report["row_drop_pct"] == 0.0
    assert report["null_pct"] == {"title": 0.0, "price": 0.0, "rating": 0.0, "availability": 0.0}


def test_report_flags_blank_titles_as_null_pct():
    raw = [
        Book(url="u1", title="A", price=10.0, rating=3, availability="In stock"),
        Book(url="u2", title="   ", price=10.0, rating=3, availability="In stock"),
    ]
    clean = [BookRecord(url="u1", title="A", price=10.0, rating=3, availability="In stock")]

    report = build_quality_report(raw, clean, current_row_count=1, previous_row_count=None)

    assert report["null_pct"]["title"] == 50.0
    assert report["rejected"] == 1
    assert report["reject_ratio_pct"] == 50.0


def test_report_computes_row_drop_percentage():
    raw = [Book(url="u1", title="A", price=10.0, rating=3, availability="In stock")]
    clean = [BookRecord(url="u1", title="A", price=10.0, rating=3, availability="In stock")]

    report = build_quality_report(raw, clean, current_row_count=1, previous_row_count=10)

    assert report["row_drop_pct"] == 90.0


def test_report_handles_no_previous_run():
    report = build_quality_report([], [], current_row_count=0, previous_row_count=None)
    assert report["row_drop_pct"] is None
    assert report["reject_ratio_pct"] == 0.0

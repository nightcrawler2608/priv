"""
Tests for pagination batching: pages are validated and stored one at a
time instead of accumulating the whole site in memory before saving
anything. The property that actually matters and is worth testing
directly: if the scrape crashes partway through, rows from pages already
processed are NOT lost -- they were already committed to the database.
"""
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from scrapers.books_toscrape.models import Book, BookRecord
from scrapers.books_toscrape.quality import QualityAccumulator, build_quality_report
from scrapers.books_toscrape.storage.db import BookORM, get_engine, init_db
from scrapers.generic.models import FieldConfig, SiteDefinition
from scrapers.generic.quality import GenericQualityAccumulator, build_generic_quality_report

FIXTURE = Path(__file__).parent / "fixtures" / "books_page1.html"
PERMISSIVE_ROBOTS_TXT = "User-agent: *\nAllow: /\n"


def make_job(engine, *, max_pages=5, status="queued", **extra):
    import uuid
    from datetime import datetime, timezone
    from scrapers.books_toscrape.storage.db import JobORM

    job_id = uuid.uuid4().hex
    with Session(engine) as session:
        session.add(JobORM(
            id=job_id, status=status, max_pages=max_pages,
            created_at=datetime.now(timezone.utc),
            rows_new=0, rows_changed=0, rows_unchanged=0, rows_rejected=0,
            **extra,
        ))
        session.commit()
    return job_id


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    db_path = tmp_path / "test_batching.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr("api.tasks.fetch_robots_txt", lambda *a, **k: PERMISSIVE_ROBOTS_TXT)
    monkeypatch.setattr("api.tasks.save_raw_snapshot", lambda *a, **k: None)
    eng = get_engine()
    init_db(eng)
    return eng


def test_page_committed_before_a_later_page_crashes(engine, monkeypatch):
    """The core durability property of batching: if page 2 blows up, page
    1's rows must already be safely in the database, not lost."""

    def crashing_pages(*a, **k):
        yield 1, FIXTURE.read_text(encoding="utf-8")
        raise RuntimeError("simulated crash fetching page 2")

    monkeypatch.setattr("api.tasks.iter_catalogue_pages", crashing_pages)

    job_id = make_job(engine, max_pages=5)
    from api.tasks import run_scrape_job
    run_scrape_job(job_id, max_pages=5)

    from scrapers.books_toscrape.storage.db import JobORM
    with Session(engine) as session:
        job = session.get(JobORM, job_id)
        assert job.status == "failed"  # the job as a whole did fail...
        assert session.query(BookORM).count() == 6  # ...but page 1's 6 books were NOT lost


def test_quality_accumulator_matches_all_at_once_report():
    raw = [
        Book(url="u1", title="A", price=10.0, rating=3, availability="In stock"),
        Book(url="u2", title="", price=-1.0, rating=1, availability="In stock"),  # rejected
        Book(url="u3", title="C", price=5.0, rating=2, availability="Out of stock"),
    ]
    clean = [
        BookRecord(url="u1", title="A", price=10.0, rating=3, availability="In stock"),
        BookRecord(url="u3", title="C", price=5.0, rating=2, availability="Out of stock"),
    ]

    whole_report = build_quality_report(raw, clean, current_row_count=2, previous_row_count=10)

    accumulator = QualityAccumulator()
    accumulator.add_batch(raw[:1], clean[:1])   # page 1: just u1
    accumulator.add_batch(raw[1:], clean[1:])   # page 2: u2 (rejected) + u3
    streamed_report = accumulator.build_report(current_row_count=2, previous_row_count=10)

    assert streamed_report == whole_report


def test_generic_quality_accumulator_matches_all_at_once_report():
    site = SiteDefinition(
        id="s1", name="t", base_url="https://x/", list_url_template="https://x/{page}",
        item_selector="div", fields=[FieldConfig(name="title", selector="h1")],
    )
    raw = [{"_key": "k1", "title": "A"}, {"_key": "k2", "title": "  "}, {"_key": "k3", "title": "C"}]
    clean = [{"_key": "k1", "title": "A"}, {"_key": "k3", "title": "C"}]

    whole_report = build_generic_quality_report(raw, clean, site, current_row_count=2, previous_row_count=10)

    accumulator = GenericQualityAccumulator(site)
    accumulator.add_batch(raw[:1], clean[:1])
    accumulator.add_batch(raw[1:], clean[1:])
    streamed_report = accumulator.build_report(current_row_count=2, previous_row_count=10)

    assert streamed_report == whole_report

"""Phase 3 tests: idempotency and change detection against a real (local,
file-based) SQLite database via SQLAlchemy -- no live Postgres needed for
these tests, but the same upsert_books() code runs unchanged against
Postgres when DATABASE_URL points there."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from scrapers.books_toscrape.models import BookRecord
from scrapers.books_toscrape.storage.db import BookHistoryORM, BookORM, get_engine, init_db, upsert_books

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc)


def _engine(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path}/test.db")
    init_db(engine)
    return engine


def test_upsert_new_book_creates_current_row_and_history_row(tmp_path):
    engine = _engine(tmp_path)
    record = BookRecord(url="u1", title="A", price=10.0, rating=3, availability="In stock")

    with Session(engine) as session:
        stats = upsert_books(session, [record], scraped_at=T0)

    assert stats == {"new": 1, "changed": 0, "unchanged": 0}
    with Session(engine) as session:
        assert session.query(BookORM).count() == 1
        assert session.query(BookHistoryORM).count() == 1


def test_running_the_same_scrape_twice_is_idempotent(tmp_path):
    """Same data scraped twice must NOT create a duplicate history row --
    this is the idempotency check the spec calls for."""
    engine = _engine(tmp_path)
    record = BookRecord(url="u1", title="A", price=10.0, rating=3, availability="In stock")

    with Session(engine) as session:
        upsert_books(session, [record], scraped_at=T0)
    with Session(engine) as session:
        stats2 = upsert_books(session, [record], scraped_at=T1)

    assert stats2 == {"new": 0, "changed": 0, "unchanged": 1}
    with Session(engine) as session:
        assert session.query(BookORM).count() == 1
        assert session.query(BookHistoryORM).count() == 1  # still just one


def test_changed_row_updates_current_and_appends_history(tmp_path):
    engine = _engine(tmp_path)
    v1 = BookRecord(url="u1", title="A", price=10.0, rating=3, availability="In stock")
    v2 = BookRecord(url="u1", title="A", price=12.0, rating=3, availability="In stock")

    with Session(engine) as session:
        upsert_books(session, [v1], scraped_at=T0)
    with Session(engine) as session:
        stats2 = upsert_books(session, [v2], scraped_at=T1)

    assert stats2 == {"new": 0, "changed": 1, "unchanged": 0}
    with Session(engine) as session:
        current = session.get(BookORM, "u1")
        assert current.price == 12.0
        # SQLite drops tz-awareness on round-trip; compare naive wall-clock value
        assert current.last_changed_at == T1.replace(tzinfo=None)
        assert session.query(BookHistoryORM).count() == 2  # original + change


def test_out_of_stock_transition_is_recorded_as_a_change(tmp_path):
    engine = _engine(tmp_path)
    in_stock = BookRecord(url="u1", title="A", price=10.0, rating=3, availability="In stock")
    out_of_stock = BookRecord(url="u1", title="A", price=10.0, rating=3, availability="Out of stock")

    with Session(engine) as session:
        upsert_books(session, [in_stock], scraped_at=T0)
    with Session(engine) as session:
        stats2 = upsert_books(session, [out_of_stock], scraped_at=T1)

    assert stats2["changed"] == 1
    with Session(engine) as session:
        assert session.get(BookORM, "u1").availability == "Out of stock"

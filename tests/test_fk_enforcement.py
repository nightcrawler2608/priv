"""
Regression test for a real bug found while switching the database to
Postgres: `session.add(BookORM(...))` followed by `session.add(BookHistoryORM(...))`
in the same flush has no guaranteed insert order without an explicit ORM
`relationship()` between the two mappers. SQLite let the wrong order
through silently (it doesn't enforce foreign keys by default); Postgres
correctly rejected it as a foreign key violation the moment a real
instance was tried.

This test catches the same class of bug without needing a real Postgres
server: SQLite *can* enforce foreign keys, it just isn't on by default --
this test turns it on for one throwaway engine and proves upsert_books()
behaves correctly under real FK enforcement, so this regression is caught
by the normal (offline, no external services) test suite from now on.
"""
from datetime import datetime, timezone

from sqlalchemy import event
from sqlalchemy.orm import Session

from scrapers.books_toscrape.models import BookRecord
from scrapers.books_toscrape.storage.db import BookHistoryORM, BookORM, get_engine, init_db, upsert_books

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _fk_enforced_engine(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path}/fk_test.db")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    init_db(engine)
    return engine


def test_new_books_can_be_inserted_with_foreign_keys_enforced(tmp_path):
    engine = _fk_enforced_engine(tmp_path)
    records = [
        BookRecord(url=f"u{i}", title=f"Book {i}", price=float(i), rating=1, availability="In stock")
        for i in range(5)
    ]

    with Session(engine) as session:
        stats = upsert_books(session, records, scraped_at=NOW)

    assert stats == {"new": 5, "changed": 0, "unchanged": 0}
    with Session(engine) as session:
        assert session.query(BookORM).count() == 5
        assert session.query(BookHistoryORM).count() == 5

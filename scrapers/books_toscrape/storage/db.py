"""
Phase 3: structured storage via SQLAlchemy.

Two tables:
- books        current state, one row per book (keyed by url).
- book_history append-only; a new row is written ONLY when a book's
                row_hash changes (idempotency + change detection).

Points at PostgreSQL in production via the DATABASE_URL env var, e.g.
    postgresql+psycopg2://user:pass@host:5432/scraper
Defaults to a local SQLite file so the pipeline (and its tests) run with
zero external services during development -- swap DATABASE_URL when a real
Postgres instance is available; the ORM code doesn't change either way.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from ..models import BookRecord

DEFAULT_DB_URL = "sqlite:///data/books.db"


class Base(DeclarativeBase):
    pass


class BookORM(Base):
    __tablename__ = "books"

    url: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    availability: Mapped[str] = mapped_column(String, nullable=False)
    row_hash: Mapped[str] = mapped_column(String, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class BookHistoryORM(Base):
    __tablename__ = "book_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String, ForeignKey("books.url"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    availability: Mapped[str] = mapped_column(String, nullable=False)
    row_hash: Mapped[str] = mapped_column(String, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


def get_engine(db_url: str | None = None):
    url = db_url or os.environ.get("DATABASE_URL", DEFAULT_DB_URL)
    if url.startswith("sqlite:///") and not url.endswith(":memory:"):
        path = Path(url.replace("sqlite:///", "", 1))
        if str(path):
            path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)


def upsert_books(
    session: Session,
    records: list[BookRecord],
    scraped_at: datetime | None = None,
) -> dict[str, int]:
    """Idempotent upsert. Running this twice with identical records leaves
    `book_history` unchanged the second time -- only new or changed rows
    get a new history entry. Returns counts for a data-quality report."""
    scraped_at = scraped_at or datetime.now(timezone.utc)
    stats = {"new": 0, "changed": 0, "unchanged": 0}

    for rec in records:
        h = rec.row_hash()
        existing = session.get(BookORM, rec.url)

        if existing is None:
            session.add(BookORM(
                url=rec.url, title=rec.title, price=rec.price, rating=rec.rating,
                availability=rec.availability, row_hash=h,
                first_seen_at=scraped_at, last_seen_at=scraped_at, last_changed_at=scraped_at,
            ))
            session.add(BookHistoryORM(
                url=rec.url, title=rec.title, price=rec.price, rating=rec.rating,
                availability=rec.availability, row_hash=h, recorded_at=scraped_at,
            ))
            stats["new"] += 1
            continue

        existing.last_seen_at = scraped_at
        if existing.row_hash != h:
            existing.title = rec.title
            existing.price = rec.price
            existing.rating = rec.rating
            existing.availability = rec.availability
            existing.row_hash = h
            existing.last_changed_at = scraped_at
            session.add(BookHistoryORM(
                url=rec.url, title=rec.title, price=rec.price, rating=rec.rating,
                availability=rec.availability, row_hash=h, recorded_at=scraped_at,
            ))
            stats["changed"] += 1
        else:
            stats["unchanged"] += 1

    session.commit()
    return stats

"""
Phase 3+4: structured storage via SQLAlchemy.

Tables:
- books         current state, one row per book (keyed by url).
- book_history  append-only; a new row is written ONLY when a book's
                 row_hash changes (idempotency + change detection). Tagged
                 with the job_id that produced it, so a job's results are
                 queryable on their own (Phase 4's GET /jobs/{id}/results).
- jobs          one row per scrape job triggered via the API (Phase 4).

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

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from ..models import BookRecord

DEFAULT_DB_URL = "sqlite:///data/books.db"


class Base(DeclarativeBase):
    pass


class JobORM(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    max_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rows_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    # Phase 6: automation bookkeeping.
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    triggered_by: Mapped[str] = mapped_column(String, nullable=False, default="manual")  # manual|scheduled|retry
    quality_warnings: Mapped[str | None] = mapped_column(String, nullable=True)  # "; "-joined, empty/None if healthy
    permanently_failed: Mapped[bool] = mapped_column(default=False)  # retries exhausted, already alerted -- don't re-alert
    quality_report: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON string, see quality.build_quality_report
    # "config-driven sites" feature: set for a job run against a generic
    # SiteDefinition (scrapers/generic), None for the books_toscrape jobs
    # from Phases 1-7. Deliberately NOT a ForeignKey: this core module must
    # stay usable (and its tables creatable) without importing the optional
    # scrapers.generic package -- a real DB-level FK here would mean
    # init_db()/any flush breaks whenever generic.storage (which owns the
    # `sites` table) hasn't been imported yet. Referential integrity for
    # this column is enforced at the application level instead.
    site_id: Mapped[str | None] = mapped_column(String, nullable=True)


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
    job_id: Mapped[str | None] = mapped_column(String, ForeignKey("jobs.id"), nullable=True)
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


def previous_successful_row_count(session: Session, before_job_id: str) -> int | None:
    """Total rows (new+changed+unchanged) from the most recent job that
    succeeded before this one -- the baseline check_job_quality() compares
    against to spot a sudden drop. None if there is no prior successful run."""
    before = session.get(JobORM, before_job_id)
    if before is None:
        return None
    prev = session.scalars(
        select(JobORM)
        .where(
            JobORM.status == "succeeded",
            JobORM.id != before_job_id,
            JobORM.created_at < before.created_at,
        )
        .order_by(JobORM.created_at.desc())
        .limit(1)
    ).first()
    if prev is None:
        return None
    return prev.rows_new + prev.rows_changed + prev.rows_unchanged


def upsert_books(
    session: Session,
    records: list[BookRecord],
    scraped_at: datetime | None = None,
    job_id: str | None = None,
) -> dict[str, int]:
    """Idempotent upsert. Running this twice with identical records leaves
    `book_history` unchanged the second time -- only new or changed rows
    get a new history entry. Returns counts for a data-quality report.

    job_id, when given, tags each new history row so a specific job's
    results can be queried back out (see api/main.py's /results endpoint)."""
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
            # Flush the parent row before adding the history row that
            # references it. Without an ORM relationship(), SQLAlchemy's
            # unit-of-work doesn't guarantee insert order between these two
            # mappers -- SQLite let a wrong order through silently (it
            # doesn't enforce foreign keys by default); Postgres correctly
            # rejects it as a real FK violation.
            session.flush()
            session.add(BookHistoryORM(
                url=rec.url, job_id=job_id, title=rec.title, price=rec.price, rating=rec.rating,
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
                url=rec.url, job_id=job_id, title=rec.title, price=rec.price, rating=rec.rating,
                availability=rec.availability, row_hash=h, recorded_at=scraped_at,
            ))
            stats["changed"] += 1
        else:
            stats["unchanged"] += 1

    session.commit()
    return stats

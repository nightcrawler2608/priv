"""
Generic storage for config-driven sites. Uses the SAME SQLAlchemy Base
(and therefore the same database/engine) as scrapers/books_toscrape/storage/db.py
-- one shared database, one shared `jobs` table, with these tables added
alongside `books`/`book_history` rather than replacing them.

Because a site's fields aren't known in advance, items are stored as JSON
(`data_json`) instead of fixed columns -- the tradeoff for "any site,
any fields" without a schema migration per site.

sites          one row per saved SiteDefinition.
items          current state, one row per item (keyed by site_id + item_key).
item_history   append-only; a new row only when an item's row_hash changes
               (same idempotency/change-detection pattern as Phase 3),
               tagged with the job_id that produced it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..books_toscrape.storage.db import Base
from .models import SiteDefinition
from .validate import item_row_hash


class SiteORM(Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    base_url: Mapped[str] = mapped_column(String, nullable=False)
    list_url_template: Mapped[str] = mapped_column(String, nullable=False)
    item_selector: Mapped[str] = mapped_column(String, nullable=False)
    key_selector: Mapped[str | None] = mapped_column(String, nullable=True)
    key_attr: Mapped[str] = mapped_column(String, nullable=False, default="href")
    fields_json: Mapped[str] = mapped_column(String, nullable=False)  # JSON list of FieldConfig dicts
    max_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    def to_site_definition(self) -> SiteDefinition:
        return SiteDefinition(
            id=self.id, name=self.name, base_url=self.base_url,
            list_url_template=self.list_url_template, item_selector=self.item_selector,
            key_selector=self.key_selector, key_attr=self.key_attr,
            fields=json.loads(self.fields_json), max_pages=self.max_pages,
        )


class ItemORM(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # f"{site_id}:{item_key}"
    site_id: Mapped[str] = mapped_column(String, ForeignKey("sites.id"), nullable=False)
    item_key: Mapped[str] = mapped_column(String, nullable=False)
    data_json: Mapped[str] = mapped_column(String, nullable=False)
    row_hash: Mapped[str] = mapped_column(String, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ItemHistoryORM(Base):
    __tablename__ = "item_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(String, ForeignKey("sites.id"), nullable=False)
    item_key: Mapped[str] = mapped_column(String, nullable=False)
    job_id: Mapped[str | None] = mapped_column(String, ForeignKey("jobs.id"), nullable=True)
    data_json: Mapped[str] = mapped_column(String, nullable=False)
    row_hash: Mapped[str] = mapped_column(String, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


def upsert_items(
    session: Session,
    site: SiteDefinition,
    records: list[dict],
    job_id: str | None = None,
    scraped_at: datetime | None = None,
) -> dict[str, int]:
    """Same idempotent-upsert pattern as books_toscrape.storage.db.upsert_books,
    generalized to arbitrary fields via row dicts."""
    scraped_at = scraped_at or datetime.now(timezone.utc)
    stats = {"new": 0, "changed": 0, "unchanged": 0}

    for row in records:
        item_key = row["_key"]
        h = item_row_hash(row, site)
        data_json = json.dumps({f.name: row.get(f.name) for f in site.fields})
        pk = f"{site.id}:{item_key}"

        existing = session.get(ItemORM, pk)
        if existing is None:
            session.add(ItemORM(
                id=pk, site_id=site.id, item_key=item_key, data_json=data_json,
                row_hash=h, first_seen_at=scraped_at, last_seen_at=scraped_at, last_changed_at=scraped_at,
            ))
            session.add(ItemHistoryORM(
                site_id=site.id, item_key=item_key, job_id=job_id,
                data_json=data_json, row_hash=h, recorded_at=scraped_at,
            ))
            stats["new"] += 1
            continue

        existing.last_seen_at = scraped_at
        if existing.row_hash != h:
            existing.data_json = data_json
            existing.row_hash = h
            existing.last_changed_at = scraped_at
            session.add(ItemHistoryORM(
                site_id=site.id, item_key=item_key, job_id=job_id,
                data_json=data_json, row_hash=h, recorded_at=scraped_at,
            ))
            stats["changed"] += 1
        else:
            stats["unchanged"] += 1

    session.commit()
    return stats


def previous_successful_row_count_for_site(session: Session, site_id: str, before_job_id: str) -> int | None:
    """Same idea as books_toscrape's previous_successful_row_count, scoped
    to a site: total item_history rows recorded by the most recent earlier
    job for this same site."""
    from ..books_toscrape.storage.db import JobORM  # local import: avoids a module-load cycle with db.py

    before = session.get(JobORM, before_job_id)
    if before is None:
        return None
    prev_job = session.scalars(
        select(JobORM)
        .where(
            JobORM.status == "succeeded",
            JobORM.site_id == site_id,
            JobORM.id != before_job_id,
            JobORM.created_at < before.created_at,
        )
        .order_by(JobORM.created_at.desc())
        .limit(1)
    ).first()
    if prev_job is None:
        return None
    return prev_job.rows_new + prev_job.rows_changed + prev_job.rows_unchanged

"""
Phase 4: the Celery task a worker actually runs.

This is the scrape pipeline from Phase 1-3 (robots check -> paginate ->
snapshot -> parse -> validate -> upsert) wrapped so a job's status/counts
are recorded in the `jobs` table as it runs. Any exception anywhere in the
pipeline is caught and turns into status="failed" with the error message
saved -- a job can never get stuck in "running" forever because its worker
died or a page broke; it always resolves to succeeded or failed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from scrapers.books_toscrape.models import Book, clean_and_validate
from scrapers.books_toscrape.scrape import (
    BASE_URL,
    fetch_robots_txt,
    is_allowed,
    iter_catalogue_pages,
    parse_books,
)
from scrapers.books_toscrape.storage.db import JobORM, get_engine, init_db, upsert_books
from scrapers.books_toscrape.storage.raw_snapshots import save_raw_snapshot

from .celery_app import celery_app


@celery_app.task(name="run_scrape_job")
def run_scrape_job(job_id: str, max_pages: int = 50) -> None:
    engine = get_engine()
    init_db(engine)

    with Session(engine) as session:
        job = session.get(JobORM, job_id)
        if job is None:
            return  # job row vanished/never existed -- nothing to run against

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        session.commit()

        try:
            robots_txt = fetch_robots_txt()
            if not is_allowed(robots_txt, "/catalogue/page-1.html"):
                raise RuntimeError("robots.txt disallows the catalogue path")

            raw_books: list[Book] = []
            for page_num, html in iter_catalogue_pages(max_pages=max_pages, delay_seconds=1.0):
                page_url = f"{BASE_URL}catalogue/page-{page_num}.html"
                save_raw_snapshot(html, page_num, Path("data/raw_html"))
                raw_books.extend(parse_books(html, page_url=page_url))

            clean_books = clean_and_validate(raw_books)
            rejected = len(raw_books) - len(clean_books)
            stats = upsert_books(session, clean_books, job_id=job_id)

            job.status = "succeeded"
            job.rows_new = stats["new"]
            job.rows_changed = stats["changed"]
            job.rows_unchanged = stats["unchanged"]
            job.rows_rejected = rejected
            job.finished_at = datetime.now(timezone.utc)
            session.commit()

        except Exception as exc:  # noqa: BLE001 -- deliberately broad: any failure must resolve the job, never leave it stuck
            session.rollback()
            job = session.get(JobORM, job_id)
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            session.commit()

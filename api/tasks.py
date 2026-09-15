"""
Phase 4+6: Celery tasks.

run_scrape_job        the pipeline itself, wrapped with status tracking,
                       a quality gate, and alerting. Always resolves the
                       job to succeeded/failed -- never stuck running.
scheduled_scrape       creates a job row and runs it -- what Celery Beat
                       calls on a timer (see celery_app.py's beat_schedule).
retry_failed_jobs      finds recently failed jobs under the configured
                       retry cap and re-queues them; gives up (and alerts)
                       once a job has been retried max_retries times.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from scrapers.books_toscrape.alerts import send_alert
from scrapers.books_toscrape.config import DEFAULT_CONFIG_PATH, load_config
from scrapers.books_toscrape.models import Book, clean_and_validate
from scrapers.books_toscrape.quality import check_job_quality
from scrapers.books_toscrape.scrape import (
    BASE_URL,
    fetch_robots_txt,
    is_allowed,
    iter_catalogue_pages,
    parse_books,
)
from scrapers.books_toscrape.storage.db import (
    JobORM,
    get_engine,
    init_db,
    previous_successful_row_count,
    upsert_books,
)
from scrapers.books_toscrape.storage.raw_snapshots import save_raw_snapshot

from .celery_app import celery_app


@celery_app.task(name="run_scrape_job")
def run_scrape_job(
    job_id: str,
    max_pages: int = 50,
    max_reject_ratio: float = 0.5,
    max_row_drop_ratio: float = 0.4,
) -> None:
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

            current_row_count = stats["new"] + stats["changed"] + stats["unchanged"]
            baseline = previous_successful_row_count(session, job_id)
            warnings = check_job_quality(
                current_row_count=current_row_count,
                previous_row_count=baseline,
                rejected=rejected,
                total_parsed=len(raw_books),
                max_reject_ratio=max_reject_ratio,
                max_row_drop_ratio=max_row_drop_ratio,
            )
            if warnings:
                job.quality_warnings = "; ".join(warnings)
                session.commit()
                send_alert(
                    f"Data quality warning on job {job_id} ({job.triggered_by}): " + "; ".join(warnings),
                    details={"job_id": job_id, "warnings": warnings},
                )

        except Exception as exc:  # noqa: BLE001 -- deliberately broad: any failure must resolve the job, never leave it stuck
            session.rollback()
            job = session.get(JobORM, job_id)
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            session.commit()
            # No alert here -- retry_failed_jobs is the only place that knows
            # whether this job's retry budget is exhausted; alerting here
            # would fire on every transient failure, not just permanent ones.


def _create_job_row(session: Session, max_pages: int, triggered_by: str) -> str:
    job_id = uuid.uuid4().hex
    session.add(JobORM(
        id=job_id, status="queued", max_pages=max_pages,
        created_at=datetime.now(timezone.utc),
        rows_new=0, rows_changed=0, rows_unchanged=0, rows_rejected=0,
        triggered_by=triggered_by,
    ))
    session.commit()
    return job_id


@celery_app.task(name="scheduled_scrape")
def scheduled_scrape(max_pages: int = 50, max_reject_ratio: float = 0.5, max_row_drop_ratio: float = 0.4) -> str:
    """What Celery Beat fires on a timer: create a job row exactly like
    the API does, then run it through the same pipeline as a manual job."""
    engine = get_engine()
    init_db(engine)
    with Session(engine) as session:
        job_id = _create_job_row(session, max_pages, triggered_by="scheduled")

    run_scrape_job(job_id, max_pages, max_reject_ratio, max_row_drop_ratio)
    return job_id


@celery_app.task(name="run_scrape_job_from_config")
def run_scrape_job_from_config(config_path: str = str(DEFAULT_CONFIG_PATH)) -> str:
    """Beat schedule entry point: read the site's YAML config for its page
    limit and quality thresholds, then run a scheduled scrape with them."""
    cfg = load_config(config_path)
    return scheduled_scrape(
        max_pages=cfg.max_pages,
        max_reject_ratio=cfg.quality.max_reject_ratio,
        max_row_drop_ratio=cfg.quality.max_row_drop_ratio,
    )


@celery_app.task(name="retry_failed_jobs")
def retry_failed_jobs(max_retries: int = 3) -> dict[str, list[str]]:
    """Self-healing retry: re-queue any failed job that hasn't already
    exhausted its retry budget (transient errors deserve another try). A
    job that's already used up its retries is left alone -- retrying it
    forever would just hammer a site that's genuinely blocking us or
    permanently broken -- and is alerted on exactly once (permanently_failed
    guards against re-alerting on every future call)."""
    engine = get_engine()
    init_db(engine)

    with Session(engine) as session:
        failed_jobs = session.scalars(select(JobORM).where(JobORM.status == "failed")).all()

        to_retry = [(j.id, j.max_pages) for j in failed_jobs if j.retry_count < max_retries]
        to_give_up = [j for j in failed_jobs if j.retry_count >= max_retries and not j.permanently_failed]

        for job in to_give_up:
            job.permanently_failed = True
            session.commit()
            send_alert(
                f"Job {job.id} failed permanently after {job.retry_count} retries: {job.error_message}",
                details={"job_id": job.id, "error": job.error_message},
            )

        for job_id, _ in to_retry:
            job = session.get(JobORM, job_id)
            job.retry_count += 1
            job.status = "queued"
            job.error_message = None
            job.triggered_by = "retry"
            session.commit()

    for job_id, max_pages in to_retry:
        run_scrape_job(job_id, max_pages)

    return {"retried": [j for j, _ in to_retry], "gave_up": [j.id for j in to_give_up]}

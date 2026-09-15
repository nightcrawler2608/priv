"""
The Celery task behind a config-driven site's scrape job -- same shape as
api/tasks.py's run_scrape_job (status tracking, quality gate, alerting,
always resolves to succeeded/failed), generalized to run against a
SiteDefinition instead of the hardcoded books_toscrape pipeline.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from sqlalchemy.orm import Session

from scrapers.books_toscrape.alerts import send_alert
from scrapers.books_toscrape.logging_config import configure_logging
from scrapers.books_toscrape.quality import check_job_quality
from scrapers.books_toscrape.storage.db import JobORM, get_engine, init_db
from scrapers.books_toscrape.storage.raw_snapshots import save_raw_snapshot
from scrapers.common.fetch import fetch_robots_txt, is_allowed
from scrapers.generic.fetch import iter_list_pages
from scrapers.generic.parser import parse_items
from scrapers.generic.quality import build_generic_quality_report
from scrapers.generic.storage import (
    SiteORM,
    previous_successful_row_count_for_site,
    upsert_items,
)
from scrapers.generic.validate import clean_and_validate_items

from .celery_app import celery_app


@celery_app.task(name="run_generic_scrape_job")
def run_generic_scrape_job(
    job_id: str,
    site_id: str,
    max_reject_ratio: float = 0.5,
    max_row_drop_ratio: float = 0.4,
) -> None:
    configure_logging()
    engine = get_engine()
    init_db(engine)

    with Session(engine) as session:
        job = session.get(JobORM, job_id)
        site_row = session.get(SiteORM, site_id)
        if job is None or site_row is None:
            logger.warning("run_generic_scrape_job called with unknown job_id={} or site_id={}", job_id, site_id)
            return
        site = site_row.to_site_definition()

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        session.commit()
        logger.info("job {} started for site {} ({})", job_id, site.name, site.base_url)

        try:
            robots_txt = fetch_robots_txt(site.base_url)
            # Checked against the site's root -- good enough as a first
            # cut; a real per-path check would need the first list URL.
            if not is_allowed(robots_txt, "/"):
                raise RuntimeError(f"robots.txt disallows scraping {site.base_url}")

            raw_items: list[dict] = []
            for page_num, html, page_url in iter_list_pages(site, delay_seconds=1.0):
                save_raw_snapshot(html, page_num, Path("data/raw_html") / site.id)
                raw_items.extend(parse_items(html, page_url, site))

            clean_items, rejected = clean_and_validate_items(raw_items, site)
            stats = upsert_items(session, site, clean_items, job_id=job_id)

            job.status = "succeeded"
            job.rows_new = stats["new"]
            job.rows_changed = stats["changed"]
            job.rows_unchanged = stats["unchanged"]
            job.rows_rejected = rejected
            job.finished_at = datetime.now(timezone.utc)
            session.commit()

            current_row_count = stats["new"] + stats["changed"] + stats["unchanged"]
            baseline = previous_successful_row_count_for_site(session, site.id, job_id)

            report = build_generic_quality_report(raw_items, clean_items, site, current_row_count, baseline)
            job.quality_report = json.dumps(report)
            session.commit()
            logger.bind(job_id=job_id, site_id=site.id, quality_report=report).info(
                "job {} finished: {} new, {} changed, {} unchanged, {} rejected",
                job_id, stats["new"], stats["changed"], stats["unchanged"], rejected,
            )

            warnings = check_job_quality(
                current_row_count=current_row_count,
                previous_row_count=baseline,
                rejected=rejected,
                total_parsed=len(raw_items),
                max_reject_ratio=max_reject_ratio,
                max_row_drop_ratio=max_row_drop_ratio,
            )
            if warnings:
                job.quality_warnings = "; ".join(warnings)
                session.commit()
                logger.warning("job {} quality warnings: {}", job_id, warnings)
                send_alert(
                    f"Data quality warning on job {job_id} for site {site.name}: " + "; ".join(warnings),
                    details={"job_id": job_id, "site_id": site.id, "warnings": warnings},
                )

        except Exception as exc:  # noqa: BLE001 -- any failure must resolve the job, never leave it stuck
            session.rollback()
            job = session.get(JobORM, job_id)
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            session.commit()
            logger.exception("job {} (site {}) failed", job_id, site_id)

"""
Phase 6 tests: quality-triggered alerts, self-healing retries with a cap,
and scheduled/config-driven runs -- exercised through the real Celery task
functions (called directly, which runs them synchronously regardless of
broker/eager settings), with the pipeline's network calls faked the same
way as tests/test_api.py. Fully offline.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from scrapers.books_toscrape.models import Book
from scrapers.books_toscrape.storage.db import JobORM, get_engine, init_db

FIXTURE = Path(__file__).parent / "fixtures" / "books_page1.html"
PERMISSIVE_ROBOTS_TXT = "User-agent: *\nAllow: /\n"


def make_job(engine, *, max_pages=1, status="queued", **extra):
    job_id = uuid.uuid4().hex
    with Session(engine) as session:
        job = JobORM(
            id=job_id, status=status, max_pages=max_pages,
            created_at=datetime.now(timezone.utc),
            rows_new=0, rows_changed=0, rows_unchanged=0, rows_rejected=0,
            **extra,
        )
        session.add(job)
        session.commit()
    return job_id


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    db_path = tmp_path / "test_automation.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    monkeypatch.setattr("api.tasks.fetch_robots_txt", lambda *a, **k: PERMISSIVE_ROBOTS_TXT)
    monkeypatch.setattr(
        "api.tasks.iter_catalogue_pages",
        lambda *a, **k: iter([(1, FIXTURE.read_text(encoding="utf-8"))]),
    )
    monkeypatch.setattr("api.tasks.save_raw_snapshot", lambda *a, **k: None)

    eng = get_engine()
    init_db(eng)
    return eng


def test_quality_alert_fires_when_a_selector_breaks(engine, monkeypatch):
    """Selector breakage doesn't crash the pipeline -- it just produces
    rows that fail validation. This is exactly the scenario the spec's
    'break a selector on purpose' check describes."""

    def broken_parse_books(html, page_url=None):
        return [Book(url=f"u{i}", title=f"t{i}", price=-1.0, rating=1, availability="In stock") for i in range(10)]

    monkeypatch.setattr("api.tasks.parse_books", broken_parse_books)

    alerts = []
    monkeypatch.setattr("api.tasks.send_alert", lambda msg, details=None: alerts.append((msg, details)) or True)

    job_id = make_job(engine, max_pages=1)
    from api.tasks import run_scrape_job
    run_scrape_job(job_id, max_pages=1)

    with Session(engine) as session:
        job = session.get(JobORM, job_id)
        assert job.status == "succeeded"  # the process didn't crash...
        assert job.rows_rejected == 10  # ...but the data is worthless
        assert job.quality_warnings and "rejected" in job.quality_warnings

    assert len(alerts) == 1
    assert "rejected" in alerts[0][0]


def test_healthy_run_never_alerts(engine, monkeypatch):
    alerts = []
    monkeypatch.setattr("api.tasks.send_alert", lambda msg, details=None: alerts.append(msg) or True)

    job_id = make_job(engine, max_pages=1)
    from api.tasks import run_scrape_job
    run_scrape_job(job_id, max_pages=1)

    with Session(engine) as session:
        job = session.get(JobORM, job_id)
        assert job.status == "succeeded"
        assert job.quality_warnings is None
    assert alerts == []


def test_retry_failed_jobs_requeues_under_cap_and_succeeds(engine):
    job_id = make_job(engine, max_pages=1, status="failed", error_message="boom", retry_count=0)

    from api.tasks import retry_failed_jobs
    result = retry_failed_jobs(max_retries=3)

    assert job_id in result["retried"]
    with Session(engine) as session:
        job = session.get(JobORM, job_id)
        assert job.status == "succeeded"
        assert job.retry_count == 1
        assert job.triggered_by == "retry"


def test_retry_failed_jobs_gives_up_after_cap_and_alerts_exactly_once(engine, monkeypatch):
    job_id = make_job(engine, max_pages=1, status="failed", error_message="boom", retry_count=3)

    alerts = []
    monkeypatch.setattr("api.tasks.send_alert", lambda msg, details=None: alerts.append(msg) or True)

    from api.tasks import retry_failed_jobs
    result1 = retry_failed_jobs(max_retries=3)
    assert result1["retried"] == []
    assert job_id in result1["gave_up"]
    assert len(alerts) == 1

    # calling again must not re-alert -- permanently_failed guards against that
    result2 = retry_failed_jobs(max_retries=3)
    assert result2["gave_up"] == []
    assert len(alerts) == 1

    with Session(engine) as session:
        job = session.get(JobORM, job_id)
        assert job.permanently_failed is True
        assert job.status == "failed"


def test_scheduled_scrape_creates_and_runs_a_job(engine):
    from api.tasks import scheduled_scrape
    job_id = scheduled_scrape(max_pages=1)

    with Session(engine) as session:
        job = session.get(JobORM, job_id)
        assert job.triggered_by == "scheduled"
        assert job.status == "succeeded"
        assert job.rows_new == 6


def test_run_scrape_job_from_config_uses_yaml_settings(engine, tmp_path):
    cfg_path = tmp_path / "site.yaml"
    cfg_path.write_text("name: test\nbase_url: https://x\nschedule: '0 * * * *'\nmax_pages: 1\n")

    from api.tasks import run_scrape_job_from_config
    job_id = run_scrape_job_from_config(str(cfg_path))

    with Session(engine) as session:
        job = session.get(JobORM, job_id)
        assert job.max_pages == 1
        assert job.status == "succeeded"

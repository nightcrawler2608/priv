"""
Phase 4: Celery app config.

REDIS_URL points Celery at the broker (job queue) and result backend.
CELERY_TASK_ALWAYS_EAGER=true runs tasks synchronously in-process with no
broker at all -- used by the test suite so it never needs a live Redis
server; leave it unset/false to run for real behind a `celery -A api.celery_app worker`
process against an actual Redis instance.
"""
from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("scraper", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.task_always_eager = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"
celery_app.conf.task_eager_propagates = True


def cron_to_crontab(expr: str) -> crontab:
    """Turn a standard 5-field cron string ("0 * * * *") into the crontab
    object Celery Beat wants -- lets a site's schedule live in its YAML
    config instead of being hardcoded here."""
    minute, hour, day_of_month, month_of_year, day_of_week = expr.split()
    return crontab(
        minute=minute, hour=hour,
        day_of_month=day_of_month, month_of_year=month_of_year, day_of_week=day_of_week,
    )


# Celery Beat entry points. Run a beat process alongside a worker to fire
# these on schedule:  celery -A api.celery_app beat --loglevel=info
celery_app.conf.beat_schedule = {
    "books-toscrape-scheduled-scrape": {
        "task": "run_scrape_job_from_config",
        "schedule": cron_to_crontab("0 * * * *"),  # hourly, matches config/books_toscrape.yaml
    },
    "retry-failed-jobs": {
        "task": "retry_failed_jobs",
        "schedule": crontab(minute="*/15"),
    },
}

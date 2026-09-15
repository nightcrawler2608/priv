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

# Import the task modules so their @celery_app.task-decorated functions
# actually register with this app. This matters for a STANDALONE worker
# process (`celery -A api.celery_app worker`, exactly what docker-compose's
# worker/beat services run) -- such a process never imports api.main, so
# without this import it would start up with zero registered tasks and
# every job would sit "queued" forever, never picked up. api.main ends up
# importing these too (it needs run_scrape_job directly), which is why this
# gap never showed up in tests -- they all run in the same process as
# api.main. Import at the bottom, after `celery_app` is defined above: task
# modules do `from .celery_app import celery_app` themselves, which is safe
# here since that name is already set on this (partially initialized)
# module by the time Python reaches these lines.
from . import generic_tasks as _generic_tasks  # noqa: E402,F401
from . import tasks as _tasks  # noqa: E402,F401

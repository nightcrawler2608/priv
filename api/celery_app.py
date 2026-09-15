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

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("scraper", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.task_always_eager = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"
celery_app.conf.task_eager_propagates = True

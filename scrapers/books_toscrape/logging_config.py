"""
Phase 7: structured logging via loguru.

Call configure_logging() once, at each entry point (uvicorn startup,
Celery worker startup, `python -m scrapers.books_toscrape.scrape`). Logs go
to stdout (human-readable, for local dev) and to a rotating JSON file (for
anything that later ships logs to a log aggregator) at the same time --
loguru calls this "serialize".
"""
from __future__ import annotations

import os
import sys

from loguru import logger

_CONFIGURED = False


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return  # idempotent -- safe to call from multiple entry points

    level = os.environ.get("LOG_LEVEL", "INFO")

    try:
        logger.remove(0)  # drop loguru's default stderr handler (always id 0); leave any handler
    except ValueError:  # added by something else (e.g. a test fixture) alone -- never wipe those
        pass
    logger.add(sys.stdout, level=level, backtrace=False, diagnose=False)
    logger.add(
        "data/logs/scraper.jsonl",
        level=level,
        serialize=True,  # one JSON object per line -- machine-parseable
        rotation="10 MB",
        retention="14 days",
        backtrace=False,
        diagnose=False,
    )

    dsn = os.environ.get("SENTRY_DSN")
    if dsn:
        import sentry_sdk
        sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0, environment=os.environ.get("ENVIRONMENT", "development"))
        logger.info("Sentry error tracking enabled")
    else:
        logger.debug("SENTRY_DSN not set -- Sentry error tracking disabled")

    _CONFIGURED = True

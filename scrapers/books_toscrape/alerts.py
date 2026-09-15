"""
Phase 6: failure/quality alerts. Posts a small JSON payload to a webhook --
an n8n workflow, a Slack incoming webhook, anything that accepts
{"text": ..., ...}. Alerting is opt-in: with no ALERT_WEBHOOK_URL set,
send_alert() just logs and returns False instead of raising, so running
the pipeline without any alerting configured (e.g. in tests, or a first
local run) never breaks.
"""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)


def send_alert(message: str, details: dict | None = None) -> bool:
    webhook_url = os.environ.get("ALERT_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("ALERT (no ALERT_WEBHOOK_URL configured, not sent): %s", message)
        return False

    payload = {"text": message, **(details or {})}
    try:
        requests.post(webhook_url, json=payload, timeout=5)
        return True
    except requests.RequestException:
        logger.exception("failed to deliver alert webhook")
        return False

"""Phase 6 tests: alert delivery. Offline -- requests.post is mocked, no
real webhook is ever hit."""
import pytest
from scrapers.books_toscrape.alerts import send_alert


def test_send_alert_returns_false_and_does_not_raise_when_unconfigured(monkeypatch):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    assert send_alert("something broke") is False


def test_send_alert_posts_to_configured_webhook(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example.com/incoming")

    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json, timeout))

        class Resp:
            status_code = 200

        return Resp()

    monkeypatch.setattr("scrapers.books_toscrape.alerts.requests.post", fake_post)

    result = send_alert("selector broke", details={"job_id": "abc123"})

    assert result is True
    assert len(calls) == 1
    url, payload, timeout = calls[0]
    assert url == "https://hooks.example.com/incoming"
    assert payload["text"] == "selector broke"
    assert payload["job_id"] == "abc123"


def test_send_alert_swallows_delivery_errors(monkeypatch):
    import requests

    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example.com/incoming")

    def raising_post(*args, **kwargs):
        raise requests.exceptions.ConnectionError("dns failure")

    monkeypatch.setattr("scrapers.books_toscrape.alerts.requests.post", raising_post)

    assert send_alert("won't crash the caller") is False

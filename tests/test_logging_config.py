"""Phase 7 tests: logging/Sentry bootstrap. Offline -- no real Sentry DSN,
sentry_sdk.init is mocked so nothing is ever actually sent."""
import importlib

from scrapers.books_toscrape import logging_config


def _reset():
    logging_config._CONFIGURED = False


def test_configure_logging_is_idempotent():
    _reset()
    logging_config.configure_logging()
    logging_config.configure_logging()  # must not raise or double-add handlers
    assert logging_config._CONFIGURED is True


def test_configure_logging_skips_sentry_when_dsn_unset(monkeypatch):
    _reset()
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    logging_config.configure_logging()  # should not attempt to import/init sentry_sdk


def test_configure_logging_initializes_sentry_when_dsn_set(monkeypatch):
    _reset()
    monkeypatch.setenv("SENTRY_DSN", "https://fake@sentry.example/1")

    calls = []
    fake_sentry_sdk = type("FakeSentrySDK", (), {"init": staticmethod(lambda **kw: calls.append(kw))})
    monkeypatch.setitem(importlib.import_module("sys").modules, "sentry_sdk", fake_sentry_sdk)

    logging_config.configure_logging()

    assert len(calls) == 1
    assert calls[0]["dsn"] == "https://fake@sentry.example/1"

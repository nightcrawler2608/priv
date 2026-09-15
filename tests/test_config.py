"""Phase 6 tests: YAML config loading/validation. Pure, offline."""
import pytest
from pydantic import ValidationError

from scrapers.books_toscrape.config import DEFAULT_CONFIG_PATH, load_config


def test_loads_the_real_project_config():
    cfg = load_config(DEFAULT_CONFIG_PATH)
    assert cfg.name == "books_toscrape"
    assert cfg.schedule == "0 * * * *"
    assert cfg.max_pages >= 1
    assert 0 <= cfg.quality.max_reject_ratio <= 1


def test_rejects_schedule_with_wrong_field_count(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\nbase_url: https://x\nschedule: '0 * * *'\n")  # only 4 fields
    with pytest.raises(ValidationError):
        load_config(bad)


def test_defaults_apply_when_retry_and_quality_omitted(tmp_path):
    minimal = tmp_path / "minimal.yaml"
    minimal.write_text("name: x\nbase_url: https://x\nschedule: '0 * * * *'\n")
    cfg = load_config(minimal)
    assert cfg.max_pages == 50
    assert cfg.retry.max_retries == 3
    assert cfg.quality.max_reject_ratio == 0.5

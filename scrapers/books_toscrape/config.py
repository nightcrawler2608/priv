"""
Phase 6: config-over-code. One YAML file per site (schedule, page limit,
quality thresholds); loading it into a validated SiteConfig is the only
Python involved in adding a new site's automation settings.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "books_toscrape.yaml"


class RetryConfig(BaseModel):
    max_retries: int = Field(ge=0, default=3)


class QualityConfig(BaseModel):
    max_reject_ratio: float = Field(ge=0, le=1, default=0.5)
    max_row_drop_ratio: float = Field(ge=0, le=1, default=0.4)


class SiteConfig(BaseModel):
    name: str
    base_url: str
    schedule: str  # 5-field cron expression: "minute hour day month day_of_week"
    max_pages: int = Field(ge=1, default=50)
    retry: RetryConfig = RetryConfig()
    quality: QualityConfig = QualityConfig()

    @field_validator("schedule")
    @classmethod
    def schedule_is_five_field_cron(cls, v: str) -> str:
        fields = v.split()
        if len(fields) != 5:
            raise ValueError(
                f"schedule must be a 5-field cron expression "
                f"(minute hour day-of-month month day-of-week), got {v!r}"
            )
        return v


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> SiteConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return SiteConfig.model_validate(raw)

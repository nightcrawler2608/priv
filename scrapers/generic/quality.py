"""
Per-run data quality report for the generic engine -- same idea as
books_toscrape/quality.py's build_quality_report()/QualityAccumulator,
adapted to work on plain dicts with a site-defined field list instead of a
fixed Book/BookRecord shape. check_job_quality() (the pass/fail alert
threshold check) is already field-agnostic, so it's reused as-is from
books_toscrape.quality.
"""
from __future__ import annotations

from ..books_toscrape.quality import _is_blank
from .models import SiteDefinition


class GenericQualityAccumulator:
    """Streaming version of build_generic_quality_report(): running totals
    updated one page/batch at a time so the pagination-batched generic
    pipeline (api/generic_tasks.py) never needs every parsed item in memory
    at once -- same idea as books_toscrape.quality.QualityAccumulator."""

    def __init__(self, site: SiteDefinition) -> None:
        self.site = site
        self.total_parsed = 0
        self.rejected = 0
        self._null_counts = {field.name: 0 for field in site.fields}

    def add_batch(self, raw_batch: list[dict], clean_batch: list[dict]) -> None:
        self.total_parsed += len(raw_batch)
        self.rejected += len(raw_batch) - len(clean_batch)
        for field in self.site.fields:
            self._null_counts[field.name] += sum(1 for item in raw_batch if _is_blank(item.get(field.name)))

    def build_report(self, current_row_count: int, previous_row_count: int | None) -> dict:
        null_pct = {
            name: round(100 * count / self.total_parsed, 1) if self.total_parsed else 0.0
            for name, count in self._null_counts.items()
        }

        row_drop_pct = None
        if previous_row_count:
            row_drop_pct = round(100 * (previous_row_count - current_row_count) / previous_row_count, 1)

        return {
            "total_parsed": self.total_parsed,
            "rejected": self.rejected,
            "reject_ratio_pct": round(100 * self.rejected / self.total_parsed, 1) if self.total_parsed else 0.0,
            "current_row_count": current_row_count,
            "previous_row_count": previous_row_count,
            "row_drop_pct": row_drop_pct,
            "null_pct": null_pct,
        }


def build_generic_quality_report(
    raw_items: list[dict],
    clean_items: list[dict],
    site: SiteDefinition,
    current_row_count: int,
    previous_row_count: int | None,
) -> dict:
    """Convenience wrapper around GenericQualityAccumulator for callers
    that already have every item in memory at once (e.g. tests); the
    pipeline itself uses GenericQualityAccumulator directly."""
    accumulator = GenericQualityAccumulator(site)
    accumulator.add_batch(raw_items, clean_items)
    return accumulator.build_report(current_row_count, previous_row_count)

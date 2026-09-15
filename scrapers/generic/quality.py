"""
Per-run data quality report for the generic engine -- same idea as
books_toscrape/quality.py's build_quality_report(), adapted to work on
plain dicts with a site-defined field list instead of a fixed Book/BookRecord
shape. check_job_quality() (the pass/fail alert threshold check) is already
field-agnostic, so it's reused as-is from books_toscrape.quality.
"""
from __future__ import annotations

from ..books_toscrape.quality import _is_blank
from .models import SiteDefinition


def build_generic_quality_report(
    raw_items: list[dict],
    clean_items: list[dict],
    site: SiteDefinition,
    current_row_count: int,
    previous_row_count: int | None,
) -> dict:
    total_parsed = len(raw_items)
    rejected = total_parsed - len(clean_items)

    null_pct = {}
    for field in site.fields:
        blank = sum(1 for item in raw_items if _is_blank(item.get(field.name)))
        null_pct[field.name] = round(100 * blank / total_parsed, 1) if total_parsed else 0.0

    row_drop_pct = None
    if previous_row_count:
        row_drop_pct = round(100 * (previous_row_count - current_row_count) / previous_row_count, 1)

    return {
        "total_parsed": total_parsed,
        "rejected": rejected,
        "reject_ratio_pct": round(100 * rejected / total_parsed, 1) if total_parsed else 0.0,
        "current_row_count": current_row_count,
        "previous_row_count": previous_row_count,
        "row_drop_pct": row_drop_pct,
        "null_pct": null_pct,
    }

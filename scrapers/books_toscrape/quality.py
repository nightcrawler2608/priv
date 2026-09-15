"""
Phase 6+7: quality gates and per-run data quality reports. A scrape can
"succeed" (no exception) while still being wrong -- a broken CSS selector
doesn't crash, it just silently extracts nothing or garbage. These checks
catch that class of failure, which retries and error handling from
Phase 2/4 can never see.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Book, BookRecord

FIELDS = ("title", "price", "rating", "availability")


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def build_quality_report(
    raw_books: "list[Book]",
    clean_books: "list[BookRecord]",
    current_row_count: int,
    previous_row_count: int | None,
) -> dict:
    """Phase 7: a per-run data quality report -- null/blank percentage per
    field, reject rate, and row count vs. the previous run. Meant to be
    logged (structured, via loguru) and/or surfaced on a dashboard, not
    just acted on like the pass/fail warnings from check_job_quality()."""
    total_parsed = len(raw_books)
    rejected = total_parsed - len(clean_books)

    null_pct = {}
    for field in FIELDS:
        blank = sum(1 for b in raw_books if _is_blank(getattr(b, field)))
        null_pct[field] = round(100 * blank / total_parsed, 1) if total_parsed else 0.0

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


def check_job_quality(
    current_row_count: int,
    previous_row_count: int | None,
    rejected: int,
    total_parsed: int,
    max_reject_ratio: float = 0.5,
    max_row_drop_ratio: float = 0.4,
) -> list[str]:
    """Pure function: returns human-readable warnings, or [] if the run
    looks healthy. Never raises -- a quality problem is a signal to alert
    on, not a reason to fail the job."""
    warnings: list[str] = []

    if total_parsed > 0:
        reject_ratio = rejected / total_parsed
        if reject_ratio >= max_reject_ratio:
            warnings.append(
                f"{reject_ratio:.0%} of parsed rows were rejected by validation "
                f"({rejected}/{total_parsed}) -- a selector may have broken"
            )

    if previous_row_count is not None and previous_row_count > 0:
        drop_ratio = (previous_row_count - current_row_count) / previous_row_count
        if drop_ratio >= max_row_drop_ratio:
            warnings.append(
                f"row count dropped {drop_ratio:.0%} vs. the previous run "
                f"({previous_row_count} -> {current_row_count}) -- layout change or block?"
            )

    return warnings

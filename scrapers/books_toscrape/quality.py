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


class QualityAccumulator:
    """Streaming version of build_quality_report(): running totals updated
    one page/batch at a time instead of requiring every parsed row to sit
    in memory simultaneously. This is what makes the pagination-batched
    pipeline (api/tasks.py) memory-bounded regardless of how many pages a
    site has -- each page's rows get folded into these counters and then
    discarded, not accumulated into one ever-growing list."""

    def __init__(self) -> None:
        self.total_parsed = 0
        self.rejected = 0
        self._null_counts = {field: 0 for field in FIELDS}

    def add_batch(self, raw_batch: "list[Book]", clean_batch: "list[BookRecord]") -> None:
        self.total_parsed += len(raw_batch)
        self.rejected += len(raw_batch) - len(clean_batch)
        for field in FIELDS:
            self._null_counts[field] += sum(1 for b in raw_batch if _is_blank(getattr(b, field)))

    def build_report(self, current_row_count: int, previous_row_count: int | None) -> dict:
        null_pct = {
            field: round(100 * count / self.total_parsed, 1) if self.total_parsed else 0.0
            for field, count in self._null_counts.items()
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


def build_quality_report(
    raw_books: "list[Book]",
    clean_books: "list[BookRecord]",
    current_row_count: int,
    previous_row_count: int | None,
) -> dict:
    """Phase 7: a per-run data quality report -- null/blank percentage per
    field, reject rate, and row count vs. the previous run. Meant to be
    logged (structured, via loguru) and/or surfaced on a dashboard, not
    just acted on like the pass/fail warnings from check_job_quality().

    Convenience wrapper around QualityAccumulator for callers that already
    have every row in memory at once (e.g. tests); the pipeline itself
    uses QualityAccumulator directly so it never needs to."""
    accumulator = QualityAccumulator()
    accumulator.add_batch(raw_books, clean_books)
    return accumulator.build_report(current_row_count, previous_row_count)


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

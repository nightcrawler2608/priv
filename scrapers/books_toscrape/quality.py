"""
Phase 6: quality gates. A scrape can "succeed" (no exception) while still
being wrong -- a broken CSS selector doesn't crash, it just silently
extracts nothing or garbage. These checks catch that class of failure,
which retries and error handling from Phase 2/4 can never see.
"""
from __future__ import annotations


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

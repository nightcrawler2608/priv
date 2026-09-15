"""Phase 6 tests: data-quality gates. Pure, offline."""
from scrapers.books_toscrape.quality import check_job_quality


def test_no_warnings_on_a_healthy_run():
    warnings = check_job_quality(
        current_row_count=50, previous_row_count=48, rejected=0, total_parsed=50,
    )
    assert warnings == []


def test_warns_when_reject_ratio_is_high_selector_broke():
    warnings = check_job_quality(
        current_row_count=2, previous_row_count=50, rejected=48, total_parsed=50,
        max_reject_ratio=0.5,
    )
    assert any("rejected" in w for w in warnings)


def test_no_reject_warning_below_threshold():
    warnings = check_job_quality(
        current_row_count=45, previous_row_count=50, rejected=5, total_parsed=50,
        max_reject_ratio=0.5,
    )
    assert not any("rejected" in w for w in warnings)


def test_warns_on_large_row_count_drop():
    warnings = check_job_quality(
        current_row_count=10, previous_row_count=50, rejected=0, total_parsed=10,
        max_row_drop_ratio=0.4,
    )
    assert any("dropped" in w for w in warnings)


def test_no_drop_warning_with_no_previous_run():
    warnings = check_job_quality(
        current_row_count=10, previous_row_count=None, rejected=0, total_parsed=10,
    )
    assert warnings == []


def test_can_report_both_warnings_at_once():
    warnings = check_job_quality(
        current_row_count=1, previous_row_count=50, rejected=48, total_parsed=50,
        max_reject_ratio=0.5, max_row_drop_ratio=0.4,
    )
    assert len(warnings) == 2

from datetime import UTC, datetime

import pytest

from bulk_mailer.mailer import AsyncMailer
from bulk_mailer.models import (
    ReportSettings,
    Settings,
    TaskExecutionResult,
    TaskExecutionStatus,
)
from bulk_mailer.reporter import ReportGenerator, aggregate_summary_report


def test_aggregate_summary_report() -> None:
    t1 = datetime(2026, 10, 17, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 17, 10, 1, tzinfo=UTC)

    results = [
        TaskExecutionResult(task_id="T1", status=TaskExecutionStatus.SUCCESS, sent_count=2),
        TaskExecutionResult(
            task_id="T2", status=TaskExecutionStatus.FAILED, failed_recipients=["a@b.com"]
        ),
        TaskExecutionResult(task_id="T3", status=TaskExecutionStatus.SKIPPED_SCHEDULE),
    ]

    report = aggregate_summary_report(results, t1, t2)
    assert report.total_tasks == 3
    assert report.successful_tasks == 1
    assert report.failed_tasks == 1
    assert report.skipped_tasks == 1
    assert report.total_duration_ms == 60000.0


@pytest.mark.asyncio
async def test_send_report_dry_run() -> None:
    report_settings = ReportSettings(
        recipient="admin@example.com",
        sender="mailer@example.com",
        subject_prefix="[TEST]",
        include_full_error_trace=True,
    )

    t1 = datetime(2026, 10, 17, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 17, 10, 1, tzinfo=UTC)
    results = [
        TaskExecutionResult(task_id="T1", status=TaskExecutionStatus.SUCCESS, sent_count=1),
    ]
    report = aggregate_summary_report(results, t1, t2)

    gen = ReportGenerator(template_dir="templates")
    mailer = AsyncMailer(Settings(), dry_run=True)

    sent = await gen.send_report(report, report_settings, mailer)
    assert sent is True


def test_render_report_success() -> None:
    report_settings = ReportSettings(
        recipient="admin@example.com",
        sender="mailer@example.com",
        subject_prefix="[TEST]",
        include_full_error_trace=True,
    )
    t1 = datetime(2026, 10, 17, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 17, 10, 1, tzinfo=UTC)
    results = [
        TaskExecutionResult(task_id="T1", status=TaskExecutionStatus.SUCCESS, sent_count=1),
    ]
    report = aggregate_summary_report(results, t1, t2)

    gen = ReportGenerator(template_dir="templates")
    html_content, txt_content = gen.render_report(report, report_settings)

    assert "BulkMailer Task Completion Status Report" in html_content
    assert "BulkMailer Task Completion Status Report" in txt_content


def test_render_report_fallback() -> None:
    report_settings = ReportSettings(
        recipient="admin@example.com",
        sender="mailer@example.com",
        subject_prefix="[TEST]",
        include_full_error_trace=True,
    )
    t1 = datetime(2026, 10, 17, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 17, 10, 1, tzinfo=UTC)
    results = [
        TaskExecutionResult(task_id="T1", status=TaskExecutionStatus.SUCCESS, sent_count=1),
    ]
    report = aggregate_summary_report(results, t1, t2)

    # Non-existent template directory forces Jinja environment lookup to fail
    gen = ReportGenerator(template_dir="non_existent_dir_12345")
    html_content, txt_content = gen.render_report(report, report_settings)

    assert html_content == "<h2>BulkMailer Report</h2><p>Tasks total: 1, Success: 1, Failed: 0</p>"
    assert txt_content == "BulkMailer Report\nTasks total: 1, Success: 1, Failed: 0"

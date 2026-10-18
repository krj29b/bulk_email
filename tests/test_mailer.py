from unittest.mock import AsyncMock

import aiosmtplib
import pytest

from bulk_mailer.mailer import AsyncMailer, TemplateRenderer
from bulk_mailer.models import BodyTemplate, MailTask, Recipients, Settings, TaskExecutionStatus


def test_template_renderer(tmp_path):
    tpl_file = tmp_path / "test.j2"
    tpl_file.write_text("Hello {{ name }}!")

    renderer = TemplateRenderer(template_dir=tmp_path)
    res = renderer.render("test.j2", {"name": "World"})
    assert res == "Hello World!"


@pytest.mark.asyncio
async def test_async_mailer_dry_run(tmp_path):
    tpl_file = tmp_path / "test.j2"
    tpl_file.write_text("Hello {{ name }}!")

    settings = Settings()
    renderer = TemplateRenderer(template_dir=tmp_path)
    mailer = AsyncMailer(settings, renderer=renderer, dry_run=True)

    task = MailTask(
        id="TASK-01",
        max_retries=2,
        schedule_ref="SCHED-1",
        sender="sender@example.com",
        recipients=Recipients(to=["to@example.com"]),
        subject="Test Subject",
        body_template=BodyTemplate(template_path="test.j2"),
    )

    result = await mailer.dispatch_task(task)
    assert result.status == TaskExecutionStatus.SUCCESS
    assert result.sent_count == 1
    assert result.attempt_count == 1
    assert result.error_details is None


@pytest.mark.asyncio
async def test_async_mailer_retry_and_failure(tmp_path):
    tpl_file = tmp_path / "test.j2"
    tpl_file.write_text("Hello {{ name }}!")

    settings = Settings()
    renderer = TemplateRenderer(template_dir=tmp_path)

    mock_smtp = AsyncMock()
    mock_smtp.is_connected = True
    mock_smtp.connect = AsyncMock()
    smtp_exc = aiosmtplib.SMTPResponseException(451, "Temporary failure")
    mock_smtp.send_message = AsyncMock(side_effect=smtp_exc)

    mailer = AsyncMailer(settings, renderer=renderer, dry_run=False, smtp_client=mock_smtp)

    task = MailTask(
        id="TASK-02",
        max_retries=2,  # total 3 attempts
        schedule_ref="SCHED-1",
        sender="sender@example.com",
        recipients=Recipients(to=["to@example.com"]),
        subject="Test Subject",
        body_template=BodyTemplate(template_path="test.j2"),
    )

    result = await mailer.dispatch_task(task)
    assert result.status == TaskExecutionStatus.FAILED
    assert result.sent_count == 0
    assert result.attempt_count == 3
    assert "SMTP error 451" in (result.error_details or "")


@pytest.mark.asyncio
async def test_dispatch_task_failure_with_rate_limiter_and_network_exception(tmp_path, monkeypatch):
    tpl_file = tmp_path / "test.j2"
    tpl_file.write_text("Hello {{ name }}!")

    settings = Settings()
    renderer = TemplateRenderer(template_dir=tmp_path)

    mock_smtp = AsyncMock()
    mock_smtp.is_connected = False
    mock_smtp.connect = AsyncMock(side_effect=ConnectionRefusedError("Connection refused by host"))

    mock_rate_limiter = AsyncMock()
    mock_sleep = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    mailer = AsyncMailer(settings, renderer=renderer, dry_run=False, smtp_client=mock_smtp)

    task = MailTask(
        id="TASK-NET-ERR",
        max_retries=2,  # 3 attempts total
        schedule_ref="SCHED-1",
        sender="sender@example.com",
        recipients=Recipients(to=["to@example.com", "cc@example.com"]),
        subject="Test Network Error",
        body_template=BodyTemplate(template_path="test.j2"),
    )

    result = await mailer.dispatch_task(task, rate_limiter=mock_rate_limiter)

    assert result.status == TaskExecutionStatus.FAILED
    assert result.sent_count == 0
    assert result.failed_recipients == ["to@example.com", "cc@example.com"]
    assert result.attempt_count == 3
    assert result.error_details is not None
    assert "Network/Connection error: Connection refused by host" in result.error_details

    # Verify rate limiter was acquired on each attempt
    assert mock_rate_limiter.acquire.call_count == 3

    # Verify exponential backoff sleep was called for attempts 1 and 2 (0.5s and 1.0s)
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(0.5)
    mock_sleep.assert_any_call(1.0)


@pytest.mark.asyncio
async def test_dispatch_task_retry_success_with_rate_limiter(tmp_path, monkeypatch):
    tpl_file = tmp_path / "test.j2"
    tpl_file.write_text("Hello {{ name }}!")

    settings = Settings()
    renderer = TemplateRenderer(template_dir=tmp_path)

    mock_smtp = AsyncMock()
    mock_smtp.is_connected = True
    mock_smtp.send_message = AsyncMock(
        side_effect=[
            aiosmtplib.SMTPException("Temporary network disconnect"),
            None,  # Success on second attempt
        ]
    )

    mock_rate_limiter = AsyncMock()
    mock_sleep = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    mailer = AsyncMailer(settings, renderer=renderer, dry_run=False, smtp_client=mock_smtp)

    task = MailTask(
        id="TASK-RETRY-SUCCESS",
        max_retries=2,
        schedule_ref="SCHED-1",
        sender="sender@example.com",
        recipients=Recipients(to=["to@example.com"]),
        subject="Test Retry Success",
        body_template=BodyTemplate(template_path="test.j2"),
    )

    result = await mailer.dispatch_task(task, rate_limiter=mock_rate_limiter)

    assert result.status == TaskExecutionStatus.SUCCESS
    assert result.sent_count == 1
    assert result.failed_recipients == []
    assert result.attempt_count == 2
    assert result.error_details is None

    assert mock_rate_limiter.acquire.call_count == 2
    assert mock_sleep.call_count == 1
    mock_sleep.assert_called_once_with(0.5)

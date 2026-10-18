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


def test_async_mailer_get_smtp_connection_default():
    settings = Settings(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user@example.com",
        smtp_password="password123",
        smtp_use_tls=False,
        smtp_start_tls=True,
        smtp_timeout=15.0,
    )
    mailer = AsyncMailer(settings)

    connection = mailer._get_smtp_connection()

    assert isinstance(connection, aiosmtplib.SMTP)
    assert connection.hostname == "smtp.example.com"
    assert connection.port == 587
    assert connection.use_tls is False
    assert connection.timeout == 15.0

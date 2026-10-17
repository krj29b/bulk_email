import asyncio
import contextlib
import logging
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from bulk_mailer.models import MailTask, Settings, TaskExecutionResult, TaskExecutionStatus
from bulk_mailer.scheduler import TokenBucketRateLimiter

logger = logging.getLogger(__name__)


class TemplateRenderer:
    def __init__(self, template_dir: str | Path = ".") -> None:
        self.template_dir = Path(template_dir)
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def render(self, template_path: str, context: dict[str, Any]) -> str:
        # Check if template_path is relative or absolute
        tpl_path = Path(template_path)
        if tpl_path.is_absolute():
            # Extract parent and filename
            env = Environment(
                loader=FileSystemLoader(str(tpl_path.parent)),
                autoescape=select_autoescape(["html", "xml"]),
            )
            template = env.get_template(tpl_path.name)
        else:
            template = self.env.get_template(template_path)

        return template.render(**context)


def build_email_message(
    task: MailTask,
    body_content: str,
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = task.subject
    msg["From"] = task.sender
    msg["To"] = ", ".join(task.recipients.to)
    if task.recipients.cc:
        msg["Cc"] = ", ".join(task.recipients.cc)

    body_format = task.body_template.format.lower()
    if body_format == "html":
        part = MIMEText(body_content, "html", "utf-8")
    else:
        part = MIMEText(body_content, "plain", "utf-8")

    msg.attach(part)
    return msg


class AsyncMailer:
    def __init__(
        self,
        settings: Settings,
        renderer: TemplateRenderer | None = None,
        dry_run: bool = False,
        smtp_client: Any | None = None,
    ) -> None:
        self.settings = settings
        self.renderer = renderer or TemplateRenderer()
        self.dry_run = dry_run
        self._custom_smtp_client = smtp_client

    def _get_smtp_connection(self) -> Any:
        if self._custom_smtp_client is not None:
            return self._custom_smtp_client

        return aiosmtplib.SMTP(
            hostname=self.settings.smtp_host,
            port=self.settings.smtp_port,
            username=self.settings.smtp_user,
            password=self.settings.smtp_password,
            use_tls=self.settings.smtp_use_tls,
            start_tls=self.settings.smtp_start_tls,
            timeout=self.settings.smtp_timeout,
        )

    async def send_single_message(
        self,
        msg: MIMEMultipart,
        sender: str,
        recipients: list[str],
    ) -> tuple[bool, str | None]:
        if self.dry_run:
            logger.info(
                f"[DRY-RUN] Would send email from {sender} to {recipients} subject={msg['Subject']}"
            )
            return True, None

        client = self._get_smtp_connection()
        try:
            # Connect and send
            if not getattr(client, "is_connected", False):
                await client.connect()
                if self.settings.smtp_user and self.settings.smtp_password:
                    await client.login(self.settings.smtp_user, self.settings.smtp_password)

            await client.send_message(msg, sender=sender, recipients=recipients)
            return True, None
        except aiosmtplib.SMTPResponseException as exc:
            return False, f"SMTP error {exc.code}: {exc.message}"
        except aiosmtplib.SMTPException as exc:
            return False, f"SMTP Exception: {exc}"
        except Exception as exc:
            return False, f"Network/Connection error: {exc}"
        finally:
            if self._custom_smtp_client is None and getattr(client, "is_connected", False):
                with contextlib.suppress(Exception):
                    await client.quit()

    async def dispatch_task(
        self,
        task: MailTask,
        rate_limiter: TokenBucketRateLimiter | None = None,
    ) -> TaskExecutionResult:
        start_time = time.monotonic()
        all_recipients = task.recipients.all_recipients

        if not all_recipients:
            return TaskExecutionResult(
                task_id=task.id,
                status=TaskExecutionStatus.SUCCESS,
                sent_count=0,
                duration_ms=0.0,
                error_details="No recipients defined",
            )

        # Render template
        try:
            context = task.get_context_dict()
            body_content = self.renderer.render(task.body_template.template_path, context)
            msg = build_email_message(task, body_content)
        except Exception as exc:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            logger.error(f"Failed to render template for task {task.id}: {exc}")
            return TaskExecutionResult(
                task_id=task.id,
                status=TaskExecutionStatus.FAILED,
                sent_count=0,
                failed_recipients=all_recipients,
                duration_ms=duration_ms,
                error_details=f"Template rendering error: {exc}",
            )

        attempts = 0
        max_attempts = max(1, task.max_retries + 1)
        last_error: str | None = None
        sent_count = 0
        failed_recipients: list[str] = []

        while attempts < max_attempts:
            attempts += 1
            if rate_limiter:
                await rate_limiter.acquire()

            success, error_msg = await self.send_single_message(
                msg=msg,
                sender=task.sender,
                recipients=all_recipients,
            )

            if success:
                sent_count = len(all_recipients)
                last_error = None
                break
            else:
                last_error = error_msg
                logger.warning(
                    f"Task {task.id} attempt {attempts}/{max_attempts} failed: {error_msg}"
                )
                if attempts < max_attempts:
                    # Exponential backoff: 0.5s, 1s, 2s...
                    backoff = 0.5 * (2 ** (attempts - 1))
                    await asyncio.sleep(backoff)

        duration_ms = (time.monotonic() - start_time) * 1000.0

        if last_error is None:
            status = TaskExecutionStatus.SUCCESS
        elif sent_count > 0:
            status = TaskExecutionStatus.PARTIAL
        else:
            status = TaskExecutionStatus.FAILED
            failed_recipients = all_recipients

        return TaskExecutionResult(
            task_id=task.id,
            status=status,
            sent_count=sent_count,
            failed_recipients=failed_recipients,
            duration_ms=duration_ms,
            error_details=last_error,
            attempt_count=attempts,
        )

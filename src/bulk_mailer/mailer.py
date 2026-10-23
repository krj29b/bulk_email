import asyncio
import contextlib
import logging
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
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
        tpl_path = Path(template_path)
        base_dir = self.template_dir.resolve()

        if tpl_path.is_absolute():
            resolved_path = tpl_path.resolve()
        else:
            resolved_path = (self.template_dir / tpl_path).resolve()

        try:
            rel_path = resolved_path.relative_to(base_dir)
        except ValueError as exc:
            msg = f"Access denied for template path outside base directory: {template_path}"
            raise ValueError(msg) from exc

        template = self.env.get_template(rel_path.as_posix())
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
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()

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

    @staticmethod
    def _is_permanent_smtp_error(errors: dict[str, Any]) -> bool:
        smtp_code = errors.get("smtp_code")
        if smtp_code is None:
            return False
        try:
            return 500 <= int(smtp_code) < 600
        except (ValueError, TypeError):
            return False

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
    ) -> tuple[bool, str | None, dict[str, Any]]:
        if self.dry_run:
            logger.info(
                f"[DRY-RUN] Would send email from {sender} to {recipients} subject={msg['Subject']}"
            )
            return True, None, {}

        client = self._get_smtp_connection()
        try:
            # Connect and send
            if not getattr(client, "is_connected", False):
                await client.connect()
                if self.settings.smtp_user and self.settings.smtp_password:
                    await client.login(self.settings.smtp_user, self.settings.smtp_password)

            res = await client.send_message(msg, sender=sender, recipients=recipients)
            errors: dict[str, Any] = {}
            if isinstance(res, tuple) and len(res) == 2 and isinstance(res[0], dict):
                errors = res[0]

            if errors:
                return True, f"Partial delivery errors: {list(errors.keys())}", errors
            return True, None, {}
        except aiosmtplib.SMTPResponseException as exc:
            return False, f"SMTP error {exc.code}: {exc.message}", {"smtp_code": exc.code}
        except aiosmtplib.SMTPException as exc:
            return False, f"SMTP Exception: {exc}", {}
        except Exception as exc:
            return False, f"Network/Connection error: {exc}", {}
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
        pending_recipients = list(all_recipients)
        successful_recipients: list[str] = []

        while attempts < max_attempts and pending_recipients:
            attempts += 1
            if rate_limiter:
                await rate_limiter.acquire()

            success, error_msg, errors = await self.send_single_message(
                msg=msg,
                sender=task.sender,
                recipients=pending_recipients,
            )

            if success:
                if errors:
                    failed_in_attempt = list(errors.keys())
                    succeeded_in_attempt = [
                        r for r in pending_recipients if r not in failed_in_attempt
                    ]
                    successful_recipients.extend(succeeded_in_attempt)
                    pending_recipients = failed_in_attempt
                    last_error = error_msg
                else:
                    successful_recipients.extend(pending_recipients)
                    pending_recipients = []
                    last_error = None
                    break
            else:
                last_error = error_msg
                logger.warning(
                    f"Task {task.id} attempt {attempts}/{max_attempts} failed: {error_msg}"
                )
                if self._is_permanent_smtp_error(errors):
                    break

            if attempts < max_attempts and pending_recipients:
                # Exponential backoff: 0.5s, 1s, 2s...
                backoff = 0.5 * (2 ** (attempts - 1))
                await asyncio.sleep(backoff)

        duration_ms = (time.monotonic() - start_time) * 1000.0

        sent_count = len(successful_recipients)
        failed_recipients = pending_recipients

        if len(successful_recipients) == len(all_recipients):
            status = TaskExecutionStatus.SUCCESS
            last_error = None
            failed_recipients = []
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

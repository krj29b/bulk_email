from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_xml import BaseXmlModel, attr, element, wrapped


class TaskExecutionStatus(StrEnum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED_SCHEDULE = "SKIPPED_SCHEDULE"


class ReportSettings(BaseXmlModel, tag="ReportSettings"):
    recipient: str = element(tag="Recipient")
    sender: str | None = element(tag="Sender", default=None)
    subject_prefix: str = element(tag="SubjectPrefix", default="[BulkMailer Report]")
    include_full_error_trace: bool = element(tag="IncludeFullErrorTrace", default=True)


class Recipients(BaseXmlModel, tag="Recipients"):
    to: list[str] = element(tag="To", default_factory=list)
    cc: list[str] = element(tag="Cc", default_factory=list)
    bcc: list[str] = element(tag="Bcc", default_factory=list)

    @property
    def all_recipients(self) -> list[str]:
        return self.to + self.cc + self.bcc


class BodyTemplate(BaseXmlModel, tag="BodyTemplate"):
    format: str = attr(default="html")
    template_path: str


class ContextVar(BaseXmlModel, tag="Var"):
    name: str = attr()
    value: str


class MailTask(BaseXmlModel, tag="MailTask"):
    id: str = attr()
    max_retries: int = attr(default=3)
    priority: str = attr(default="normal")
    schedule_ref: str = attr()
    sender: str = element(tag="Sender")
    recipients: Recipients = element(tag="Recipients")
    subject: str = element(tag="Subject")
    body_template: BodyTemplate = element(tag="BodyTemplate")
    context_variables: list[ContextVar] = wrapped(
        "ContextVariables", element(tag="Var", default_factory=list)
    )

    def get_context_dict(self) -> dict[str, str]:
        return {var.name: var.value for var in self.context_variables}


class MailConfiguration(BaseXmlModel, tag="MailConfiguration"):
    report_settings: ReportSettings = element(tag="ReportSettings")
    tasks: list[MailTask] = wrapped(
        "Tasks", element(tag="MailTask", default_factory=list)
    )


class HourWindow(BaseXmlModel, tag="HourWindow"):
    start: str = attr()
    end: str = attr()
    max_concurrency: int = attr(default=1)
    rate_limit_per_min: int = attr(default=60)


class Schedule(BaseXmlModel, tag="Schedule"):
    id: str = attr()
    description: str | None = attr(default=None)
    allowed_hours: list[HourWindow] = wrapped(
        "AllowedHours", element(tag="HourWindow", default_factory=list)
    )


class WorkSchedules(BaseXmlModel, tag="WorkSchedules"):
    timezone: str = attr(default="UTC")
    schedules: list[Schedule] = element(tag="Schedule", default_factory=list)


class TaskExecutionResult(BaseModel):
    task_id: str
    status: TaskExecutionStatus
    sent_count: int = 0
    failed_recipients: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0
    error_details: str | None = None
    attempt_count: int = 1


class BatchSummaryReport(BaseModel):
    total_tasks: int
    successful_tasks: int
    partial_tasks: int
    failed_tasks: int
    skipped_tasks: int
    total_duration_ms: float
    start_time: datetime
    end_time: datetime
    results: list[TaskExecutionResult]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = False
    smtp_start_tls: bool = False
    smtp_timeout: float = 30.0

    @classmethod
    def load(cls) -> Self:
        return cls()

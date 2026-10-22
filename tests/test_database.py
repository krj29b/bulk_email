from bulk_mailer.database import get_connection, init_db
from bulk_mailer.models import (
    BodyTemplate,
    ContextVar,
    HourWindow,
    MailConfiguration,
    MailTask,
    Recipients,
    ReportSettings,
    Schedule,
    TaskExecutionResult,
    TaskExecutionStatus,
    WorkSchedules,
)
from bulk_mailer.repository import DatabaseRepository


def test_database_init() -> None:
    conn = get_connection(":memory:")
    init_db(conn)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    assert "schedules" in tables
    assert "tasks" in tables
    assert "execution_logs" in tables


def test_repository_save_and_get_schedules() -> None:
    conn = get_connection(":memory:")
    init_db(conn)
    repo = DatabaseRepository(conn)

    schedules = WorkSchedules(
        timezone="Europe/Warsaw",
        schedules=[
            Schedule(
                id="SCHED-01",
                description="Test schedule",
                allowed_hours=[
                    HourWindow(start="08:00", end="12:00", max_concurrency=2, rate_limit_per_min=30)
                ],
            )
        ],
    )

    repo.save_work_schedules(schedules)
    loaded = repo.get_work_schedules()

    assert loaded.timezone == "Europe/Warsaw"
    assert len(loaded.schedules) == 1
    assert loaded.schedules[0].id == "SCHED-01"
    assert loaded.schedules[0].description == "Test schedule"
    assert len(loaded.schedules[0].allowed_hours) == 1
    assert loaded.schedules[0].allowed_hours[0].start == "08:00"


def test_repository_save_and_get_mail_config() -> None:
    conn = get_connection(":memory:")
    init_db(conn)
    repo = DatabaseRepository(conn)

    schedules = WorkSchedules(
        schedules=[Schedule(id="SCHED-01", allowed_hours=[HourWindow(start="00:00", end="23:59")])]
    )
    repo.save_work_schedules(schedules)

    mail_config = MailConfiguration(
        report_settings=ReportSettings(recipient="admin@example.com"),
        tasks=[
            MailTask(
                id="TASK-1",
                schedule_ref="SCHED-01",
                sender="sender@example.com",
                recipients=Recipients(to=["user1@example.com"], cc=["user2@example.com"]),
                subject="Test Subject",
                body_template=BodyTemplate(template_path="tpl.j2"),
                context_variables=[ContextVar(name="k1", value="v1")],
            )
        ],
    )

    repo.save_mail_configuration(mail_config)
    loaded = repo.get_mail_configuration()

    assert loaded.report_settings.recipient == "admin@example.com"
    assert len(loaded.tasks) == 1
    assert loaded.tasks[0].id == "TASK-1"
    assert loaded.tasks[0].recipients.to == ["user1@example.com"]
    assert loaded.tasks[0].recipients.cc == ["user2@example.com"]
    assert loaded.tasks[0].context_variables[0].name == "k1"


def test_repository_log_execution() -> None:
    conn = get_connection(":memory:")
    init_db(conn)
    repo = DatabaseRepository(conn)

    schedules = WorkSchedules(
        schedules=[Schedule(id="SCHED-01", allowed_hours=[HourWindow(start="00:00", end="23:59")])]
    )
    repo.save_work_schedules(schedules)

    mail_config = MailConfiguration(
        report_settings=ReportSettings(recipient="admin@example.com"),
        tasks=[
            MailTask(
                id="TASK-1",
                schedule_ref="SCHED-01",
                sender="sender@example.com",
                recipients=Recipients(to=["user1@example.com"]),
                subject="Test Subject",
                body_template=BodyTemplate(template_path="tpl.j2"),
            )
        ],
    )
    repo.save_mail_configuration(mail_config)

    res = TaskExecutionResult(
        task_id="TASK-1",
        status=TaskExecutionStatus.SUCCESS,
        sent_count=1,
        duration_ms=12.5,
    )
    repo.log_task_execution(res, batch_id="BATCH-001")

    history = repo.get_execution_results_for_batch("BATCH-001")
    assert len(history) == 1
    assert history[0].task_id == "TASK-1"
    assert history[0].status == TaskExecutionStatus.SUCCESS


def test_repository_get_report_settings_default_and_saved() -> None:
    conn = get_connection(":memory:")
    init_db(conn)
    repo = DatabaseRepository(conn)

    # 1. Test default report settings when no row exists in report_settings table
    defaults = repo.get_report_settings()
    assert defaults.recipient == "admin@example.com"
    assert defaults.sender is None
    assert defaults.subject_prefix == "[BulkMailer Report]"
    assert defaults.include_full_error_trace is True

    # 2. Test save_report_settings and get_report_settings with custom values
    custom = ReportSettings(
        recipient="reports@company.com",
        sender="noreply@company.com",
        subject_prefix="[Custom]",
        include_full_error_trace=False,
    )
    repo.save_report_settings(custom)

    loaded = repo.get_report_settings()
    assert loaded.recipient == "reports@company.com"
    assert loaded.sender == "noreply@company.com"
    assert loaded.subject_prefix == "[Custom]"
    assert loaded.include_full_error_trace is False

    # 3. Test updating existing settings (upsert behavior)
    updated = ReportSettings(
        recipient="new_admin@company.com",
        sender="notifications@company.com",
        subject_prefix="[Updated Report]",
        include_full_error_trace=True,
    )
    repo.save_report_settings(updated)

    loaded_updated = repo.get_report_settings()
    assert loaded_updated.recipient == "new_admin@company.com"
    assert loaded_updated.sender == "notifications@company.com"
    assert loaded_updated.subject_prefix == "[Updated Report]"
    assert loaded_updated.include_full_error_trace is True

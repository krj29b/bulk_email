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

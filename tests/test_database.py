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
                recipients=Recipients(
                    to=["to1@example.com", "to2@example.com"],
                    cc=["cc1@example.com"],
                    bcc=["bcc1@example.com"],
                ),
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
    assert loaded.tasks[0].recipients.to == ["to1@example.com", "to2@example.com"]
    assert loaded.tasks[0].recipients.cc == ["cc1@example.com"]
    assert loaded.tasks[0].recipients.bcc == ["bcc1@example.com"]
    assert loaded.tasks[0].context_variables[0].name == "k1"

    rows = conn.execute(
        "SELECT recipient_type, email, seq FROM task_recipients "
        "WHERE task_id = 'TASK-1' ORDER BY seq"
    ).fetchall()
    assert [dict(r) for r in rows] == [
        {"recipient_type": "to", "email": "to1@example.com", "seq": 0},
        {"recipient_type": "to", "email": "to2@example.com", "seq": 1},
        {"recipient_type": "cc", "email": "cc1@example.com", "seq": 2},
        {"recipient_type": "bcc", "email": "bcc1@example.com", "seq": 3},
    ]


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


def test_repository_get_mail_tasks_empty() -> None:
    conn = get_connection(":memory:")
    init_db(conn)
    repo = DatabaseRepository(conn)

    tasks = repo.get_mail_tasks()
    assert tasks == []


def test_repository_get_mail_tasks_detailed() -> None:
    conn = get_connection(":memory:")
    init_db(conn)
    repo = DatabaseRepository(conn)

    schedules = WorkSchedules(
        schedules=[Schedule(id="SCHED-01", allowed_hours=[HourWindow(start="00:00", end="23:59")])]
    )
    repo.save_work_schedules(schedules)

    task2 = MailTask(
        id="TASK-2",
        max_retries=5,
        priority="high",
        schedule_ref="SCHED-01",
        sender="sender2@example.com",
        recipients=Recipients(
            to=["to2@example.com"],
            cc=["cc2@example.com"],
            bcc=["bcc2@example.com"],
        ),
        subject="Subject 2",
        body_template=BodyTemplate(format="html", template_path="tpl2.html"),
        context_variables=[
            ContextVar(name="var1", value="val1"),
            ContextVar(name="var2", value="val2"),
        ],
    )

    task1 = MailTask(
        id="TASK-1",
        max_retries=1,
        priority="low",
        schedule_ref="SCHED-01",
        sender="sender1@example.com",
        recipients=Recipients(
            to=["to1_a@example.com", "to1_b@example.com"],
            cc=[],
            bcc=["bcc1@example.com"],
        ),
        subject="Subject 1",
        body_template=BodyTemplate(format="text", template_path="tpl1.txt"),
        context_variables=[],
    )

    # Save configuration containing task2 and task1
    mail_config = MailConfiguration(
        report_settings=ReportSettings(recipient="admin@example.com"),
        tasks=[task2, task1],
    )
    repo.save_mail_configuration(mail_config)

    tasks = repo.get_mail_tasks()
    assert len(tasks) == 2

    # Tasks should be ordered by ID ('TASK-1' before 'TASK-2')
    t1 = tasks[0]
    assert t1.id == "TASK-1"
    assert t1.max_retries == 1
    assert t1.priority == "low"
    assert t1.schedule_ref == "SCHED-01"
    assert t1.sender == "sender1@example.com"
    assert t1.subject == "Subject 1"
    assert t1.body_template.format == "text"
    assert t1.body_template.template_path == "tpl1.txt"
    assert t1.recipients.to == ["to1_a@example.com", "to1_b@example.com"]
    assert t1.recipients.cc == []
    assert t1.recipients.bcc == ["bcc1@example.com"]
    assert t1.context_variables == []

    t2 = tasks[1]
    assert t2.id == "TASK-2"
    assert t2.max_retries == 5
    assert t2.priority == "high"
    assert t2.schedule_ref == "SCHED-01"
    assert t2.sender == "sender2@example.com"
    assert t2.subject == "Subject 2"
    assert t2.body_template.format == "html"
    assert t2.body_template.template_path == "tpl2.html"
    assert t2.recipients.to == ["to2@example.com"]
    assert t2.recipients.cc == ["cc2@example.com"]
    assert t2.recipients.bcc == ["bcc2@example.com"]
    assert len(t2.context_variables) == 2
    assert t2.context_variables[0].name == "var1"
    assert t2.context_variables[0].value == "val1"
    assert t2.context_variables[1].name == "var2"
    assert t2.context_variables[1].value == "val2"

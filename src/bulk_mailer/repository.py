import json
import sqlite3
from collections import defaultdict
from typing import Literal

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


class DatabaseRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # --- WorkSchedules Operations ---

    def get_work_schedules(self) -> WorkSchedules:
        meta_row = self.conn.execute(
            "SELECT timezone FROM work_schedules_meta WHERE id = 1"
        ).fetchone()
        timezone = meta_row["timezone"] if meta_row else "UTC"

        sched_rows = self.conn.execute(
            "SELECT id, description FROM schedules ORDER BY id"
        ).fetchall()

        hw_rows = self.conn.execute(
            """
            SELECT schedule_id, start_time, end_time, max_concurrency, rate_limit_per_min
            FROM hour_windows
            ORDER BY schedule_id, seq, id
            """
        ).fetchall()

        hw_by_schedule: dict[str, list[HourWindow]] = defaultdict(list)
        for hw in hw_rows:
            hw_by_schedule[hw["schedule_id"]].append(
                HourWindow(
                    start=hw["start_time"],
                    end=hw["end_time"],
                    max_concurrency=hw["max_concurrency"],
                    rate_limit_per_min=hw["rate_limit_per_min"],
                )
            )

        schedules: list[Schedule] = [
            Schedule(
                id=s_row["id"],
                description=s_row["description"],
                allowed_hours=hw_by_schedule[s_row["id"]],
            )
            for s_row in sched_rows
        ]

        return WorkSchedules(timezone=timezone, schedules=schedules)

    def save_work_schedules(
        self, work_schedules: WorkSchedules, mode: Literal["upsert", "replace"] = "upsert"
    ) -> None:
        with self.conn:
            if mode == "replace":
                self.conn.execute("DELETE FROM hour_windows")
                self.conn.execute("DELETE FROM schedules")
                self.conn.execute("DELETE FROM work_schedules_meta")

            self.conn.execute(
                """
                INSERT INTO work_schedules_meta (id, timezone)
                VALUES (1, ?)
                ON CONFLICT(id) DO UPDATE SET timezone = excluded.timezone
                """,
                (work_schedules.timezone,),
            )

            for sched in work_schedules.schedules:
                self.conn.execute(
                    """
                    INSERT INTO schedules (id, description)
                    VALUES (?, ?)
                    ON CONFLICT(id) DO UPDATE SET description = excluded.description
                    """,
                    (sched.id, sched.description),
                )

                if mode == "upsert":
                    self.conn.execute("DELETE FROM hour_windows WHERE schedule_id = ?", (sched.id,))

                for seq, hw in enumerate(sched.allowed_hours):
                    self.conn.execute(
                        """
                        INSERT INTO hour_windows
                        (schedule_id, start_time, end_time, max_concurrency,
                         rate_limit_per_min, seq)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            sched.id,
                            hw.start,
                            hw.end,
                            hw.max_concurrency,
                            hw.rate_limit_per_min,
                            seq,
                        ),
                    )

    # --- ReportSettings Operations ---

    def get_report_settings(self) -> ReportSettings:
        row = self.conn.execute(
            """
            SELECT recipient, sender, subject_prefix, include_full_error_trace
            FROM report_settings WHERE id = 1
            """
        ).fetchone()

        if not row:
            return ReportSettings(
                recipient="admin@example.com",
                sender=None,
                subject_prefix="[BulkMailer Report]",
                include_full_error_trace=True,
            )

        return ReportSettings(
            recipient=row["recipient"],
            sender=row["sender"],
            subject_prefix=row["subject_prefix"],
            include_full_error_trace=bool(row["include_full_error_trace"]),
        )

    def save_report_settings(self, settings: ReportSettings) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO report_settings
                (id, recipient, sender, subject_prefix, include_full_error_trace)
                VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    recipient = excluded.recipient,
                    sender = excluded.sender,
                    subject_prefix = excluded.subject_prefix,
                    include_full_error_trace = excluded.include_full_error_trace
                """,
                (
                    settings.recipient,
                    settings.sender,
                    settings.subject_prefix,
                    1 if settings.include_full_error_trace else 0,
                ),
            )

    # --- MailConfiguration & MailTask Operations ---

    def get_mail_tasks(self) -> list[MailTask]:
        task_rows = self.conn.execute(
            """
            SELECT id, max_retries, priority, schedule_ref, sender, subject,
                   body_format, body_template_path
            FROM tasks
            ORDER BY id
            """
        ).fetchall()

        tasks: list[MailTask] = []
        for r in task_rows:
            task_id = r["id"]

            rec_rows = self.conn.execute(
                """
                SELECT recipient_type, email FROM task_recipients
                WHERE task_id = ? ORDER BY seq, id
                """,
                (task_id,),
            ).fetchall()

            to_list: list[str] = []
            cc_list: list[str] = []
            bcc_list: list[str] = []
            for rec in rec_rows:
                rtype = rec["recipient_type"]
                email = rec["email"]
                if rtype == "to":
                    to_list.append(email)
                elif rtype == "cc":
                    cc_list.append(email)
                elif rtype == "bcc":
                    bcc_list.append(email)

            var_rows = self.conn.execute(
                """
                SELECT var_name, var_value FROM task_context_variables
                WHERE task_id = ? ORDER BY seq, id
                """,
                (task_id,),
            ).fetchall()

            context_vars = [ContextVar(name=v["var_name"], value=v["var_value"]) for v in var_rows]

            tasks.append(
                MailTask(
                    id=task_id,
                    max_retries=r["max_retries"],
                    priority=r["priority"],
                    schedule_ref=r["schedule_ref"],
                    sender=r["sender"],
                    recipients=Recipients(to=to_list, cc=cc_list, bcc=bcc_list),
                    subject=r["subject"],
                    body_template=BodyTemplate(
                        format=r["body_format"], template_path=r["body_template_path"]
                    ),
                    context_variables=context_vars,
                )
            )

        return tasks

    def get_mail_configuration(self) -> MailConfiguration:
        report_settings = self.get_report_settings()
        tasks = self.get_mail_tasks()
        return MailConfiguration(report_settings=report_settings, tasks=tasks)

    def save_mail_configuration(
        self,
        mail_config: MailConfiguration,
        mode: Literal["upsert", "replace"] = "upsert",
    ) -> None:
        with self.conn:
            self.save_report_settings(mail_config.report_settings)

            if mode == "replace":
                self.conn.execute("DELETE FROM task_context_variables")
                self.conn.execute("DELETE FROM task_recipients")
                self.conn.execute("DELETE FROM tasks")

            for task in mail_config.tasks:
                self.conn.execute(
                    """
                    INSERT INTO tasks
                    (id, max_retries, priority, schedule_ref, sender, subject,
                     body_format, body_template_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        max_retries = excluded.max_retries,
                        priority = excluded.priority,
                        schedule_ref = excluded.schedule_ref,
                        sender = excluded.sender,
                        subject = excluded.subject,
                        body_format = excluded.body_format,
                        body_template_path = excluded.body_template_path
                    """,
                    (
                        task.id,
                        task.max_retries,
                        task.priority,
                        task.schedule_ref,
                        task.sender,
                        task.subject,
                        task.body_template.format,
                        task.body_template.template_path,
                    ),
                )

                if mode == "upsert":
                    self.conn.execute("DELETE FROM task_recipients WHERE task_id = ?", (task.id,))
                    self.conn.execute(
                        "DELETE FROM task_context_variables WHERE task_id = ?", (task.id,)
                    )

                # Insert recipients
                seq = 0
                for email in task.recipients.to:
                    self.conn.execute(
                        "INSERT INTO task_recipients "
                        "(task_id, recipient_type, email, seq) VALUES (?, 'to', ?, ?)",
                        (task.id, email, seq),
                    )
                    seq += 1
                for email in task.recipients.cc:
                    self.conn.execute(
                        "INSERT INTO task_recipients "
                        "(task_id, recipient_type, email, seq) VALUES (?, 'cc', ?, ?)",
                        (task.id, email, seq),
                    )
                    seq += 1
                for email in task.recipients.bcc:
                    self.conn.execute(
                        "INSERT INTO task_recipients "
                        "(task_id, recipient_type, email, seq) VALUES (?, 'bcc', ?, ?)",
                        (task.id, email, seq),
                    )
                    seq += 1

                # Insert context variables
                for seq_var, var in enumerate(task.context_variables):
                    self.conn.execute(
                        """
                        INSERT INTO task_context_variables (task_id, var_name, var_value, seq)
                        VALUES (?, ?, ?, ?)
                        """,
                        (task.id, var.name, var.value, seq_var),
                    )

    # --- Execution History / Logs ---

    def log_task_execution(
        self,
        result: TaskExecutionResult,
        batch_id: str | None = None,
    ) -> None:
        failed_recipients_str = json.dumps(result.failed_recipients)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO execution_logs
                (batch_id, task_id, status, sent_count, failed_recipients,
                 duration_ms, error_details, attempt_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    result.task_id,
                    result.status.value,
                    result.sent_count,
                    failed_recipients_str,
                    result.duration_ms,
                    result.error_details,
                    result.attempt_count,
                ),
            )

            self.conn.execute(
                """
                UPDATE tasks
                SET last_run = CURRENT_TIMESTAMP,
                    last_status = ?,
                    last_error = ?
                WHERE id = ?
                """,
                (result.status.value, result.error_details, result.task_id),
            )

    def get_execution_results_for_batch(self, batch_id: str) -> list[TaskExecutionResult]:
        rows = self.conn.execute(
            """
            SELECT task_id, status, sent_count, failed_recipients, duration_ms,
                   error_details, attempt_count
            FROM execution_logs
            WHERE batch_id = ?
            ORDER BY id
            """,
            (batch_id,),
        ).fetchall()

        results: list[TaskExecutionResult] = []
        for r in rows:
            failed_recipients = json.loads(r["failed_recipients"]) if r["failed_recipients"] else []
            results.append(
                TaskExecutionResult(
                    task_id=r["task_id"],
                    status=TaskExecutionStatus(r["status"]),
                    sent_count=r["sent_count"],
                    failed_recipients=failed_recipients,
                    duration_ms=r["duration_ms"],
                    error_details=r["error_details"],
                    attempt_count=r["attempt_count"],
                )
            )

        return results

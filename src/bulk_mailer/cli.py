import asyncio
import logging
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import typer

from bulk_mailer.database import get_connection, init_db
from bulk_mailer.mailer import AsyncMailer, TemplateRenderer
from bulk_mailer.models import (
    MailTask,
    Settings,
    TaskExecutionResult,
    TaskExecutionStatus,
)
from bulk_mailer.reporter import ReportGenerator, aggregate_summary_report
from bulk_mailer.repository import DatabaseRepository
from bulk_mailer.scheduler import TaskScheduler, TokenBucketRateLimiter
from bulk_mailer.xml_loader import (
    XMLValidationError,
    export_to_xml,
    import_from_xml,
)

app = typer.Typer(
    name="bulk-mailer",
    help="Asynchronous bulk email dispatch and reporting engine",
    invoke_without_command=True,
)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


async def run_dispatch_pipeline(
    tasks_xml: Path | None = None,
    schedule_xml: Path | None = None,
    dry_run: bool = False,
    verbose: bool = False,
    ref_dt: datetime | None = None,
    db_path: str = "bulk_mailer.db",
) -> int:
    setup_logging(verbose)
    logger = logging.getLogger("bulk_mailer.cli")

    start_time = datetime.now(UTC)
    logger.info(f"Starting bulk email dispatch engine (dry_run={dry_run}, db={db_path})...")

    conn = get_connection(db_path)
    init_db(conn)
    repo = DatabaseRepository(conn)

    # If tasks_xml and schedule_xml are provided, seed or update SQLite DB
    if tasks_xml and schedule_xml:
        try:
            import_from_xml(conn, tasks_xml, schedule_xml, mode="upsert")
        except XMLValidationError as exc:
            logger.error(f"Configuration error: {exc}")
            return 1
        except Exception as exc:
            logger.error(f"Unexpected error loading XML configs: {exc}")
            return 1

    try:
        mail_config = repo.get_mail_configuration()
        work_schedules = repo.get_work_schedules()
        execution_states = repo.get_task_execution_states()
    except Exception as exc:
        logger.error(f"Failed to load configuration from database: {exc}")
        return 1

    if not mail_config.tasks:
        logger.warning("No tasks found in database.")
        return 0

    settings = Settings.load()
    renderer = TemplateRenderer()
    mailer = AsyncMailer(settings=settings, renderer=renderer, dry_run=dry_run)
    scheduler = TaskScheduler(work_schedules)

    batch_id = str(uuid.uuid4())

    # Evaluate task eligibility
    eligible_tasks: list[tuple[MailTask, TokenBucketRateLimiter, asyncio.Semaphore]] = []
    results: list[TaskExecutionResult] = []
    window_controls: dict[
        tuple[str, str, str], tuple[TokenBucketRateLimiter, asyncio.Semaphore]
    ] = {}

    for task in mail_config.tasks:
        last_run, last_status = execution_states.get(task.id, (None, None))
        eligible, window = scheduler.is_task_eligible(
            task, reference_dt=ref_dt, last_run=last_run, last_status=last_status
        )
        if eligible and window is not None:
            key = (task.schedule_ref, window.start, window.end)
            if key not in window_controls:
                window_controls[key] = (
                    TokenBucketRateLimiter(window.rate_limit_per_min),
                    asyncio.Semaphore(window.max_concurrency),
                )
            rate_limiter, semaphore = window_controls[key]
            eligible_tasks.append((task, rate_limiter, semaphore))
        else:
            logger.info(f"Task {task.id} skipped due to schedule rules.")
            skipped_res = TaskExecutionResult(
                task_id=task.id,
                status=TaskExecutionStatus.SKIPPED_SCHEDULE,
                sent_count=0,
                duration_ms=0.0,
                error_details=f"Schedule '{task.schedule_ref}' not active at current time",
            )
            results.append(skipped_res)
            repo.log_task_execution(skipped_res, batch_id=batch_id)

    logger.info(f"Scheduled {len(eligible_tasks)} tasks for execution ({len(results)} skipped).")

    # Concurrent task execution using asyncio.TaskGroup
    async def _execute_single_task(
        task: MailTask,
        rate_limiter: TokenBucketRateLimiter,
        sem: asyncio.Semaphore,
    ) -> TaskExecutionResult:
        async with sem:
            logger.info(f"Executing task {task.id}...")
            res = await mailer.dispatch_task(task, rate_limiter=rate_limiter)
            repo.log_task_execution(res, batch_id=batch_id)
            return res

    if eligible_tasks:
        exec_results: list[TaskExecutionResult] = []
        async with asyncio.TaskGroup() as tg:
            tasks_tg = [
                tg.create_task(_execute_single_task(t, rl, sem)) for t, rl, sem in eligible_tasks
            ]
        for completed_task in tasks_tg:
            exec_results.append(completed_task.result())

        results.extend(exec_results)

    end_time = datetime.now(UTC)

    # Aggregate report and send
    report = aggregate_summary_report(results, start_time, end_time)
    reporter = ReportGenerator()
    await reporter.send_report(report, mail_config.report_settings, mailer)

    logger.info("Bulk mailer execution complete.")
    return 0 if report.failed_tasks == 0 else 2


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    tasks_xml: Annotated[
        Path | None,
        typer.Option(
            "--tasks-xml",
            "-t",
            help="Path to tasks configuration XML file to seed database",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    schedule_xml: Annotated[
        Path | None,
        typer.Option(
            "--schedule-xml",
            "-s",
            help="Path to hourly work schedules XML file to seed database",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    db: Annotated[
        str,
        typer.Option(
            "--db",
            "-b",
            envvar="BULK_MAILER_DB",
            help="Path to SQLite database file",
        ),
    ] = "bulk_mailer.db",
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-d",
            help="Execute without sending real network SMTP requests",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable verbose debug logging",
        ),
    ] = False,
) -> None:
    if ctx.invoked_subcommand is None:
        exit_code = asyncio.run(
            run_dispatch_pipeline(
                tasks_xml=tasks_xml,
                schedule_xml=schedule_xml,
                dry_run=dry_run,
                verbose=verbose,
                db_path=db,
            )
        )
        raise typer.Exit(code=exit_code)


@app.command("import-xml")
def cli_import_xml(
    tasks_xml: Annotated[
        Path,
        typer.Option(
            "--tasks-xml",
            "-t",
            help="Path to tasks configuration XML file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    schedule_xml: Annotated[
        Path,
        typer.Option(
            "--schedule-xml",
            "-s",
            help="Path to hourly work schedules XML file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    db: Annotated[
        str,
        typer.Option(
            "--db",
            "-b",
            envvar="BULK_MAILER_DB",
            help="Path to SQLite database file",
        ),
    ] = "bulk_mailer.db",
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            "-m",
            help="Import mode: 'upsert' (update existing) or 'replace' (wipe and replace)",
        ),
    ] = "upsert",
) -> None:
    """Import tasks and schedules XML into the SQLite database."""
    conn = get_connection(db)
    init_db(conn)
    import_mode: Literal["upsert", "replace"] = "replace" if mode.lower() == "replace" else "upsert"

    try:
        import_from_xml(conn, tasks_xml, schedule_xml, mode=import_mode)
        typer.echo(
            f"Successfully imported {tasks_xml} and {schedule_xml} into {db} ({import_mode})."
        )
    except XMLValidationError as exc:
        typer.echo(f"XML Validation Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.echo(f"Error importing XML: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("export-xml")
def cli_export_xml(
    tasks_xml: Annotated[
        Path,
        typer.Option(
            "--tasks-xml",
            "-t",
            help="Target path for tasks configuration XML file",
        ),
    ],
    schedule_xml: Annotated[
        Path,
        typer.Option(
            "--schedule-xml",
            "-s",
            help="Target path for hourly work schedules XML file",
        ),
    ],
    db: Annotated[
        str,
        typer.Option(
            "--db",
            "-b",
            envvar="BULK_MAILER_DB",
            help="Path to SQLite database file",
        ),
    ] = "bulk_mailer.db",
) -> None:
    """Export current SQLite database configuration to XML files."""
    conn = get_connection(db)
    init_db(conn)

    try:
        export_to_xml(conn, tasks_xml, schedule_xml)
        typer.echo(f"Successfully exported database {db} to {tasks_xml} and {schedule_xml}.")
    except Exception as exc:
        typer.echo(f"Error exporting XML: {exc}", err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()

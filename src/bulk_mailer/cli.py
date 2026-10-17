import asyncio
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from bulk_mailer.mailer import AsyncMailer, TemplateRenderer
from bulk_mailer.models import (
    MailTask,
    Settings,
    TaskExecutionResult,
    TaskExecutionStatus,
)
from bulk_mailer.reporter import ReportGenerator, aggregate_summary_report
from bulk_mailer.scheduler import TaskScheduler, TokenBucketRateLimiter
from bulk_mailer.xml_loader import (
    XMLValidationError,
    load_mail_configuration,
    load_work_schedules,
    validate_xml_configs,
)

app = typer.Typer(
    name="bulk-mailer",
    help="Asynchronous bulk email dispatch and reporting engine",
)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


async def run_dispatch_pipeline(
    tasks_xml: Path,
    schedule_xml: Path,
    dry_run: bool,
    verbose: bool = False,
    ref_dt: datetime | None = None,
) -> int:
    setup_logging(verbose)
    logger = logging.getLogger("bulk_mailer.cli")

    start_time = datetime.now(UTC)
    logger.info(f"Starting bulk email dispatch engine (dry_run={dry_run})...")

    # 1. Load and validate XML configurations
    try:
        mail_config = load_mail_configuration(tasks_xml)
        work_schedules = load_work_schedules(schedule_xml)
        validate_xml_configs(mail_config, work_schedules)
    except XMLValidationError as exc:
        logger.error(f"Configuration error: {exc}")
        return 1
    except Exception as exc:
        logger.error(f"Unexpected error loading XML configs: {exc}")
        return 1

    settings = Settings.load()
    renderer = TemplateRenderer()
    mailer = AsyncMailer(settings=settings, renderer=renderer, dry_run=dry_run)
    scheduler = TaskScheduler(work_schedules)

    # 2. Evaluate task eligibility
    eligible_tasks: list[tuple[MailTask, TokenBucketRateLimiter, asyncio.Semaphore]] = []
    results: list[TaskExecutionResult] = []

    for task in mail_config.tasks:
        eligible, window = scheduler.is_task_eligible(task, reference_dt=ref_dt)
        if eligible and window is not None:
            rate_limiter = TokenBucketRateLimiter(window.rate_limit_per_min)
            semaphore = asyncio.Semaphore(window.max_concurrency)
            eligible_tasks.append((task, rate_limiter, semaphore))
        else:
            logger.info(f"Task {task.id} skipped due to schedule rules.")
            results.append(
                TaskExecutionResult(
                    task_id=task.id,
                    status=TaskExecutionStatus.SKIPPED_SCHEDULE,
                    sent_count=0,
                    duration_ms=0.0,
                    error_details=f"Schedule '{task.schedule_ref}' not active at current time",
                )
            )

    logger.info(f"Scheduled {len(eligible_tasks)} tasks for execution ({len(results)} skipped).")

    # 3. Concurrent task execution using asyncio.TaskGroup
    async def _execute_single_task(
        task: MailTask,
        rate_limiter: TokenBucketRateLimiter,
        sem: asyncio.Semaphore,
    ) -> TaskExecutionResult:
        async with sem:
            logger.info(f"Executing task {task.id}...")
            return await mailer.dispatch_task(task, rate_limiter=rate_limiter)

    if eligible_tasks:
        exec_results: list[TaskExecutionResult] = []
        async with asyncio.TaskGroup() as tg:
            tasks_tg = [
                tg.create_task(_execute_single_task(t, rl, sem))
                for t, rl, sem in eligible_tasks
            ]
        for completed_task in tasks_tg:
            exec_results.append(completed_task.result())

        results.extend(exec_results)

    end_time = datetime.now(UTC)

    # 4. Aggregate report and send
    report = aggregate_summary_report(results, start_time, end_time)
    reporter = ReportGenerator()
    await reporter.send_report(report, mail_config.report_settings, mailer)

    logger.info("Bulk mailer execution complete.")
    return 0 if report.failed_tasks == 0 else 2


@app.command()
def main(
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
    exit_code = asyncio.run(
        run_dispatch_pipeline(
            tasks_xml=tasks_xml,
            schedule_xml=schedule_xml,
            dry_run=dry_run,
            verbose=verbose,
        )
    )
    raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()

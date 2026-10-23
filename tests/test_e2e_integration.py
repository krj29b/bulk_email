from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bulk_mailer.cli import run_dispatch_pipeline
from bulk_mailer.database import get_connection
from bulk_mailer.models import TaskExecutionStatus
from bulk_mailer.repository import DatabaseRepository


@pytest.mark.asyncio
async def test_full_dispatch_pipeline_with_ref_dt(tmp_path: Path) -> None:
    tasks_file = Path("config/samples/tasks.xml")
    schedules_file = Path("config/samples/schedules.xml")

    # Reference time: 2026-10-17 08:00 Warsaw time (Morning schedule is active: 06:00-12:00)
    ref_dt = datetime(2026, 10, 17, 8, 0, tzinfo=ZoneInfo("Europe/Warsaw"))

    code = await run_dispatch_pipeline(
        tasks_xml=tasks_file,
        schedule_xml=schedules_file,
        dry_run=True,
        verbose=True,
        ref_dt=ref_dt,
    )

    assert code == 0


@pytest.mark.asyncio
async def test_run_dispatch_pipeline_idempotency_two_runs(tmp_path: Path) -> None:
    tasks_file = Path("config/samples/tasks.xml")
    schedules_file = Path("config/samples/schedules.xml")
    db_file = tmp_path / "test_idempotency.db"

    # Reference time: 2026-10-17 08:00 Warsaw time (Morning schedule active: 06:00-12:00)
    ref_dt = datetime(2026, 10, 17, 8, 0, tzinfo=ZoneInfo("Europe/Warsaw"))

    # First run
    code1 = await run_dispatch_pipeline(
        tasks_xml=tasks_file,
        schedule_xml=schedules_file,
        dry_run=True,
        verbose=True,
        ref_dt=ref_dt,
        db_path=str(db_file),
    )
    assert code1 == 0

    # Verify task state in database after first run
    conn = get_connection(db_file)
    repo = DatabaseRepository(conn)
    states1 = repo.get_task_execution_states()
    assert any(status == TaskExecutionStatus.SUCCESS for _, status in states1.values())

    # Second run with same ref_dt and same database
    code2 = await run_dispatch_pipeline(
        tasks_xml=tasks_file,
        schedule_xml=schedules_file,
        dry_run=True,
        verbose=True,
        ref_dt=ref_dt,
        db_path=str(db_file),
    )
    assert code2 == 0

    # Execution logs should now record SKIPPED_SCHEDULE for the second run
    logs = conn.execute(
        "SELECT status FROM execution_logs ORDER BY id DESC LIMIT 2"
    ).fetchall()
    statuses = [r["status"] for r in logs]
    assert TaskExecutionStatus.SKIPPED_SCHEDULE.value in statuses


@pytest.mark.asyncio
async def test_full_dispatch_pipeline_invalid_xml(tmp_path: Path) -> None:
    invalid_xml = tmp_path / "invalid.xml"
    invalid_xml.write_bytes(b"<MailConfiguration><BadTag></MailConfiguration>")
    schedules_file = Path("config/samples/schedules.xml")

    code = await run_dispatch_pipeline(
        tasks_xml=invalid_xml,
        schedule_xml=schedules_file,
        dry_run=True,
    )

    assert code == 1

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bulk_mailer.cli import run_dispatch_pipeline


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

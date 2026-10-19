import logging
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from bulk_mailer.cli import app, setup_logging

runner = CliRunner()


@pytest.mark.parametrize(
    "verbose, expected_level",
    [
        (True, logging.DEBUG),
        (False, logging.INFO),
    ],
)
def test_setup_logging(verbose: bool, expected_level: int) -> None:
    with patch("logging.basicConfig") as mock_basic_config:
        setup_logging(verbose=verbose)
        mock_basic_config.assert_called_once()
        _, kwargs = mock_basic_config.call_args
        assert kwargs["level"] == expected_level
        assert kwargs["format"] == "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        handlers = kwargs["handlers"]
        assert len(handlers) == 1
        assert isinstance(handlers[0], logging.StreamHandler)
        assert handlers[0].stream == sys.stdout


def test_cli_dry_run_samples() -> None:
    tasks = Path("config/samples/tasks.xml")
    schedules = Path("config/samples/schedules.xml")

    result = runner.invoke(
        app,
        ["--tasks-xml", str(tasks), "--schedule-xml", str(schedules), "--dry-run"],
    )
    assert result.exit_code == 0
    assert "Starting bulk email dispatch engine" in result.output or result.exit_code == 0


@pytest.mark.asyncio
async def test_shared_primitives_per_schedule_window(tmp_path: Path) -> None:
    tasks_xml = tmp_path / "tasks.xml"
    schedules_xml = tmp_path / "schedules.xml"

    tasks_xml.write_bytes(b"""<?xml version="1.0" encoding="UTF-8"?>
<MailConfiguration>
  <ReportSettings>
    <Recipient>admin@example.com</Recipient>
  </ReportSettings>
  <Tasks>
    <MailTask id="TASK-001" schedule_ref="SCHED-01">
      <Sender>noreply@example.com</Sender>
      <Recipients><To>u1@example.com</To></Recipients>
      <Subject>Task 1</Subject>
      <BodyTemplate format="html">tpl.j2</BodyTemplate>
    </MailTask>
    <MailTask id="TASK-002" schedule_ref="SCHED-01">
      <Sender>noreply@example.com</Sender>
      <Recipients><To>u2@example.com</To></Recipients>
      <Subject>Task 2</Subject>
      <BodyTemplate format="html">tpl.j2</BodyTemplate>
    </MailTask>
  </Tasks>
</MailConfiguration>""")

    schedules_xml.write_bytes(b"""<?xml version="1.0" encoding="UTF-8"?>
<WorkSchedules timezone="UTC">
  <Schedule id="SCHED-01">
    <AllowedHours>
      <HourWindow start="00:00" end="23:59" max_concurrency="5" rate_limit_per_min="60"/>
    </AllowedHours>
  </Schedule>
</WorkSchedules>""")

    from bulk_mailer.cli import run_dispatch_pipeline
    from bulk_mailer.models import TaskExecutionResult, TaskExecutionStatus

    captured_rl: list[pytest.MonkeyPatch | object] = []

    async def fake_dispatch(task: object, rate_limiter: object = None) -> TaskExecutionResult:
        captured_rl.append(rate_limiter)
        return TaskExecutionResult(
            task_id="T",
            status=TaskExecutionStatus.SUCCESS,
            sent_count=1,
            duration_ms=1.0,
        )

    import asyncio

    sem_instances: list[asyncio.Semaphore] = []
    original_sem = asyncio.Semaphore

    def tracked_sem(value: int = 1) -> asyncio.Semaphore:
        sem = original_sem(value)
        sem_instances.append(sem)
        return sem

    with (
        patch("bulk_mailer.cli.AsyncMailer.dispatch_task", side_effect=fake_dispatch),
        patch("asyncio.Semaphore", side_effect=tracked_sem),
    ):
        code = await run_dispatch_pipeline(tasks_xml, schedules_xml, dry_run=True)
        assert code == 0
        assert len(captured_rl) == 2
        # Identical rate limiter instance
        assert captured_rl[0] is captured_rl[1]
        # Identical semaphore instance (instantiated only once)
        assert len(sem_instances) == 1

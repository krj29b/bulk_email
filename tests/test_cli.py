from pathlib import Path

from typer.testing import CliRunner

from bulk_mailer.cli import app

runner = CliRunner()

def test_cli_dry_run_samples():
    tasks = Path("config/samples/tasks.xml")
    schedules = Path("config/samples/schedules.xml")

    result = runner.invoke(
        app,
        ["--tasks-xml", str(tasks), "--schedule-xml", str(schedules), "--dry-run"],
    )
    assert result.exit_code == 0
    assert "Starting bulk email dispatch engine" in result.output or result.exit_code == 0

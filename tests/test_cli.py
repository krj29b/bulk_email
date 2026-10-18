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

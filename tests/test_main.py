import asyncio
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import main as main_module
import pytest


def test_load_recipients(tmp_path: Path) -> None:
    path = (tmp_path / "data") / "email_list.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("a@example.com\nb@example.com\n\n", encoding="utf-8")

    logger = MagicMock()
    recipients = main_module.load_recipients(path, logger)
    assert recipients == ["a@example.com", "b@example.com"]


def test_load_recipients_missing_file(tmp_path: Path) -> None:
    path = (tmp_path / "data") / "non_existent.txt"
    logger = MagicMock()
    recipients = main_module.load_recipients(path, logger)
    assert recipients == []
    logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_main_async_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_dir = tmp_path / "base"
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    email_file = data_dir / "email_list.txt"
    email_file.write_text(
        "user1@example.com\nuser2@example.com\nuser3@example.com\n",
        encoding="utf-8",
    )

    log_dir = base_dir / "log"
    log_file = log_dir / "test_bulk_email.log"

    test_config = {
        "smtp_server": "smtp.example.com",
        "port": 587,
        "login": "test_user",
        "password": "test_password",
        "sender": "sender@example.com",
        "logging": {
            "log_file": str(log_file),
            "log_level": "INFO",
        },
    }

    monkeypatch.chdir(base_dir)
    monkeypatch.setattr("config.Config.init", lambda self: None)
    monkeypatch.setattr("config.Config.config", test_config)

    mock_smtp = AsyncMock()
    mock_smtp.is_connected = True
    mock_smtp.connect = AsyncMock()
    mock_smtp.login = AsyncMock()
    mock_smtp.send_message = AsyncMock()
    mock_smtp.quit = AsyncMock()

    await main_module.main(concurrency=2, custom_smtp_client=mock_smtp)

    assert mock_smtp.send_message.call_count == 3


@pytest.mark.asyncio
async def test_async_performance_boost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    num_emails = 50
    base_dir = tmp_path / "base"
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    email_file = data_dir / "email_list.txt"
    recipients = [f"user{i}@example.com" for i in range(num_emails)]
    email_file.write_text("\n".join(recipients) + "\n", encoding="utf-8")

    log_dir = base_dir / "log"
    log_file = log_dir / "perf_bulk_email.log"

    test_config = {
        "smtp_server": "smtp.example.com",
        "port": 587,
        "login": "test_user",
        "password": "test_password",
        "sender": "sender@example.com",
        "logging": {
            "log_file": str(log_file),
            "log_level": "INFO",
        },
    }

    monkeypatch.chdir(base_dir)
    monkeypatch.setattr("config.Config.init", lambda self: None)
    monkeypatch.setattr("config.Config.config", test_config)

    simulated_delay = 0.01  # 10ms per email send

    mock_smtp = AsyncMock()
    mock_smtp.is_connected = True

    async def fake_send(msg: Any) -> None:
        await asyncio.sleep(simulated_delay)

    mock_smtp.send_message.side_effect = fake_send

    t0 = time.perf_counter()
    await main_module.main(concurrency=10, custom_smtp_client=mock_smtp)
    async_duration = time.perf_counter() - t0

    sync_expected_time = num_emails * simulated_delay  # 0.50 seconds
    assert async_duration < sync_expected_time * 0.5  # At least 2x faster than sync sequential


@pytest.mark.asyncio
async def test_send_worker_task_done_on_exception() -> None:
    queue: asyncio.Queue[str] = asyncio.Queue()
    queue.put_nowait("fail@example.com")

    config = {
        "smtp_server": "localhost",
        "port": 25,
        "logging": {"log_file": "test.log", "log_level": "INFO"},
    }

    mock_smtp = AsyncMock()
    mock_smtp.is_connected = True
    mock_smtp.send_message = AsyncMock(side_effect=RuntimeError("SMTP dispatch error"))

    logger = MagicMock()

    with pytest.raises(RuntimeError, match="SMTP dispatch error"):
        await main_module.send_worker(
            queue=queue,
            config=config,
            context=None,
            sender="sender@example.com",
            log=logger,
            smtp_client=mock_smtp,
        )

    # Key assertion: task_done was called, unblocking queue.join()
    await asyncio.wait_for(queue.join(), timeout=1.0)
    assert queue._unfinished_tasks == 0  # type: ignore[attr-defined]

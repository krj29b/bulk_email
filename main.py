import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Any

import aiosmtplib
import ssl_context
from config import Config
from messages import (
    MESSAGE_TEXT as message_text,
)
from messages import (
    SUBJECT as subject,
)
from messages import (
    build_message,
)


def load_recipients(file_path: Path, log: logging.Logger) -> list[str]:
    if not file_path.exists():
        log.warning(f"{file_path} does not exist.")
        return []
    with file_path.open("r", encoding="utf-8") as f:
        return [line.strip("\n") for line in f if line.strip("\n")]


async def send_worker(
    queue: asyncio.Queue[str],
    config: dict[str, Any],
    context: Any,
    sender: str,
    log: logging.Logger,
    smtp_client: aiosmtplib.SMTP | None = None,
) -> None:
    smtp_server = str(config['smtp_server'])
    port = int(config['port'])
    login = str(config.get('login', ''))
    password = str(config.get('password', ''))

    client = smtp_client or aiosmtplib.SMTP(
        hostname=smtp_server,
        port=port,
        start_tls=True,
        tls_context=context,
    )

    try:
        if smtp_client is None or not getattr(client, "is_connected", False):
            await client.connect()
            if login and password:
                await client.login(login, password)

        while not queue.empty():
            try:
                recipient_email = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            msg = build_message(subject, sender, recipient_email, message_text)
            await client.send_message(msg)
            log.info(f'Sent to {recipient_email}')
            queue.task_done()
    finally:
        if smtp_client is None and getattr(client, "is_connected", False):
            with contextlib.suppress(Exception):
                await client.quit()


async def main(concurrency: int = 10, custom_smtp_client: aiosmtplib.SMTP | None = None) -> None:
    c = Config()
    c.init()

    if not c.config:
        raise ValueError("Configuration failed to load")

    log_file = c.config['logging']['log_file']
    log_file_path = Path(log_file)
    if log_file_path.parent:
        log_file_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        filename=log_file,
        encoding='utf-8',
        level=getattr(logging, c.config['logging']['log_level']),
    )
    log = logging.getLogger()

    sender = str(c.config['sender'])

    recipient_list = load_recipients(Path('data/email_list.txt'), log)

    if not recipient_list:
        log.info("No recipients to send emails to.")
        return

    context = ssl_context.get_context()

    queue: asyncio.Queue[str] = asyncio.Queue()
    for recipient_email in recipient_list:
        queue.put_nowait(recipient_email)

    num_workers = min(concurrency, len(recipient_list))
    workers = [
        asyncio.create_task(
            send_worker(
                queue,
                c.config,
                context,
                sender,
                log,
                smtp_client=custom_smtp_client,
            )
        )
        for _ in range(num_workers)
    ]

    await queue.join()
    await asyncio.gather(*workers)


if __name__ == '__main__':
    asyncio.run(main())

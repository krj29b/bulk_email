from datetime import time

from bulk_mailer.models import (
    BodyTemplate,
    ContextVar,
    HourWindow,
    MailTask,
    Recipients,
    parse_time_str,
)


def test_get_context_dict_empty() -> None:
    task = MailTask(
        id="TASK-EMPTY",
        schedule_ref="SCHED-01",
        sender="sender@example.com",
        recipients=Recipients(to=["user@example.com"]),
        subject="Test Subject",
        body_template=BodyTemplate(template_path="template.html"),
        context_variables=[],
    )
    assert task.get_context_dict() == {}


def test_get_context_dict_single_and_multiple_vars() -> None:
    task = MailTask(
        id="TASK-VARS",
        schedule_ref="SCHED-01",
        sender="sender@example.com",
        recipients=Recipients(to=["user@example.com"]),
        subject="Test Subject",
        body_template=BodyTemplate(template_path="template.html"),
        context_variables=[
            ContextVar(name="first_name", value="John"),
            ContextVar(name="last_name", value="Doe"),
            ContextVar(name="company", value="Acme Corp"),
        ],
    )
    expected = {
        "first_name": "John",
        "last_name": "Doe",
        "company": "Acme Corp",
    }
    assert task.get_context_dict() == expected


def test_get_context_dict_duplicate_keys() -> None:
    task = MailTask(
        id="TASK-DUP",
        schedule_ref="SCHED-01",
        sender="sender@example.com",
        recipients=Recipients(to=["user@example.com"]),
        subject="Test Subject",
        body_template=BodyTemplate(template_path="template.html"),
        context_variables=[
            ContextVar(name="role", value="developer"),
            ContextVar(name="role", value="maintainer"),
        ],
    )
    assert task.get_context_dict() == {"role": "maintainer"}


def test_get_context_dict_special_chars_and_empty_values() -> None:
    task = MailTask(
        id="TASK-SPECIAL",
        schedule_ref="SCHED-01",
        sender="sender@example.com",
        recipients=Recipients(to=["user@example.com"]),
        subject="Test Subject",
        body_template=BodyTemplate(template_path="template.html"),
        context_variables=[
            ContextVar(name="empty_val", value=""),
            ContextVar(name="var_with_spaces", value="hello world"),
            ContextVar(name="special_chars!@#$", value="123 & 456 <tag>"),
        ],
    )
    assert task.get_context_dict() == {
        "empty_val": "",
        "var_with_spaces": "hello world",
        "special_chars!@#$": "123 & 456 <tag>",
    }


def test_recipients_all_recipients() -> None:
    recipients = Recipients(
        to=["to1@example.com", "to2@example.com"],
        cc=["cc1@example.com"],
        bcc=["bcc1@example.com"],
    )
    assert recipients.all_recipients == [
        "to1@example.com",
        "to2@example.com",
        "cc1@example.com",
        "bcc1@example.com",
    ]


def test_parse_time_str() -> None:
    assert parse_time_str("09:30") == time(9, 30, 0)
    assert parse_time_str("18:45:30") == time(18, 45, 30)


def test_hour_window_start_and_end_time() -> None:
    hw = HourWindow(start="08:00:00", end="17:00:00")
    assert hw.start_time == time(8, 0, 0)
    assert hw.end_time == time(17, 0, 0)

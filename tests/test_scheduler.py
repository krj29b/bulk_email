import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bulk_mailer.models import (
    BodyTemplate,
    HourWindow,
    MailTask,
    Recipients,
    Schedule,
    WorkSchedules,
)
from bulk_mailer.scheduler import (
    TaskScheduler,
    TokenBucketRateLimiter,
    is_time_in_window,
    parse_time_str,
)


def test_parse_time_str() -> None:
    assert parse_time_str("08:30") == datetime.strptime("08:30", "%H:%M").time()
    assert parse_time_str("14:15:30") == datetime.strptime("14:15:30", "%H:%M:%S").time()

def test_is_time_in_window() -> None:
    t1 = parse_time_str("10:00")
    t2 = parse_time_str("05:00")
    t3 = parse_time_str("23:00")

    s = parse_time_str("06:00")
    e = parse_time_str("12:00")

    assert is_time_in_window(t1, s, e) is True
    assert is_time_in_window(t2, s, e) is False
    assert is_time_in_window(t3, s, e) is False

    # Midnight spanning
    s_overnight = parse_time_str("22:00")
    e_overnight = parse_time_str("04:00")
    assert is_time_in_window(parse_time_str("23:00"), s_overnight, e_overnight) is True
    assert is_time_in_window(parse_time_str("02:00"), s_overnight, e_overnight) is True
    assert is_time_in_window(parse_time_str("12:00"), s_overnight, e_overnight) is False

    # Midnight spanning edge cases: times before start_time and after end_time (outside window)
    assert is_time_in_window(parse_time_str("05:00"), s_overnight, e_overnight) is False
    assert is_time_in_window(parse_time_str("21:00"), s_overnight, e_overnight) is False
    assert is_time_in_window(parse_time_str("04:00:01"), s_overnight, e_overnight) is False
    assert is_time_in_window(parse_time_str("21:59:59"), s_overnight, e_overnight) is False

    # Midnight spanning boundaries: exact start_time and end_time
    assert is_time_in_window(parse_time_str("22:00"), s_overnight, e_overnight) is True
    assert is_time_in_window(parse_time_str("04:00"), s_overnight, e_overnight) is True

def test_task_scheduler_timezones() -> None:
    schedules = WorkSchedules(
        timezone="Europe/Warsaw",
        schedules=[
            Schedule(
                id="SCHED-MORNING",
                allowed_hours=[
                    HourWindow(start="06:00", end="12:00", max_concurrency=5, rate_limit_per_min=60)
                ]
            )
        ]
    )

    scheduler = TaskScheduler(schedules)
    task = MailTask(
        id="T1",
        schedule_ref="SCHED-MORNING",
        sender="s@example.com",
        recipients=Recipients(to=["r@example.com"]),
        subject="Subject",
        body_template=BodyTemplate(template_path="t.j2")
    )

    # 08:00 Warsaw time (UTC+1/UTC+2 depending on DST)
    # 2026-10-17 08:00 Warsaw time
    dt_warsaw = datetime(2026, 10, 17, 8, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
    eligible, window = scheduler.is_task_eligible(task, reference_dt=dt_warsaw)
    assert eligible is True
    assert window is not None
    assert window.max_concurrency == 5

    # 14:00 Warsaw time
    dt_afternoon = datetime(2026, 10, 17, 14, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
    eligible, window = scheduler.is_task_eligible(task, reference_dt=dt_afternoon)
    assert eligible is False
    assert window is None


def test_is_task_eligible_naive_datetime() -> None:
    schedules = WorkSchedules(
        timezone="Europe/Warsaw",
        schedules=[
            Schedule(
                id="SCHED-MORNING",
                allowed_hours=[
                    HourWindow(start="06:00", end="12:00", max_concurrency=5, rate_limit_per_min=60)
                ]
            )
        ]
    )
    scheduler = TaskScheduler(schedules)
    task = MailTask(
        id="T1",
        schedule_ref="SCHED-MORNING",
        sender="s@example.com",
        recipients=Recipients(to=["r@example.com"]),
        subject="Subject",
        body_template=BodyTemplate(template_path="t.j2")
    )

    # Naive datetime during allowed window (08:00)
    naive_dt = datetime(2026, 10, 17, 8, 0)
    assert naive_dt.tzinfo is None
    eligible, window = scheduler.is_task_eligible(task, reference_dt=naive_dt)
    assert eligible is True
    assert window is not None
    assert window.max_concurrency == 5

    # Naive datetime outside allowed window (15:00)
    naive_dt_outside = datetime(2026, 10, 17, 15, 0)
    assert naive_dt_outside.tzinfo is None
    eligible_out, window_out = scheduler.is_task_eligible(task, reference_dt=naive_dt_outside)
    assert eligible_out is False
    assert window_out is None


def test_is_task_eligible_none_datetime() -> None:
    schedules = WorkSchedules(
        timezone="Europe/Warsaw",
        schedules=[
            Schedule(
                id="SCHED-MORNING",
                allowed_hours=[
                    HourWindow(start="00:00", end="23:59", max_concurrency=5, rate_limit_per_min=60)
                ]
            )
        ]
    )
    scheduler = TaskScheduler(schedules)
    task = MailTask(
        id="T1",
        schedule_ref="SCHED-MORNING",
        sender="s@example.com",
        recipients=Recipients(to=["r@example.com"]),
        subject="Subject",
        body_template=BodyTemplate(template_path="t.j2")
    )

    eligible, window = scheduler.is_task_eligible(task, reference_dt=None)
    assert eligible is True
    assert window is not None


def test_is_task_eligible_tz_conversion() -> None:
    schedules = WorkSchedules(
        timezone="Europe/Warsaw",
        schedules=[
            Schedule(
                id="SCHED-MORNING",
                allowed_hours=[
                    HourWindow(start="06:00", end="12:00", max_concurrency=5, rate_limit_per_min=60)
                ]
            )
        ]
    )
    scheduler = TaskScheduler(schedules)
    task = MailTask(
        id="T1",
        schedule_ref="SCHED-MORNING",
        sender="s@example.com",
        recipients=Recipients(to=["r@example.com"]),
        subject="Subject",
        body_template=BodyTemplate(template_path="t.j2")
    )

    # 07:00 UTC on Oct 17 is 09:00 in Europe/Warsaw (CEST / UTC+2 in Oct) -> Eligible
    utc_dt = datetime(2026, 10, 17, 7, 0, tzinfo=ZoneInfo("UTC"))
    eligible, window = scheduler.is_task_eligible(task, reference_dt=utc_dt)
    assert eligible is True
    assert window is not None


def test_is_task_eligible_missing_schedule() -> None:
    schedules = WorkSchedules(
        timezone="Europe/Warsaw",
        schedules=[]
    )
    scheduler = TaskScheduler(schedules)
    task = MailTask(
        id="T1",
        schedule_ref="NON-EXISTENT",
        sender="s@example.com",
        recipients=Recipients(to=["r@example.com"]),
        subject="Subject",
        body_template=BodyTemplate(template_path="t.j2")
    )

    eligible, window = scheduler.is_task_eligible(task)
    assert eligible is False
    assert window is None


def test_is_task_eligible_unknown_schedule_ref() -> None:
    schedules = WorkSchedules(
        timezone="Europe/Warsaw",
        schedules=[
            Schedule(
                id="SCHED-MORNING",
                allowed_hours=[
                    HourWindow(start="06:00", end="12:00", max_concurrency=5, rate_limit_per_min=60)
                ]
            )
        ]
    )
    scheduler = TaskScheduler(schedules)
    task = MailTask(
        id="T1",
        schedule_ref="UNKNOWN_REF",
        sender="s@example.com",
        recipients=Recipients(to=["r@example.com"]),
        subject="Subject",
        body_template=BodyTemplate(template_path="t.j2")
    )

    eligible, window = scheduler.is_task_eligible(task)
    assert eligible is False
    assert window is None


@pytest.mark.asyncio
async def test_rate_limiter() -> None:
    limiter = TokenBucketRateLimiter(rate_limit_per_min=6000)  # fast limit for test
    start = asyncio.get_event_loop().time()
    for _ in range(5):
        await limiter.acquire()
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed < 1.0

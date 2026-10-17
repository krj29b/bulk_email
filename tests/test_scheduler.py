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


def test_parse_time_str():
    assert parse_time_str("08:30") == datetime.strptime("08:30", "%H:%M").time()
    assert parse_time_str("14:15:30") == datetime.strptime("14:15:30", "%H:%M:%S").time()

def test_is_time_in_window():
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

def test_task_scheduler_timezones():
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

@pytest.mark.asyncio
async def test_rate_limiter():
    limiter = TokenBucketRateLimiter(rate_limit_per_min=6000)  # fast limit for test
    start = asyncio.get_event_loop().time()
    for _ in range(5):
        await limiter.acquire()
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed < 1.0

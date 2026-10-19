import asyncio
import sqlite3
import time as time_module
from datetime import datetime, time
from zoneinfo import ZoneInfo

from bulk_mailer.models import HourWindow, MailTask, Schedule, WorkSchedules, parse_time_str
from bulk_mailer.repository import DatabaseRepository

__all__ = [
    "TaskScheduler",
    "TokenBucketRateLimiter",
    "get_active_window",
    "is_time_in_window",
    "parse_time_str",
]


def is_time_in_window(current_time: time, start_time: time, end_time: time) -> bool:
    if start_time <= end_time:
        return start_time <= current_time <= end_time
    else:
        # Window spans across midnight (e.g., 22:00 to 04:00)
        return current_time >= start_time or current_time <= end_time


def get_active_window(schedule: Schedule, dt: datetime) -> HourWindow | None:
    current_time = dt.time()
    for window in schedule.allowed_hours:
        if is_time_in_window(current_time, window.start_time, window.end_time):
            return window
    return None


class TokenBucketRateLimiter:
    def __init__(self, rate_limit_per_min: int) -> None:
        self.rate_limit_per_min = rate_limit_per_min
        self.capacity = float(max(1, rate_limit_per_min))
        self.tokens = self.capacity
        self.fill_rate = self.capacity / 60.0  # tokens per second
        self.last_update = time_module.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self.rate_limit_per_min <= 0:
            return

        async with self._lock:
            while True:
                now = time_module.monotonic()
                elapsed = now - self.last_update
                self.last_update = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return

                needed = 1.0 - self.tokens
                wait_time = needed / self.fill_rate
                await asyncio.sleep(wait_time)


class TaskScheduler:
    def __init__(self, work_schedules: WorkSchedules | sqlite3.Connection) -> None:
        if isinstance(work_schedules, sqlite3.Connection):
            repo = DatabaseRepository(work_schedules)
            self.work_schedules = repo.get_work_schedules()
        else:
            self.work_schedules = work_schedules

        self.timezone = ZoneInfo(self.work_schedules.timezone)
        self._schedules_by_id: dict[str, Schedule] = {
            s.id: s for s in self.work_schedules.schedules
        }

    def is_task_eligible(
        self, task: MailTask, reference_dt: datetime | None = None
    ) -> tuple[bool, HourWindow | None]:
        schedule = self._schedules_by_id.get(task.schedule_ref)
        if not schedule:
            return False, None

        if reference_dt is None:
            reference_dt = datetime.now(self.timezone)
        elif reference_dt.tzinfo is None:
            reference_dt = reference_dt.replace(tzinfo=self.timezone)
        else:
            reference_dt = reference_dt.astimezone(self.timezone)

        window = get_active_window(schedule, reference_dt)
        if window is not None:
            return True, window

        return False, None

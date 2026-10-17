# Bulk Mailer Engine

Production-grade, asynchronous bulk email dispatch and reporting engine built in **Python 3.12+**.

## Overview

`bulk-mailer` parses two XML configuration files (`tasks.xml` and `schedules.xml`), evaluates active schedule windows across timezones, concurrently dispatches scheduled email tasks with rate limiting and exponential backoff retry resilience, and sends a final Task Completion Status Report email upon completion.

## Features
- **Python 3.12+ Standards:** Strict type safety, `asyncio.TaskGroup`, `StrEnum`, `pydantic v2`, and `pydantic-xml`.
- **Safe XML Parsing:** `defusedxml` integration to prevent XML vulnerabilities.
- **Timezone-Aware Throttling:** `zoneinfo` hourly schedule windows with `TokenBucketRateLimiter` and `asyncio.Semaphore` concurrency controls.
- **Async SMTP Dispatch & Retries:** `aiosmtplib` with exponential backoff on transient errors and `--dry-run` simulation mode.
- **Jinja2 Templating:** Templated task emails and consolidated HTML/plain-text summary status report emails.

## Usage

### Installation
```bash
make install
```

### Dry Run Execution
```bash
make run-dry
```

Or run via CLI:
```bash
bulk-mailer --tasks-xml config/samples/tasks.xml --schedule-xml config/samples/schedules.xml --dry-run
```

### Running Tests and Quality Gates
```bash
make test
make quality-gate
```

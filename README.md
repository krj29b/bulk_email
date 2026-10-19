# Bulk Mailer Engine

Production-grade, asynchronous bulk email dispatch and reporting engine built in **Python 3.12+**.

## Overview

`bulk-mailer` uses SQLite as its primary database backend for runtime configurations and execution history logging, while retaining XML support for importing and exporting `tasks.xml` and `schedules.xml`. It evaluates active schedule windows across timezones, concurrently dispatches scheduled email tasks with rate limiting and exponential backoff retry resilience, and sends a final Task Completion Status Report email upon completion.

## Features
- **Python 3.12+ Standards:** Strict type safety, `asyncio.TaskGroup`, `StrEnum`, `pydantic v2`, and `pydantic-xml`.
- **SQLite Persistence & Runtime DB:** Centralized database storage for schedules, tasks, report settings, and execution history logs.
- **Safe XML Import & Export:** `defusedxml` and `pydantic-xml` integration to import XML configuration into SQLite or export SQLite configurations back to XML files.
- **Timezone-Aware Throttling:** `zoneinfo` hourly schedule windows with `TokenBucketRateLimiter` and `asyncio.Semaphore` concurrency controls.
- **Async SMTP Dispatch & Retries:** `aiosmtplib` with exponential backoff on transient errors and `--dry-run` simulation mode.
- **Jinja2 Templating:** Templated task emails and consolidated HTML/plain-text summary status report emails.

## Configuration

`bulk-mailer` is configured through environment variables (or a `.env` file) for SMTP server options and XML configuration files for task definitions and execution schedules.

### Environment & SMTP Settings

Environment variables can be set directly or placed in a `.env` file in the project root:

| Variable | Default | Description |
| --- | --- | --- |
| `SMTP_HOST` | `localhost` | Hostname or IP address of the SMTP server |
| `SMTP_PORT` | `1025` | Port number for the SMTP server |
| `SMTP_USER` | *None* | Username for SMTP authentication (optional) |
| `SMTP_PASSWORD` | *None* | Password for SMTP authentication (optional) |
| `SMTP_USE_TLS` | `false` | Enable TLS connection (`true`/`false`) |
| `SMTP_START_TLS` | `false` | Enable STARTTLS (`true`/`false`) |
| `SMTP_TIMEOUT` | `30.0` | Timeout in seconds for SMTP operations |
| `BULK_MAILER_DB` | `bulk_mailer.db` | Path to SQLite database file |

### Tasks Configuration (`tasks.xml`)

The tasks configuration XML file defines email dispatch tasks, template references, context variables, and global report settings.

#### Structure & Example
```xml
<?xml version="1.0" encoding="UTF-8"?>
<MailConfiguration>
  <ReportSettings>
    <Recipient>ops-alerts@example.com</Recipient>
    <Sender>mailer-daemon@example.com</Sender>
    <SubjectPrefix>[BulkMailer Status Report]</SubjectPrefix>
    <IncludeFullErrorTrace>true</IncludeFullErrorTrace>
  </ReportSettings>
  <Tasks>
    <MailTask id="TASK-001" max_retries="3" priority="high" schedule_ref="SCHED-MORNING">
      <Sender>noreply@example.com</Sender>
      <Recipients>
        <To>client.alpha@example.com</To>
        <To>client.beta@example.com</To>
        <Cc>account.manager@example.com</Cc>
      </Recipients>
      <Subject>Daily Operational Dispatch - EMEA</Subject>
      <BodyTemplate format="html">templates/daily_dispatch.html.j2</BodyTemplate>
      <ContextVariables>
        <Var name="region">EMEA</Var>
        <Var name="report_date">2026-10-17</Var>
      </ContextVariables>
    </MailTask>
  </Tasks>
</MailConfiguration>
```

#### Key Elements
- **`<ReportSettings>`**: Defines configuration for the final summary status report.
  - `Recipient`: Email address receiving the report (required).
  - `Sender`: Sender email address for the report email (optional).
  - `SubjectPrefix`: Prefix added to the status report email subject (default: `[BulkMailer Report]`).
  - `IncludeFullErrorTrace`: Boolean flag (`true`/`false`) indicating whether full error details are included in the report.
- **`<MailTask>`**: Defines an individual email dispatch task.
  - Attributes: `id` (unique task identifier), `max_retries` (number of retry attempts on transient failure, default: `3`), `priority` (`high`/`normal`/`low`), `schedule_ref` (references a `Schedule` ID in `schedules.xml`).
  - `Sender`: Sender email address for this task.
  - `Recipients`: Contains lists of `<To>`, `<Cc>`, and `<Bcc>` recipient email addresses.
  - `Subject`: Subject line template for the email.
  - `BodyTemplate`: Jinja2 template filepath and `format` attribute (`html` or `text`).
  - `ContextVariables`: Key-value variables (`<Var name="...">value</Var>`) rendered within the email template.

### Work Schedules Configuration (`schedules.xml`)

The work schedules XML file defines schedule windows, timezones, rate limits, and concurrency limits.

#### Structure & Example
```xml
<?xml version="1.0" encoding="UTF-8"?>
<WorkSchedules timezone="Europe/Warsaw">
  <Schedule id="SCHED-MORNING" description="Morning operational window">
    <AllowedHours>
      <HourWindow start="06:00" end="12:00" max_concurrency="5" rate_limit_per_min="60"/>
    </AllowedHours>
  </Schedule>
</WorkSchedules>
```

#### Key Elements
- **`<WorkSchedules>`**: Root element with a `timezone` attribute (IANA timezone string, e.g., `Europe/Warsaw`, `UTC`).
- **`<Schedule>`**: Schedule rule group referenced by `schedule_ref` in tasks. Contains an `id` and optional `description`.
- **`<HourWindow>`**: Defines time execution window and throttling controls:
  - `start` / `end`: Local time window bounds in `HH:MM` or `HH:MM:SS` format.
  - `max_concurrency`: Maximum simultaneous emails sent concurrently within this window (default: `1`).
  - `rate_limit_per_min`: Maximum emails sent per minute (token bucket rate limiter, default: `60`).

### CLI Options and Commands

You can configure execution options and manage configurations when running the CLI tool:

#### Global Options
| Option | Short | Description |
| --- | --- | --- |
| `--db` | `-b` | Path to SQLite database file (default: `bulk_mailer.db` or `BULK_MAILER_DB`) |
| `--tasks-xml` | `-t` | Optional path to tasks configuration XML file to seed/upsert database |
| `--schedule-xml` | `-s` | Optional path to schedules configuration XML file to seed/upsert database |
| `--dry-run` | `-d` | Execute workflow without sending real network SMTP requests |
| `--verbose` | `-v` | Enable verbose debug logging |

#### Management Commands

- **`import-xml`**: Import tasks and schedule XML files into the SQLite database.
  - `--tasks-xml` / `-t`: Path to tasks XML file.
  - `--schedule-xml` / `-s`: Path to schedule XML file.
  - `--db` / `-b`: Path to SQLite database file.
  - `--mode` / `-m`: Import mode (`upsert` or `replace`, default: `upsert`).
- **`export-xml`**: Export tasks and schedule configurations from SQLite database to XML files.
  - `--tasks-xml` / `-t`: Target path for tasks XML output.
  - `--schedule-xml` / `-s`: Target path for schedules XML output.
  - `--db` / `-b`: Path to SQLite database file.

## Usage

### Installation
```bash
make install
```

### Importing XML Configuration into SQLite
```bash
bulk-mailer import-xml --tasks-xml config/samples/tasks.xml --schedule-xml config/samples/schedules.xml --db bulk_mailer.db
```

### Dry Run Execution
```bash
make run-dry
```

Or run directly via CLI:
```bash
bulk-mailer --tasks-xml config/samples/tasks.xml --schedule-xml config/samples/schedules.xml --dry-run
```

If the database is already seeded, you can run dispatch without specifying XML files:
```bash
bulk-mailer --db bulk_mailer.db --dry-run
```

### Exporting SQLite Database Configuration to XML
```bash
bulk-mailer export-xml --tasks-xml exported_tasks.xml --schedule-xml exported_schedules.xml --db bulk_mailer.db
```

### Running Tests and Quality Gates
```bash
make test
make quality-gate
```

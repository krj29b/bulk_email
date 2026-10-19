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

### CLI Options

You can configure execution options when running the CLI tool:

| Option | Short | Description |
| --- | --- | --- |
| `--tasks-xml` | `-t` | Path to tasks configuration XML file (Required) |
| `--schedule-xml` | `-s` | Path to schedules configuration XML file (Required) |
| `--dry-run` | `-d` | Execute workflow without sending real network SMTP requests |
| `--verbose` | `-v` | Enable verbose debug logging |

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

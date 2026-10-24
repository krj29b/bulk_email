# Bulk Mailer Engine

Production-grade, asynchronous bulk email dispatch and reporting engine built in **Python 3.12+**.

## Overview

`bulk-mailer` is a high-performance email dispatch engine that utilizes SQLite as its primary database backend for runtime configurations and execution history logging, while retaining full XML support for importing and exporting configuration definitions (`tasks.xml` and `schedules.xml`). It evaluates active schedule windows across timezones, dispatches scheduled email tasks concurrently with rate limiting and exponential backoff retry resilience, and sends a final Task Completion Status Report email upon completion.

---

## Key Features

- **Python 3.12+ Standards:** Built with strict type safety, `asyncio.TaskGroup`, `StrEnum`, `pydantic v2`, and `pydantic-xml`.
- **SQLite State Persistence:** SQLite runtime database storing tasks, schedules, report settings, and detailed execution logs with Write-Ahead Logging (`WAL`) mode and busy timeout handling (`30,000 ms`).
- **Safe XML Import & Export:** Built-in `defusedxml` protection against XXE and entity expansion attacks, supporting bidirectional conversion between XML documents and SQLite data models.
- **Timezone-Aware Throttling & Idempotency:** Hourly schedule windows with `zoneinfo` time zone awareness, midnight-spanning time calculation, window-level idempotency protection (`last_status == SUCCESS`), and token bucket rate limiting.
- **Async SMTP Dispatch & Retries:** High-concurrency SMTP dispatch with `aiosmtplib`, `asyncio.Semaphore`, connection pooling, exponential backoff retries on transient errors, and `--dry-run` simulation mode.
- **Jinja2 Templating:** Templated task emails with path traversal defense and auto-escaped context variables, alongside consolidated HTML/plain-text batch summary reports.

---

## Prerequisites & Installation

### Requirements
- **Python >= 3.12**
- **pip** package manager

### Installation Instructions

Clone the repository and install `bulk-mailer` along with its development dependencies:

```bash
# Install in editable mode with development dependencies
python3 -m pip install -e ".[dev]"
```

Or use the provided `Makefile`:

```bash
make install
```

---

## Configuration Reference

`bulk-mailer` is configured through environment variables (or a `.env` file) for SMTP server options and database location, alongside XML or database settings.

### Environment Variables (`Settings`)

Supported environment settings defined in `bulk_mailer.models.Settings`:

| Variable | Default | Description |
| --- | --- | --- |
| `SMTP_HOST` | `localhost` | Hostname or IP address of the SMTP server |
| `SMTP_PORT` | `1025` | Port number for the SMTP server |
| `SMTP_USER` | *None* | Username for SMTP authentication (optional) |
| `SMTP_PASSWORD` | *None* | Password for SMTP authentication (optional) |
| `SMTP_USE_TLS` | `false` | Enable direct TLS connection (`true`/`false`) |
| `SMTP_START_TLS` | `false` | Enable STARTTLS command upgrade (`true`/`false`) |
| `SMTP_TIMEOUT` | `30.0` | Timeout in seconds for SMTP operations |
| `BULK_MAILER_DB` | `bulk_mailer.db` | Path to SQLite database file |

---

## CLI Usage Guide (`bulk-mailer`)

The package provides the `bulk-mailer` CLI executable (as well as `python -m bulk_mailer.cli`).

### 1. Main Dispatch Command

Executes the main bulk mailer dispatch pipeline.

```bash
bulk-mailer [OPTIONS]
```

#### Flags & Options
| Option | Short | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--tasks-xml` | `-t` | `PATH` | *None* | Optional path to tasks XML file to seed/upsert database |
| `--schedule-xml` | `-s` | `PATH` | *None* | Optional path to schedule XML file to seed/upsert database |
| `--db` | `-b` | `PATH` | `bulk_mailer.db` | Path to SQLite database file (overrides `BULK_MAILER_DB`) |
| `--dry-run` | `-d` | `FLAG` | `false` | Execute workflow in simulation mode without sending network SMTP requests |
| `--verbose` | `-v` | `FLAG` | `false` | Enable verbose debug logging output |

#### Exit Codes
- **`0`**: Successful execution or no tasks were eligible for processing.
- **`1`**: Configuration or database error encountered (e.g. invalid file format, database connection failure).
- **`2`**: One or more tasks failed execution during the dispatch batch.

#### Example Dispatch Commands
```bash
# Execute dispatch and seed XML configurations if database is empty or needs updates
bulk-mailer --tasks-xml config/samples/tasks.xml --schedule-xml config/samples/schedules.xml

# Run dispatch in dry-run mode using an existing SQLite database
bulk-mailer --db bulk_mailer.db --dry-run --verbose
```

---

### 2. XML Import Command (`import-xml`)

Imports task definitions and schedule rules from XML configuration files into the SQLite database.

```bash
bulk-mailer import-xml [OPTIONS]
```

#### Options
| Option | Short | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--tasks-xml` | `-t` | `PATH` | *None* | Path to tasks configuration XML file |
| `--schedule-xml` | `-s` | `PATH` | *None* | Path to schedule configuration XML file |
| `--db` | `-b` | `PATH` | `bulk_mailer.db` | Target SQLite database file path |
| `--mode` | `-m` | `CHOICE` | `upsert` | Import mode: `upsert` (update/insert) or `replace` (clear and reload) |

#### Example
```bash
bulk-mailer import-xml --tasks-xml config/samples/tasks.xml --schedule-xml config/samples/schedules.xml --mode upsert
```

---

### 3. XML Export Command (`export-xml`)

Exports current task definitions, schedules, and report settings from the SQLite database back into XML files.

```bash
bulk-mailer export-xml [OPTIONS]
```

#### Options
| Option | Short | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--tasks-xml` | `-t` | `PATH` | *None* | Destination path for exported tasks XML |
| `--schedule-xml` | `-s` | `PATH` | *None* | Destination path for exported schedules XML |
| `--db` | `-b` | `PATH` | `bulk_mailer.db` | Source SQLite database file path |

#### Example
```bash
bulk-mailer export-xml --tasks-xml exported_tasks.xml --schedule-xml exported_schedules.xml
```

---

## Development & Quality Gates

The project maintains strict code quality standards enforced via `Makefile` commands:

```bash
# Run unit and integration test suite with coverage
make test

# Run code style and linting checks (Ruff & Mypy)
make lint

# Run dead code detection (Vulture)
make dead-code

# Run code complexity analysis (Radon)
make complexity

# Run dependency vulnerability audit (pip-audit)
make audit

# Run all quality gate checks in sequence
make quality-gate
```

---

## Architectural Deep Dive

For detailed technical specifications, database entity-relationship diagrams (ERD), scheduling algorithms, Mermaid state/sequence diagrams, and security mechanics, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

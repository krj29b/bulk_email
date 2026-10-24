import json
import sqlite3
from collections.abc import Generator
from contextlib import closing
from pathlib import Path
from typing import Any

import jinja2
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from bulk_mailer.database import get_connection, init_db
from bulk_mailer.mailer import TemplateRenderer
from bulk_mailer.models import (
    BodyTemplate,
    ContextVar,
    HourWindow,
    MailTask,
    Recipients,
    ReportSettings,
    Schedule,
    WorkSchedules,
)
from bulk_mailer.repository import DatabaseRepository

PACKAGE_TEMPLATES_DIR = Path(__file__).parent / "web_templates"
templates = Jinja2Templates(directory=str(PACKAGE_TEMPLATES_DIR))
router = APIRouter()


def get_repo(request: Request) -> Generator[DatabaseRepository, None, None]:
    db_path = getattr(request.app.state, "db_path", "bulk_mailer.db")
    with closing(get_connection(db_path)) as conn:
        init_db(conn)
        yield DatabaseRepository(conn)


def parse_email_list(raw_input: str) -> list[str]:
    if not raw_input:
        return []
    cleaned = raw_input.replace("\r\n", "\n").replace("\r", "\n")
    items = [item.strip() for line in cleaned.split("\n") for item in line.split(",")]
    return [item for item in items if item]


def parse_context_vars(raw_json: str) -> list[ContextVar]:
    if not raw_json or not raw_json.strip():
        return []
    data = json.loads(raw_json)
    if isinstance(data, list):
        return [ContextVar(name=item["name"], value=str(item["value"])) for item in data]
    if isinstance(data, dict):
        return [ContextVar(name=k, value=str(v)) for k, v in data.items()]
    return []


def parse_hour_windows(raw_json: str) -> list[HourWindow]:
    if not raw_json or not raw_json.strip():
        return []
    data = json.loads(raw_json)
    if isinstance(data, list):
        return [
            HourWindow(
                start=item["start"],
                end=item["end"],
                max_concurrency=int(item.get("max_concurrency", 1)),
                rate_limit_per_min=int(item.get("rate_limit_per_min", 60)),
            )
            for item in data
        ]
    return []


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    repo: DatabaseRepository = Depends(get_repo),
) -> Response:
    stats = repo.get_dashboard_stats()
    logs = repo.get_recent_execution_logs(limit=50)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"active_page": "dashboard", "stats": stats, "logs": logs},
    )


@router.get("/tasks", response_class=HTMLResponse)
def list_tasks(
    request: Request,
    repo: DatabaseRepository = Depends(get_repo),
) -> Response:
    tasks = repo.get_mail_tasks()
    schedules = repo.get_work_schedules().schedules
    return templates.TemplateResponse(
        request=request,
        name="tasks.html",
        context={"active_page": "tasks", "tasks": tasks, "schedules": schedules},
    )


def _build_task_from_form_dict(form_dict: dict[str, Any]) -> MailTask:
    task_id = str(form_dict.get("id", ""))
    schedule_ref = str(form_dict.get("schedule_ref", ""))
    sender = str(form_dict.get("sender", ""))
    priority = str(form_dict.get("priority", "normal"))
    max_retries = int(form_dict.get("max_retries", 3))
    subject = str(form_dict.get("subject", ""))
    body_format = str(form_dict.get("body_format", "html"))
    body_template_path = str(form_dict.get("body_template_path", ""))

    to_list = parse_email_list(str(form_dict.get("to", "")))
    cc_list = parse_email_list(str(form_dict.get("cc", "")))
    bcc_list = parse_email_list(str(form_dict.get("bcc", "")))
    context_vars = parse_context_vars(str(form_dict.get("context_variables", "")))

    return MailTask(
        id=task_id,
        max_retries=max_retries,
        priority=priority,
        schedule_ref=schedule_ref,
        sender=sender,
        recipients=Recipients(to=to_list, cc=cc_list, bcc=bcc_list),
        subject=subject,
        body_template=BodyTemplate(
            format=body_format,
            template_path=body_template_path,
        ),
        context_variables=context_vars,
    )


@router.post("/tasks", response_class=HTMLResponse)
async def save_task(
    request: Request,
    repo: DatabaseRepository = Depends(get_repo),
) -> Response:
    try:
        form_data = await request.form()
        form_dict = {k: v for k, v in form_data.items()}
        task = _build_task_from_form_dict(form_dict)
        repo.save_single_task(task)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Validation Error: {exc}",
        ) from exc

    tasks = repo.get_mail_tasks()
    schedules = repo.get_work_schedules().schedules
    return templates.TemplateResponse(
        request=request,
        name="tasks.html",
        context={
            "active_page": "tasks",
            "tasks": tasks,
            "schedules": schedules,
            "message": f"Task '{task.id}' saved successfully.",
        },
    )


@router.delete("/tasks/{task_id}")
def delete_task(
    task_id: str,
    repo: DatabaseRepository = Depends(get_repo),
) -> Response:
    deleted = repo.delete_mail_task(task_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found",
        )
    return HTMLResponse("")


@router.get("/tasks/{task_id}/preview")
def preview_task(
    task_id: str,
    request: Request,
    repo: DatabaseRepository = Depends(get_repo),
) -> Response:
    task = repo.get_mail_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found",
        )

    template_dir = getattr(request.app.state, "template_dir", ".")
    renderer = TemplateRenderer(template_dir=template_dir)

    try:
        rendered = renderer.render(
            task.body_template.template_path,
            task.get_context_dict(),
        )
    except (ValueError, jinja2.TemplateNotFound, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Template error: {exc}",
        ) from exc

    if task.body_template.format.lower() == "html":
        return HTMLResponse(content=rendered)
    return Response(content=rendered, media_type="text/plain")


@router.get("/schedules", response_class=HTMLResponse)
def list_schedules(
    request: Request,
    repo: DatabaseRepository = Depends(get_repo),
) -> Response:
    work_schedules = repo.get_work_schedules()
    return templates.TemplateResponse(
        request=request,
        name="schedules.html",
        context={"active_page": "schedules", "work_schedules": work_schedules},
    )


@router.post("/schedules", response_class=HTMLResponse)
async def save_schedule(
    request: Request,
    repo: DatabaseRepository = Depends(get_repo),
) -> Response:
    form = await request.form()
    schedule_id = str(form.get("id", ""))
    desc = form.get("description")
    description = str(desc) if desc is not None else None
    allowed_hours_json = str(form.get("allowed_hours_json", ""))

    try:
        allowed_hours = parse_hour_windows(allowed_hours_json)
        sched = Schedule(
            id=schedule_id,
            description=description,
            allowed_hours=allowed_hours,
        )
        repo.save_single_schedule(sched)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Validation Error: {exc}",
        ) from exc

    work_schedules = repo.get_work_schedules()
    return templates.TemplateResponse(
        request=request,
        name="schedules.html",
        context={
            "active_page": "schedules",
            "work_schedules": work_schedules,
            "message": f"Schedule '{schedule_id}' saved successfully.",
        },
    )


@router.post("/schedules/timezone", response_class=HTMLResponse)
async def update_timezone(
    request: Request,
    repo: DatabaseRepository = Depends(get_repo),
) -> Response:
    form = await request.form()
    tz_val = str(form.get("timezone", "UTC"))

    try:
        work_schedules = repo.get_work_schedules()
        updated_ws = WorkSchedules(timezone=tz_val, schedules=work_schedules.schedules)
        repo.save_work_schedules(updated_ws)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Validation Error: {exc}",
        ) from exc

    work_schedules = repo.get_work_schedules()
    return templates.TemplateResponse(
        request=request,
        name="schedules.html",
        context={
            "active_page": "schedules",
            "work_schedules": work_schedules,
            "message": f"Timezone updated to '{tz_val}'.",
        },
    )


@router.delete("/schedules/{schedule_id}")
def delete_schedule(
    schedule_id: str,
    repo: DatabaseRepository = Depends(get_repo),
) -> Response:
    try:
        deleted = repo.delete_schedule(schedule_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Schedule '{schedule_id}' not found",
            )
        return HTMLResponse("")
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete schedule '{schedule_id}': referenced by existing tasks.",
        ) from exc


@router.get("/settings", response_class=HTMLResponse)
def view_settings(
    request: Request,
    repo: DatabaseRepository = Depends(get_repo),
) -> Response:
    report_settings = repo.get_report_settings()
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={"active_page": "settings", "settings": report_settings},
    )


@router.post("/settings", response_class=HTMLResponse)
async def save_settings(
    request: Request,
    repo: DatabaseRepository = Depends(get_repo),
) -> Response:
    form = await request.form()
    recipient = str(form.get("recipient", ""))
    sender_raw = form.get("sender")
    sender = str(sender_raw) if sender_raw and str(sender_raw).strip() else None
    subject_prefix = str(form.get("subject_prefix", "[BulkMailer Report]"))
    include_full_error_trace = form.get("include_full_error_trace") in ("true", "1", "on", True)

    try:
        settings = ReportSettings(
            recipient=recipient,
            sender=sender,
            subject_prefix=subject_prefix,
            include_full_error_trace=include_full_error_trace,
        )
        repo.save_report_settings(settings)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Validation Error: {exc}",
        ) from exc

    report_settings = repo.get_report_settings()
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "active_page": "settings",
            "settings": report_settings,
            "message": "Report settings updated successfully.",
        },
    )


@router.get("/api/stats", response_class=JSONResponse)
def api_stats(
    repo: DatabaseRepository = Depends(get_repo),
) -> dict[str, Any]:
    return repo.get_dashboard_stats()


@router.get("/api/logs", response_class=JSONResponse)
def api_logs(
    limit: int = Query(50, ge=1, le=500),
    status_filter: str | None = Query(None, alias="status"),
    task_id_filter: str | None = Query(None, alias="task_id"),
    repo: DatabaseRepository = Depends(get_repo),
) -> list[dict[str, Any]]:
    return repo.get_recent_execution_logs(
        limit=limit,
        status_filter=status_filter,
        task_id_filter=task_id_filter,
    )


def create_app(
    db_path: str | Path = "bulk_mailer.db",
    template_dir: str | Path = ".",
) -> FastAPI:
    app = FastAPI(
        title="BulkMailer Admin Panel",
        description="Lightweight web administration and observability panel",
        version="0.1.0",
    )
    app.state.db_path = str(db_path)
    app.state.template_dir = str(template_dir)
    app.include_router(router)
    return app

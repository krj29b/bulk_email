from pathlib import Path
from typing import cast

import defusedxml.ElementTree as ET  # type: ignore[import-untyped]

from bulk_mailer.models import MailConfiguration, WorkSchedules


class XMLValidationError(Exception):
    """Raised when XML parsing or schema/cross-reference validation fails."""


def _parse_xml_safely(file_path: str | Path) -> bytes:
    path = Path(file_path)
    if not path.is_file():
        raise XMLValidationError(f"File not found: {path}")

    try:
        # Use defusedxml to safely parse the XML file and catch entity expansion or malformed XML
        tree = ET.parse(path)
        root = tree.getroot()
        # Convert root back to bytes for pydantic-xml parsing
        raw_bytes = ET.tostring(root, encoding="utf-8")
        return cast(bytes, raw_bytes)
    except Exception as exc:
        raise XMLValidationError(f"XML security/syntax error in {path}: {exc}") from exc


def load_mail_configuration(file_path: str | Path) -> MailConfiguration:
    xml_bytes = _parse_xml_safely(file_path)
    try:
        return MailConfiguration.from_xml(xml_bytes)
    except Exception as exc:
        msg = f"Invalid MailConfiguration XML schema in {file_path}: {exc}"
        raise XMLValidationError(msg) from exc


def load_work_schedules(file_path: str | Path) -> WorkSchedules:
    xml_bytes = _parse_xml_safely(file_path)
    try:
        return WorkSchedules.from_xml(xml_bytes)
    except Exception as exc:
        msg = f"Invalid WorkSchedules XML schema in {file_path}: {exc}"
        raise XMLValidationError(msg) from exc


def validate_xml_configs(
    mail_config: MailConfiguration, work_schedules: WorkSchedules
) -> None:
    schedule_ids = {s.id for s in work_schedules.schedules}
    missing_refs = set()

    for task in mail_config.tasks:
        if task.schedule_ref not in schedule_ids:
            missing_refs.add(f"Task '{task.id}' references unknown schedule '{task.schedule_ref}'")

    if missing_refs:
        raise XMLValidationError(
            "Cross-reference validation failed: " + "; ".join(sorted(missing_refs))
        )

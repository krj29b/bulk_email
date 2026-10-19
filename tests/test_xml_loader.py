from pathlib import Path

import pytest

from bulk_mailer.xml_loader import (
    XMLValidationError,
    _parse_xml_safely,
    load_mail_configuration,
    load_work_schedules,
    validate_xml_configs,
)


def test_load_sample_xml_files(tmp_path: Path) -> None:
    tasks_path = "config/samples/tasks.xml"
    schedules_path = "config/samples/schedules.xml"

    mail_config = load_mail_configuration(tasks_path)
    schedules = load_work_schedules(schedules_path)

    assert len(mail_config.tasks) == 2
    assert len(schedules.schedules) == 3

    # Validate cross references without errors
    validate_xml_configs(mail_config, schedules)

def test_missing_file() -> None:
    with pytest.raises(XMLValidationError, match="File not found"):
        load_mail_configuration("non_existent.xml")


def test_parse_xml_safely_missing_file() -> None:
    fake_path = "non_existent_file.xml"
    with pytest.raises(XMLValidationError, match=f"File not found: {fake_path}"):
        _parse_xml_safely(fake_path)

    fake_path_obj = Path("non_existent_path_obj.xml")
    with pytest.raises(XMLValidationError, match=f"File not found: {fake_path_obj}"):
        _parse_xml_safely(fake_path_obj)

def test_invalid_schedule_reference(tmp_path: Path) -> None:
    tasks_xml = tmp_path / "tasks.xml"
    schedules_xml = tmp_path / "schedules.xml"

    tasks_xml.write_bytes(b'''<?xml version="1.0" encoding="UTF-8"?>
<MailConfiguration>
  <ReportSettings>
    <Recipient>admin@example.com</Recipient>
  </ReportSettings>
  <Tasks>
    <MailTask id="TASK-001" schedule_ref="SCHED-UNKNOWN">
      <Sender>noreply@example.com</Sender>
      <Recipients><To>user@example.com</To></Recipients>
      <Subject>Test</Subject>
      <BodyTemplate format="html">tpl.j2</BodyTemplate>
    </MailTask>
  </Tasks>
</MailConfiguration>''')

    schedules_xml.write_bytes(b'''<?xml version="1.0" encoding="UTF-8"?>
<WorkSchedules timezone="UTC">
  <Schedule id="SCHED-KNOWN">
    <AllowedHours>
      <HourWindow start="00:00" end="23:59"/>
    </AllowedHours>
  </Schedule>
</WorkSchedules>''')

    mail_config = load_mail_configuration(tasks_xml)
    schedules = load_work_schedules(schedules_xml)

    with pytest.raises(XMLValidationError, match="references unknown schedule 'SCHED-UNKNOWN'"):
        validate_xml_configs(mail_config, schedules)

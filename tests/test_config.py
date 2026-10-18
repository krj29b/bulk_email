from unittest.mock import patch

import yaml
from config import Config


def test_config_yaml_error(caplog):
    cfg = Config()
    with patch("yaml.safe_load", side_effect=yaml.YAMLError("Invalid YAML")), caplog.at_level(
        "ERROR"
    ):
        cfg.init()

    assert cfg.config is None
    assert "Error loading YAML configuration: Invalid YAML" in caplog.text


def test_config_default_password(monkeypatch):
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("PASSWORD", raising=False)

    cfg = Config()
    cfg.init()

    assert cfg.config is not None
    assert cfg.config["password"] == ""


def test_config_password_from_smtp_password_env(monkeypatch):
    monkeypatch.setenv("SMTP_PASSWORD", "secret123")
    monkeypatch.delenv("PASSWORD", raising=False)

    cfg = Config()
    cfg.init()

    assert cfg.config is not None
    assert cfg.config["password"] == "secret123"


def test_config_password_from_password_env(monkeypatch):
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.setenv("PASSWORD", "fallback_secret")

    cfg = Config()
    cfg.init()

    assert cfg.config is not None
    assert cfg.config["password"] == "fallback_secret"

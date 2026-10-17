from config import Config


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

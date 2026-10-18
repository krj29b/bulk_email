from config import Config


def test_config_init_valid_yaml(tmp_path):
    config_file = tmp_path / "config.yml"
    config_file.write_text("host: localhost\nport: 587\npassword: mysecretpassword\n")

    cfg = Config()
    cfg.config_file = str(config_file)
    cfg.init()

    assert cfg.config is not None
    assert cfg.config["host"] == "localhost"
    assert cfg.config["port"] == 587
    assert cfg.config["password"] == "mysecretpassword"


def test_config_init_invalid_yaml(tmp_path, capsys):
    config_file = tmp_path / "config.yml"
    config_file.write_text("invalid_yaml: [unclosed_bracket")

    cfg = Config()
    cfg.config_file = str(config_file)
    cfg.init()

    assert cfg.config is None
    captured = capsys.readouterr()
    assert captured.out != ""


def test_config_init_empty_yaml(tmp_path):
    config_file = tmp_path / "config.yml"
    config_file.write_text("")

    cfg = Config()
    cfg.config_file = str(config_file)
    cfg.init()

    assert cfg.config is None


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


def test_config_password_precedence(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yml"
    config_file.write_text("password: yaml_pass\n")

    # Case 1: Both SMTP_PASSWORD and PASSWORD set -> SMTP_PASSWORD wins over PASSWORD and YAML
    monkeypatch.setenv("SMTP_PASSWORD", "smtp_pass")
    monkeypatch.setenv("PASSWORD", "env_pass")

    cfg = Config()
    cfg.config_file = str(config_file)
    cfg.init()
    assert cfg.config is not None
    assert cfg.config["password"] == "smtp_pass"

    # Case 2: Only PASSWORD set -> PASSWORD wins over YAML
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.setenv("PASSWORD", "env_pass")

    cfg = Config()
    cfg.config_file = str(config_file)
    cfg.init()
    assert cfg.config is not None
    assert cfg.config["password"] == "env_pass"

    # Case 3: Neither env set -> YAML password is used
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("PASSWORD", raising=False)

    cfg = Config()
    cfg.config_file = str(config_file)
    cfg.init()
    assert cfg.config is not None
    assert cfg.config["password"] == "yaml_pass"

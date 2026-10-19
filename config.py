import logging
import os
from typing import Any

import yaml  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class Config:
    config_file: str = 'config.yml'
    config: dict[str, Any] | None = None

    def init(self) -> None:
        try:
            with open(self.config_file, encoding="utf-8") as dcf:
                self.config = yaml.safe_load(dcf)
        except Exception as exc:
            print(f"Error loading YAML configuration: {exc}")
            logger.error(f"Error loading YAML configuration: {exc}")

        if self.config:
            yaml_password = self.config.get('password') or ''
            smtp_pass = os.getenv('SMTP_PASSWORD')
            pass_env = os.getenv('PASSWORD')
            if smtp_pass is not None:
                env_password = smtp_pass
            elif pass_env is not None:
                env_password = pass_env
            else:
                env_password = yaml_password
            self.config['password'] = env_password

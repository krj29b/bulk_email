from typing import Any

import yaml  # type: ignore[import-untyped]


class Config:
    config_file: str = 'config.yml'
    config: dict[str, Any] | None = None

    def init(self) -> None:
        with open(self.config_file) as dcf:
            try:
                self.config = yaml.safe_load(dcf)
            except yaml.YAMLError as exc:
                print(exc)

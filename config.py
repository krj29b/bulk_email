import os

import yaml


class Config:
    config_file = 'config.yml'
    config = None

    def init(self):
        with open(self.config_file) as dcf:
            try:
                self.config = yaml.safe_load(dcf)
            except yaml.YAMLError as exc:
                print(exc)

        if self.config:
            yaml_password = self.config.get('password') or ''
            env_password = os.getenv('SMTP_PASSWORD') or os.getenv('PASSWORD')
            self.config['password'] = env_password if env_password is not None else yaml_password

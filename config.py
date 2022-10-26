import yaml


class Config:
    config_file = 'config.yml'
    config = None

    def init(self):
        with open(self.config_file, 'r') as dcf:
            try:
                self.config = yaml.safe_load(dcf)
            except yaml.YAMLError as exc:
                print(exc)

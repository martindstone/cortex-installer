from ruamel.yaml import YAML, RoundTripLoader, RoundTripDumper
import shutil
import os
import datetime

class Values:
    def __init__(self):
        self.values_templates = {
            "demo": {
                "app": {
                    "springProfilesActive": "dev",
                    "service": {
                        "type": "NodePort",
                    },
                    "hostnames": {
                        "backend": "backend.demo.local",
                        "frontend": "frontend.demo.local",
                    },
                    "backend": {
                        "replicaCount": 1,
                    },
                    "worker": {
                        "replicaCount": 1,
                    },
                }
            }
        }

    def get_values_template(self, template_name):
        return self.values_templates.get(template_name, {})

    def edit_values_yaml(self, values_path, *updates):
        def walk_update(values, update):
            for key, value in update.items():
                if isinstance(value, dict):
                    if key in values:
                        walk_update(values[key], value)
                    else:
                        values[key] = value
                elif isinstance(value, list):
                    # TODO: implement list update properly when lists of lists or dicts are involved
                    values[key] = value
                else:
                    values[key] = value
            return values

        if not updates:
            raise ValueError("At least one values update is required")
        if not os.path.exists(values_path):
            raise FileNotFoundError(f"Values file not found: {values_path}")
        if not os.access(values_path, os.R_OK | os.W_OK):
            raise PermissionError(f"Cannot read/write file: {values_path}")
        yaml = YAML()
        with open(values_path, 'r') as f:
            values = yaml.load(f)
        backup_path = values_path + datetime.datetime.now().strftime(".%Y%m%d%H%M%S.bak")
        with open(backup_path, 'w') as f:
            yaml.dump(values, f)
        for update in updates:
            # walk the values dict and update the values
            values = walk_update(values, update)

        with open(values_path, 'w') as f:
            yaml.dump(values, f)
        return backup_path
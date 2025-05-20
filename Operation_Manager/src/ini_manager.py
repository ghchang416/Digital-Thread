import configparser
import os
import json

class Settings:
    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        setting_path = os.path.join(base_dir, "Setting", "setting.ini")
        self.config = configparser.ConfigParser()
        self.config.read(setting_path, encoding="utf-8")

    def get(self, section, key):
        return self.config.get(section, key)

class Projects:
    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        setting_path = os.path.join(base_dir, "..", "Projects", "projects.ini")
        with open(setting_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def get_project_by_index(self, index: int) -> dict:
        return self.data["Projects"][index]
    
    def __len__(self):
        return int(self.data["Count"])


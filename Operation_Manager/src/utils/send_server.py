import requests
from ini_manager import Settings
from datetime import datetime, timezone

settings = Settings()

def time_to_timestamp():
    dt = datetime.now(timezone.utc)
    return str(int(dt.timestamp() * 1000000))

def send_material_id(endpoint_type, material_id):
    url = settings.get("API", "material") + endpoint_type
    payload = {
        "equipmentInfo": {
            "site": "korea",
            "company": "kitech",
            "eq": "kitechpc",
            "operation": "",
            "unit": "",
            "module": ""
        },
        "time": time_to_timestamp(),
        "materialIds": [material_id]
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"[ERROR] Failed to send material ID: {e}")

def send_recipe_id(endpoint_type, material_id, recipe_id):
    url = settings.get("API", "recipe") + endpoint_type
    payload = {
        "equipmentInfo": {
            "site": "korea",
            "company": "kitech",
            "eq": "kitechpc",
            "operation": "",
            "unit": "",
            "module": ""
        },
        "time": time_to_timestamp(),
        "materialIds": [material_id],
        "recipeId": recipe_id
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"[ERROR] Failed to send recipe ID: {e}")
import os
import json
from datetime import datetime
from dlls import Torus
from ini_manager import Settings

settings = Settings()

def add_product(project_id, uuid, upload_data_names, uuid_index):
    product_path = os.path.join(settings.get("PATH", "project_root"), project_id, "Products", "products.json")
    if os.path.exists(product_path):
        with open(product_path, "r", encoding="utf-8") as f:
            products = json.load(f)
    else:
        products = {"Products": []}

    products_list = products.get("Products", [])

    if uuid_index == 0:
        product_id = len(products_list) + 1
        product_folder = os.path.join(settings.get("PATH", "project_root"), project_id, "Products", str(product_id))
        os.makedirs(os.path.join(product_folder, "GDNT"), exist_ok=True)
        upload_data = {"MainPG": upload_data_names[0]}
        for i, data in enumerate(upload_data_names[1:], 1):
            upload_data[f"PG{i}"] = data

        new_product = {
            "UUID": uuid,
            "PATH": product_folder,
            "PRODUCT_ID": product_id,
            "START_TIME": datetime.now().isoformat(),
            "UpLoadData": upload_data
        }
        products_list.append(new_product)
    else:
        products_list[-1][f"UUID{uuid_index}"] = uuid

    with open(product_path, "w", encoding="utf-8") as f:
        json.dump({"Products": products_list}, f, indent=2)

    return

def update_product_finish_time(project_id, product_id):
    product_path = os.path.join(settings.get("PATH", "project_root"), project_id, "Products", "products.json")
    with open(product_path, "r", encoding="utf-8") as f:
        products = json.load(f)
    if products["Products"]:
        products["Products"][-1]["FINISH_TIME"] = datetime.now().isoformat()
    with open(product_path, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2)
    
    # run_inspection(settings.get("PATH", "project_root"), project_id, product_id)

def get_toolpath_count(project_id):
    cam_dir = os.path.join(settings.get("PATH", "project_root"), project_id, "CAM")
    try:
        json_file = next((f for f in os.listdir(cam_dir) if f.endswith(".json")), None)
        if not json_file:
            return 0
        with open(os.path.join(cam_dir, json_file), "r", encoding="utf-8") as f:
            data = json.load(f)
        return len(data.get("values", []))
    except Exception as e:
        print(f"[ERROR] get_toolpath_count: {e}")
        return 0

def add_upload_toolpath_data(start_no, cnt):
    return [f"{start_no + i:04d}" for i in range(cnt + 1)]

def load_operation_names(project_id):
    settings = Settings()
    cam_path = os.path.join(settings.get("PATH", "project_root"), project_id, "CAM")
    json_file = next((f for f in os.listdir(cam_path) if f.endswith(".json")), None)
    if not json_file:
        raise FileNotFoundError("No CAM JSON file found")
    with open(os.path.join(cam_path, json_file), "r", encoding="utf-8") as f:
        data = json.load(f)
    return [v["Operation Information"]["Operation Name"] for v in data["values"]]

def upload_all_operations(project_id, start_no, torus: Torus):
    settings = Settings()
    cam_path = os.path.join(settings.get("PATH", "project_root"), project_id, "CAM")
    operation_names = load_operation_names(project_id)
    for i, op_name in enumerate(operation_names):
        target_file = next((f for f in os.listdir(cam_path) if f.startswith(op_name)), None)
        if not target_file:
            raise FileNotFoundError(f"No file starting with {op_name}")
        target_path = os.path.join(cam_path, target_file)
        o_name = f"O{start_no + i:04d}"
        torus.upload(target_path, o_name)

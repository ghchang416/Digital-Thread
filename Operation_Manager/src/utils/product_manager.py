import asyncio
from send_server import send_material_id, send_recipe_id
from product_utils import add_product
from dlls import Torus
from utils import generate_uuid
import os
from ini_manager import Settings

settings = Settings()

def create_main_program(start_no, cnt, project_id, torus: Torus):
    name = f"O{start_no:04d}"
    path = os.path.join(settings.get("PATH", "project_root"), project_id, name)
    lines = ["%", name]
    for i in range(cnt + 1):
        lines.append(f"M98P{start_no + i + 1}")
    lines.append("M30\n%")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    torus.upload(path, name)
    return

async def monitor_cnc(parent_torus: Torus, project_id, toolpath_count, upload_data):
    mode = 0
    pname = ""
    uuid_index = 0

    product_uuid = generate_uuid()
    recipe_uuid = ""

    while True:
        status = parent_torus.get_status()
        current_program = parent_torus.get_program_name()

        if status == 1 and mode != 3:
            mode = 3
            send_material_id("start", product_uuid)
            add_product(project_id, product_uuid, upload_data, uuid_index)
            uuid_index += 1

        if current_program != pname and mode == 3:
            if recipe_uuid:
                send_recipe_id("finish", product_uuid, recipe_uuid)

            recipe_uuid = generate_uuid()
            send_recipe_id("start", product_uuid, recipe_uuid)
            add_product(project_id, recipe_uuid, upload_data, uuid_index)
            uuid_index += 1
            pname = current_program

        if status != 1 and mode == 3:
            send_recipe_id("finish", product_uuid, recipe_uuid)
            send_material_id("finish", product_uuid)
            break

        await asyncio.sleep(1)
    return product_uuid

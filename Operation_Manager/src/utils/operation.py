import asyncio
import os
from product_utils import get_toolpath_count, add_upload_toolpath_data, update_product_finish_time, upload_all_operations
from product_manager import create_main_program
from product_manager import monitor_cnc
from product_utils import update_product_finish_time
from utils import write_log
from dlls import Torus
    
async def main():
    project_id = "P188164"
    project_name = "4path"
    # vm_result_path = json_path + "\\VM\\" + name + "\\" + name + "\\result" 에 사용
    start_no = 0
    torus = Torus()

    toolpath_count = get_toolpath_count(project_id)

    # main program 생성 및 업로드
    create_main_program(start_no, toolpath_count, project_id, torus)
    upload_data_names = add_upload_toolpath_data(start_no, toolpath_count)

    # # 각 operation 별 파일 업로드
    upload_all_operations(project_id, start_no + 1, torus)
    write_log("UPLOAD COMPLETE")

    write_log("BACKGROUND WORKER RUN")
    product_id = await monitor_cnc(torus, project_id, toolpath_count, upload_data_names)

    write_log("PRODUCT CUTTING FINISH")
    update_product_finish_time(project_id, product_id)

if __name__ == "__main__":
    asyncio.run(main())
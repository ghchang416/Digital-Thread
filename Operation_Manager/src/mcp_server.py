from fastmcp import FastMCP
from src.services import get_machine_service, get_project_service
mcp = FastMCP(name="machine_service")

async def setup_tools():
    project_service = await get_project_service()
    machine_service = await get_machine_service()

    mcp.tool(machine_service.get_machine_list)
    mcp.tool(machine_service.upload_torus_file)
    mcp.tool(machine_service.get_machine_status)

    mcp.tool(project_service.get_project_list)
    mcp.tool(project_service.extract_workplan_and_nc)
    mcp.tool(project_service.get_nc_code)
    mcp.tool(project_service.update_nc_code)
    mcp.tool(project_service.get_product_logs_by_project_id)
    mcp.tool(project_service.get_machine_status_info)
    
import asyncio
asyncio.run(setup_tools()) 

mcp.run(transport="sse", port=8050, host="0.0.0.0")
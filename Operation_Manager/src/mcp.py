from fastmcp import FastMCP
from src.services.machine import MachineService

mcp = FastMCP(name="machine_service")
service = MachineService()
mcp.add_tool(service.get_machine_list, name="get_machine_list", description="...")
mcp.run()

from fastmcp import FastMCP
from src.services import get_file_service

mcp = FastMCP(name="machine_service")

async def setup_tools():
    service = await get_file_service()
    mcp.tool(service.get_machine_list)
    
import asyncio
asyncio.run(setup_tools()) 

mcp.run()

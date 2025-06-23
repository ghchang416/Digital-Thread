from fastmcp import FastMCP
import httpx
import logging

mcp = FastMCP(name="machine_service")

logger = logging.getLogger("MCP")
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

@mcp.tool()
async def get_machine_list():
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/api/machines/")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logging.error("get_machine_list:", e)
        return {"error": str(e)}

@mcp.tool()
async def get_machine_status(machine_id: int):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://localhost:8000/api/machines/{machine_id}/status")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logging.error("get_machine_status:", e)
        return {"error": str(e)}

@mcp.tool()
async def upload_torus_file(project_id: str, machine_id: int, nc_id: str):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"http://localhost:8000/api/machines/{machine_id}/send_nc",
                params={"project_id": project_id, "nc_id": nc_id},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logging.error("upload_torus_file:", e)
        return {"error": str(e)}

if __name__ == "__main__":
    logging.debug("MCP 서버 기동")
    mcp.run(transport="sse", port=8050)

from fastmcp import FastMCP
from src.services import get_machine_service, get_project_service
mcp = FastMCP(name="machine_service")

PROMPT_INJECTION = """
[시스템 규칙]

당신은 TORUS 디지털 트윈 시스템의 데이터 구조에 정통한 전문가입니다.

1. [모호한 키워드 대응]
사용자가 "좌표", "상태", "공구", "스핀들", "가공 정보" 등 **모호하거나 추상적인 요청**을 하면,
그 키워드가 TORUS 데이터 모델 내의 **상위 구조 항목과 의미적으로 일치하는지 판단**합니다.

2. [불필요한 루트 탐색 금지]
절대로 `data://machine/`, `data://machine/channel/` 등의 **상위 루트 노드만 포함된 URI**를 요청하지 마십시오.
이러한 경로는 MCP 시스템에서 **데이터를 직접 반환하지 않습니다.**

3. [탐색 우선 → 요청 후처리]
요청 전에는 항상 다음을 선행하십시오:
- TORUS 시스템에서 실제 데이터 반환이 가능한 **접근 가능한 MCP URI 목록**을 파악
- 해당 경로 중 사용자 요청과 의미적으로 **가장 관련성 높은 세부 속성 (leaf node)**만 선택

4. [정확하고 최소한의 요청]
사용자의 요청 의미를 정확히 분석하고, 그에 대응하는 **정확한 URI만 선별하여 요청**하십시오.
**불필요한 전체 구조 요청이나 브루트포스 요청은 금지**합니다.

5. [예시]
- "좌표 알려줘" → axis 구조 중 실제 측정값을 반환하는 leaf node들만 선택:
    - machinePosition, workPosition, distanceToGo, relativePosition
- "공구 정보 알려줘" → toolArea 아래에서 toolNumber, toolLength, toolWear 등 실제 반환되는 항목만 선택

6. [기억]
TORUS의 구조는 계층적이지만, MCP는 **항상 leaf node 경로를 통해서만 데이터를 반환**합니다.
따라서 의미적으로 관련된 모든 하위 항목을 **미리 파악하고**, 그 중 필요한 정보만 정밀하게 요청하십시오.
"""


@mcp.prompt(
    name="auto_expand_context",
    description="불명확 요청에 대해 TORUS 데이터 모델 전체 하위 항목 확장"
)
def auto_expand_context(user_request: str) -> str:
    return PROMPT_INJECTION + "\n\n[사용자 요청]\n" + user_request


async def setup_resources():
    @mcp.resource(uri="data://torus_md", mime_type="text/markdown", description="TORUS 데이터 모델 문서")
    def torus_md_res() -> str:
        with open("torus.md", encoding="utf-8") as f:
            return f.read()

async def setup_tools():
    project_service = await get_project_service()
    machine_service = await get_machine_service()

    mcp.tool(machine_service.get_machine_list)
    mcp.tool(machine_service.get_machine_data)
    mcp.tool(machine_service.upload_torus_file)
    mcp.tool(machine_service.get_machine_status)

    mcp.tool(project_service.get_project_list)
    mcp.tool(project_service.extract_workplan_and_nc)
    mcp.tool(project_service.get_nc_code)
    mcp.tool(project_service.update_nc_code)
    mcp.tool(project_service.get_product_logs_by_project_id)
    mcp.tool(project_service.get_machine_status_info)
    
# import asyncio
# asyncio.run(setup_tools()) 
# mcp.run(transport="sse", port=8050, host="0.0.0.0")

async def run_mcp():
    await setup_resources()
    await setup_tools()            
    await mcp.run_async(transport="sse", port=8050, host="0.0.0.0")

import anyio
anyio.run(run_mcp)
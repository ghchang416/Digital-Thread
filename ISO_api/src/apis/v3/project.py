from typing import Optional, Dict, List, Any
import logging
import xmltodict
from fastapi import (
    APIRouter,
    Depends,
    File,
    Path,
    Query,
    Response,
    UploadFile,
    HTTPException,
    Form,
)
from src.services import (
    FileService,
    V3ProjectService,
    get_file_service,
    get_v3_project_service,
    AssetService,
    get_asset_service,
)
from src.schemas.asset import (
    AssetCreateResponse,
    AssetListResponse,
    AssetDocument,
    AttachRefResponse,
    AssetCreateRequest,
)
from src.utils.nc_spliter import extract_tool_sequence
from src.utils.v3_xml_parser import (
    extract_dtfile_oid,
    append_ws_into_project_xml,
    create_feature_xml_temp,
    count_workingsteps_in_workplan_xml,
    validate_xml_against_schema,
    inject_cutting_tool_ref,
    get_nested_value,
)
from src.utils.exceptions import CustomException, ExceptionEnum
from src.utils.file_modifier import read_json_file
from src.utils.cam_common import (
    invert_cam14649_to_cam13399,
    extract_13399_values_from_cam,
    build_cutting_tool_13399_dtasset_xml,
    ensure_dummy_secplane,
    ensure_dummy_feature,
    derive_tool_display_name_from_mapping,
    force_dummy_its_tool,
    ensure_milling_technology,
    ensure_milling_machine_functions,
    find_cam_key_for_coolant,
    ensure_strategy_with_pathmode,
    reorder_operation_children,
    normalize_dt_project_structure,
)
from src.utils.cam_nx_adapter import pick_nx_ops
from src.utils.cam_powermill_adapter import (
    pick_powermill_ops,
    reorder_powermill_files_by_order,
)
import requests
from src.config import settings

router = APIRouter(prefix="/api/v3/projects", tags=["Project Management(v3)"])

log = logging.getLogger(__name__)


@router.post(
    "",
    status_code=201,
    response_model=AssetCreateResponse,
    summary="프로젝트 업로드",
)
async def upload_project(
    project_xml_file: UploadFile = File(..., description="업로드할 프로젝트 XML 파일"),
    project_service: V3ProjectService = Depends(get_v3_project_service),
):
    """
    프로젝트 XML 파일을 업로드하는 API입니다.

    - 업로드된 XML 파일을 파싱하여 프로젝트를 생성합니다.
    - 프로젝트는 데이터베이스에 저장됩니다.
    - **반환값**: 생성된 프로젝트의 정보
    """
    xml_content = await project_xml_file.read()
    xml_string = xml_content.decode("utf-8")

    # 1) 중복 키 선검사 (race 대응을 위해 DB 유니크 인덱스는 필수)
    try:
        # exists_by_keys 가 True/False 반환하도록 해두면:
        dup = await project_service.exists_by_keys(xml_string=xml_string)
        if dup:
            raise CustomException(ExceptionEnum.ASSET_ID_DUPLICATION)
        # 만약 내부에서 raise 하는 버전이라면 위 두 줄 대신 try/except로 잡으면 됨.
    except CustomException as ce:
        if ce.enum == ExceptionEnum.ASSET_ID_DUPLICATION:
            raise CustomException(ExceptionEnum.ASSET_ID_DUPLICATION)
        raise

    return await project_service.create_from_xml(xml_string)


@router.get("", response_model=AssetListResponse, summary="프로젝트 목록 조회")
async def get_project_list(
    global_asset_id: str = Query(..., description="조회할 프로젝트의 글로벌 에셋 Id"),
    asset_id: str = Query(None, description="조회할 프로젝트의 에셋 Id"),
    project_service: V3ProjectService = Depends(get_v3_project_service),
):
    """
    프로젝트 목록을 조회하는 API입니다.

    - 저장된 프로젝트의 document를 반환합니다.
    - **반환값**: 프로젝트 도큐먼트 리스트
    """
    return await project_service.list_projects(
        global_asset_id=global_asset_id,
        asset_id=asset_id,
    )


@router.post(
    "/add-ref",
    response_model=AttachRefResponse,
    summary="프로젝트에 에셋 참조(URI) 붙이기",
)
async def attach_project_ref(
    # 프로젝트 키
    global_asset_id: str = Query(..., description="프로젝트 global_asset_id"),
    asset_id: str = Query(..., description="프로젝트 asset_id"),
    project_element_id: str = Query(
        ..., description="프로젝트의 dt_project element_id"
    ),
    # 참조 대상 키
    ref_global_asset_id: str = Query(..., description="참조 대상 global_asset_id"),
    ref_asset_id: str = Query(..., description="참조 대상 asset_id"),
    ref_element_id: str = Query(..., description="참조 대상 element_id"),
    # 타입/카테고리 힌트
    ref_type: str = Query(
        ...,
        description="참조 대상 type (예: dt_machine_tool / dt_material / dt_cutting_tool_13399 / dt_file)",
    ),
    ref_category: str | None = Query(
        None, description="참조 대상 category (파일계열: NC/VM/TDMS 등)"
    ),
    # 위치 파라미터(필요 시)
    workplan_id: str | None = Query(
        None, description="workplan its_id (머신툴/파일/커팅툴에 필요)"
    ),
    workpiece_id: str | None = Query(
        None, description="workpiece its_id (머티리얼에 필요)"
    ),
    workingstep_id: str | None = Query(
        None, description="workingstep its_id (커팅툴에 필요)"
    ),
    project_service: V3ProjectService = Depends(get_v3_project_service),
):
    """
    - 앵커(작업계획/워크피스/오퍼레이션)는 **이미 존재해야** 하며, 없으면 추가/생성하지 않고 에러 반환
    - 파일 계열(dt_file: NC/VM/TDMS)은 중복 URI 방지 append
    - 그 외(머신툴/머티리얼/커팅툴)는 덮어쓰기
    """
    try:
        result = await project_service.attach_ref(
            global_asset_id=global_asset_id,
            asset_id=asset_id,
            project_element_id=project_element_id,
            ref_global_asset_id=ref_global_asset_id,
            ref_asset_id=ref_asset_id,
            ref_element_id=ref_element_id,
            ref_type=ref_type,
            ref_category=ref_category,
            workplan_id=workplan_id,
            workpiece_id=workpiece_id,
            workingstep_id=workingstep_id,
        )
        return AttachRefResponse(**result)
    except CustomException as ce:
        raise HTTPException(status_code=ce.status_code, detail=ce.detail)


@router.put("/delete-ref", summary="프로젝트에서 참조 삭제")
async def remove_ref(
    global_asset_id: str = Query(..., description="프로젝트의 global_asset_id"),
    asset_id: str = Query(..., description="프로젝트의 asset_id"),
    project_element_id: str = Query(..., description="프로젝트 dt_project element_id"),
    ref_global_asset_id: str = Query(
        ..., description="삭제 대상 참조의 global_asset_id"
    ),
    ref_asset_id: str = Query(..., description="삭제 대상 참조의 asset_id"),
    ref_element_id: str = Query(..., description="삭제 대상 참조의 element_id"),
    ref_type: str = Query(
        ..., description="참조 타입 (예: dt_machine_tool, dt_file 등)"
    ),
    ref_category: Optional[str] = Query(
        None, description="파일 계열이면 NC/VM/TDMS 등"
    ),
    workplan_id: Optional[str] = Query(None, description="workplan 앵커에 필요"),
    workpiece_id: Optional[str] = Query(None, description="workpiece 앵커에 필요"),
    workingstep_id: Optional[str] = Query(None, description="operation 앵커에 필요"),
    project_service: V3ProjectService = Depends(get_v3_project_service),
):
    return await project_service.remove_ref(
        global_asset_id=global_asset_id,
        asset_id=asset_id,
        project_element_id=project_element_id,
        ref_global_asset_id=ref_global_asset_id,
        ref_asset_id=ref_asset_id,
        ref_element_id=ref_element_id,
        ref_type=ref_type,
        ref_category=ref_category,
        workplan_id=workplan_id,
        workpiece_id=workpiece_id,
        workingstep_id=workingstep_id,
    )


@router.post(
    "/cam-json",
    summary="(NX/PowerMill) NC의 T시퀀스에 맞춰 CAM JSON + 매핑으로 Tool/Workingstep 생성 → Workplan에 추가",
)
async def apply_cam_into_workplan(
    global_asset_id: str = Query(...),
    asset_id: str = Query(...),
    project_element_id: str = Query(..., alias="element_id"),
    workplan_id: str = Query(...),
    cam_type: str = Form(..., description="'nx' 또는 'powermill'"),
    # PowerMill은 여러 파일, NX는 보통 1개(여러 op)
    cam_files: List[UploadFile] = File(...),
    mapping_file: UploadFile = File(...),
    # PowerMill 전용: 파일 처리 순서(필수). NX는 무시됨.
    ops_order: str | None = Form(
        None, description="PowerMill 전용: 처리 순서(콤마/JSON 배열). NX는 불필요."
    ),
    asset_service: AssetService = Depends(get_asset_service),
    file_service: FileService = Depends(get_file_service),
    project_service: V3ProjectService = Depends(get_v3_project_service),
) -> Dict[str, Any]:
    """
    흐름
    0) NC dt_file 1개를 프로젝트/워크플랜 기준으로 찾아서 T시퀀스 추출
    1) CAM 파일 순서 확정(NX: 단일파일, PowerMill: ops_order 필수) 후 op 리스트 구성
    2) CAM→14649 매핑 로드 + 14649→13399 합성 테이블 준비
    3) 프로젝트 XML 로딩(원본 보관) + 정책: 기존 워킹스텝 있으면 차단
    4) 메모리에서 전부 생성:
       - (중복 T 재사용) 각 T에 대해 13399 tool XML 생성(필요 시) + WS XML/DICT 생성
         - its_tool 스텁 + ref_dt_cutting_tool 주입
         - its_secplane 더미 보강
    5) 스키마 선검증 (툴XML들 + 최종 프로젝트XML)
    6) 실제 쓰기(툴 → 프로젝트). DB 오류 시 보상 롤백
    """
    # --- 0) NC 참조 검증 + T 시퀀스 ---
    g_url = project_service.normalize_global_asset_id(global_asset_id)

    rows = await asset_service.find_nc_files_by_project_ref(
        global_asset_id=g_url,
        asset_id=asset_id,
        project_element_id=project_element_id,
        workplan_id=workplan_id,
        validate_project_exists=True,
    )
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No NC file referencing project={project_element_id}, wp={workplan_id}",
        )
    if len(rows) > 1:
        raise HTTPException(
            status_code=409,
            detail="Multiple NC files reference the same project/workplan",
        )

    nc_doc = rows[0]
    nc_asset = await asset_service.repo.get_asset_by_mongo_id(str(nc_doc["_id"]))
    if not nc_asset or not isinstance(nc_asset.get("data"), str):
        raise HTTPException(status_code=500, detail="NC asset XML not found")

    nc_oid = extract_dtfile_oid(
        nc_asset["data"], target_element_id=nc_doc.get("element_id")
    )
    if not nc_oid:
        raise HTTPException(
            status_code=422, detail="NC file OID not found in asset XML"
        )

    nc_text = await file_service.get_file_text(nc_oid)
    tool_seq = extract_tool_sequence(nc_text)  # ["T2","T3","T1","T2", ...]
    if not tool_seq:
        return {"message": "No tool change sequence detected from NC", "applied": 0}

    # --- 1) CAM 파일 순서 확정 & op 추출 ---
    all_ops: List[Dict[str, Any]] = []
    ordered_names: List[str] = []

    ct = cam_type.lower().strip()
    if ct == "nx":
        if len(cam_files) != 1:
            raise HTTPException(
                status_code=422, detail="NX expects exactly one CAM JSON file."
            )
        cam_json = await read_json_file(cam_files[0])
        all_ops = pick_nx_ops("nx", cam_json)  # 한 파일 안에 여러 op
        ordered_names = [cam_files[0].filename or ""]
    elif ct in ("powermill", "pmill", "power_mill"):
        if not ops_order:
            raise HTTPException(
                status_code=422, detail="ops_order is required for powermill."
            )
        # 파일을 ops_order 순서로 재정렬
        cam_files = reorder_powermill_files_by_order(cam_files, ops_order)
        for f in cam_files:
            j = await read_json_file(f)
            ops = pick_powermill_ops(j) or []
            if not ops:
                raise HTTPException(
                    status_code=422, detail=f"No operation found in file: {f.filename}"
                )
            if len(ops) != 1:
                raise HTTPException(
                    status_code=422,
                    detail=f"Expected exactly 1 operation per PowerMill file: {f.filename}",
                )
            all_ops.extend(ops)
            ordered_names.append(f.filename or "")
    else:
        raise HTTPException(status_code=422, detail=f"Unsupported cam_type: {cam_type}")

    # 길이 일치 검사
    if len(all_ops) != len(tool_seq):
        raise HTTPException(
            status_code=422,
            detail=f"NC tool sequence length ({len(tool_seq)}) != CAM op count ({len(all_ops)}).",
        )

    # --- 2) 매핑 준비 (CAM→14649 → 13399) ---
    cam_to_14649_map: Dict[str, str] = await read_json_file(mapping_file)
    cam_to_13399_map: Dict[str, str] = invert_cam14649_to_cam13399(cam_to_14649_map)

    # --- 3) 프로젝트 XML 로딩 (복구용 보관) ---
    proj_doc = await asset_service.repo.get_asset_by_keys(
        global_asset_id=g_url,
        asset_id=asset_id,
        type="dt_project",
        element_id=project_element_id,
    )
    if not proj_doc or not isinstance(proj_doc.get("data"), str):
        raise HTTPException(status_code=404, detail="Project asset XML not found")
    original_project_xml: str = proj_doc["data"]
    working_project_xml: str = original_project_xml

    # 정책: 기존 워킹스텝이 있으면 차단 (추가/수정은 별도 API)
    existing_ws_count = count_workingsteps_in_workplan_xml(
        original_project_xml, project_element_id, workplan_id
    )
    if existing_ws_count > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Workplan already contains workingsteps; creation is blocked by policy.",
                "workplan_id": workplan_id,
                "existing_workingsteps": existing_ws_count,
            },
        )

    # --- 4) 메모리에서 전부 생성 (툴 캐시 + ws dict) ---
    tool_asset_id = f"{asset_id}_cutting_tool"
    tool_cache: Dict[str, str] = {}  # "T1" -> "tool_0001"
    tool_xmls_to_write: Dict[str, str] = {}  # elem_id -> XML
    ws_nodes_to_append: List[Dict[str, Any]] = []

    for idx, tool_tag in enumerate(tool_seq):
        cam_op = all_ops[idx]

        # 4-A) cutting tool(13399) 생성/재사용
        elem_id = tool_cache.get(tool_tag)
        if not elem_id:
            # ✅ element_id 는 'T번호' 그대로 사용
            #    (tool_tag가 'T1','T2' 형태이므로 그대로 element_id로 채택)
            elem_id = tool_tag.strip() or f"T{idx+1}"

            # ✅ display_name 은 매핑에서 추출한 ToolType(=MachiningTool.its_id) 값 사용, 없으면 tool_tag
            display = derive_tool_display_name_from_mapping(
                cam_op=cam_op,
                cam_to_14649_map=cam_to_14649_map,
                fallback_display=tool_tag,
            )

            vals13399 = extract_13399_values_from_cam(cam_op, cam_to_13399_map)

            tool_xml = build_cutting_tool_13399_dtasset_xml(
                global_asset_id_url=g_url,
                asset_id=tool_asset_id,
                element_id=elem_id,  # ← T번호
                display_name=display,  # ← 툴 타입(매핑)
                values_13399=vals13399,
            )
            tool_cache[tool_tag] = elem_id
            tool_xmls_to_write[elem_id] = tool_xml

        # 4-B) 워킹스텝 XML → dict 변환, its_tool 스텁 + ref_dt_cutting_tool 주입
        ws_xml = create_feature_xml_temp(
            json_data=cam_op, mapping_data=cam_to_14649_map, strict_required=False
        )
        ws_node = xmltodict.parse(
            ws_xml,
            process_namespaces=True,
            namespaces={
                "http://digital-thread.re/dt_asset": None,
                "http://digital-thread.re/iso14649": None,
                "http://www.w3.org/2001/XMLSchema-instance": "xsi",
            },
            attr_prefix="@",
        )["its_elements"]

        op = ws_node.get("its_operation") or {}
        # its_tool 더미 유지 …
        # ref_dt_cutting_tool 구성 (요구 포맷):
        full_uri = f"{g_url}/{tool_asset_id}/{elem_id}"
        op["ref_dt_cutting_tool"] = {
            "element_id": elem_id,  # ✅ ref 자체의 element_id도 tool elem_id와 동일
            "category": "reference",
            "display_name": "Cutting Tool Ref",
            "keys": [
                {"key": "DT_ELEMENT_FULLPATH", "value": full_uri},  # ✅ 단일 키만 사용
            ],
        }
        ws_node["its_operation"] = op

        # ref_dt_cutting_tool 주입 (이제 FULLPATH + 메타로)
        full_uri = f"{g_url}/{tool_asset_id}/{elem_id}"

        inject_cutting_tool_ref(
            ws_node,
            tool_uri=full_uri,
            dt_global_url=g_url,  # 호환용 자리만 채움(유틸 내부에서 미사용)
            tool_asset_id=tool_asset_id,  # 호환용 자리만 채움(유틸 내부에서 미사용)
            tool_element_id=elem_id,  # ref_dt_cutting_tool.element_id == tool elem_id
            display_name="Cutting Tool Ref",
        )

        # its_secplane 더미 보강 (name + 빈 position)
        ensure_dummy_secplane(ws_node)

        # its_feature 더미 보강
        ensure_dummy_feature(ws_node)

        # ✅ pathmode 보강(+순서 정렬). CAM 매핑에 있으면 그 값, 없으면 "forward"
        ensure_strategy_with_pathmode(
            ws_node, cam_op, cam_to_14649_map, default="forward"
        )

        # feedrate_reference 보강 (cutmode는 ws_node 쪽에서 추출 가능하면 넣고, 없으면 None)
        cutmode = (
            ws_node.get("its_operation", {})
            .get("MachiningOperation", {})
            .get("MillingMachiningOperation", {})
            .get("MillingTypeOperation", {})
            .get("FreeformOperation", {})
            .get("its_machining_strategy", {})
            .get("FreeformStrategy", {})
            .get("cutmode")
        )

        # ① CAM JSON에서 coolant 원값 뽑기
        coolant_cam_key = find_cam_key_for_coolant(cam_to_14649_map)
        raw_coolant = (
            get_nested_value(cam_op, coolant_cam_key.split("."))
            if coolant_cam_key
            else None
        )

        # ② 밀링 머신 펑션 보강 (bool 변환 + 필수 필드 채우기)
        ensure_milling_machine_functions(ws_node, raw_coolant, default=False)

        # its_tool 더미 추가
        force_dummy_its_tool(ws_node, dummy_id="temp")

        # its_technology, feedrate_reference 보강 + 순서 정렬
        ensure_milling_technology(ws_node, cutmode=cutmode)

        # ✅ its_operation 순서 재정렬 (ref_dt_cutting_tool 맨 앞)
        ws_node["its_operation"] = reorder_operation_children(ws_node["its_operation"])

        ws_nodes_to_append.append(ws_node)

    # --- 5) 쓰기 전 스키마 검증 → 쓰기 + 보상 롤백 ---
    created_tool_elements: List[str] = (
        []
    )  # 이번 호출에서 '새로 생성한' tool element_id만 기록

    try:
        # 5-0) 스키마 선검증: (A) 모든 cutting_tool_13399 XML, (B) 최종 프로젝트 XML
        for _elem_id, tool_xml in tool_xmls_to_write.items():
            if not validate_xml_against_schema(tool_xml):
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid tool XML schema: element_id={_elem_id}",
                )

        updated_xml = working_project_xml
        for ws_node in ws_nodes_to_append:
            updated_xml = append_ws_into_project_xml(
                project_xml_text=updated_xml,
                project_element_id=project_element_id,
                workplan_id=workplan_id,
                ws_node_dict=ws_node,
            )

        # ✅ 한 방에 전체 정렬
        updated_xml = normalize_dt_project_structure(updated_xml, project_element_id)

        if not validate_xml_against_schema(updated_xml):
            with open("debug_updated.xml", "w", encoding="utf-8") as f:
                f.write(updated_xml)
            raise HTTPException(
                status_code=422, detail="Updated project XML failed schema validation"
            )

        # 5-1) 실제 쓰기: 툴 → 프로젝트 (DB 에러 대비 롤백 준비)
        #    - 이미 스키마 통과했으므로 여기서는 DB 오류만 대비
        for elem_id, tool_xml in tool_xmls_to_write.items():
            # 존재하면 재사용, 없을 때만 생성
            from src.utils.v3_xml_parser import extract_dtasset_meta

            meta = extract_dtasset_meta(tool_xml, strict=True)
            exists = await asset_service.get_by_keys(
                global_asset_id=meta["global_asset_id"],
                asset_id=meta["asset_id"],
                type=meta["type"],
                element_id=meta["element_id"],
            )
            if not exists:
                await asset_service.create_from_xml(tool_xml, upsert=False)
                created_tool_elements.append(elem_id)

        ok = await asset_service.update_from_xml(
            mongo_id=str(proj_doc["_id"]),
            xml=updated_xml,
            validate_schema=False,  # 이미 유효성 검증 완료
            forbid_type_change=True,
            precheck_dup_conflict=False,
        )
        if not ok:
            raise HTTPException(status_code=500, detail="Project update failed")

        # 성공
        return {
            "message": f"{cam_type.upper()} CAM applied",
            "order_applied": ordered_names if ct.startswith("power") else None,
            "tool_sequence": tool_seq,
            "tools_created": len(created_tool_elements),
            "workingsteps_appended": len(ws_nodes_to_append),
            "project_element_id": project_element_id,
            "workplan_id": workplan_id,
        }

    except HTTPException:
        # 프로젝트 XML은 아직 DB에 쓰기 전이면 복원 불필요.
        # 다만 툴 생성이 일부라도 됐으면 삭제(보상 롤백).
        for elem_id in created_tool_elements:
            try:
                await asset_service.repo.rollback_delete_tool_by_keys(
                    global_asset_id=g_url, asset_id=tool_asset_id, element_id=elem_id
                )
            except Exception:
                logging.exception(
                    "[apply_cam_into_workplan] tool delete rollback failed: %s",
                    elem_id,
                )
        raise

    except Exception as e:
        # 예기치 못한 오류. 프로젝트 XML이 이미 저장됐다면 복원 시도.
        try:
            await asset_service.repo.rollback_restore_xml_by_mongo_id(
                str(proj_doc["_id"]), original_project_xml
            )
        except Exception:
            logging.exception("[apply_cam_into_workplan] project xml restore failed")

        for elem_id in created_tool_elements:
            try:
                await asset_service.repo.rollback_delete_tool_by_keys(
                    global_asset_id=g_url, asset_id=tool_asset_id, element_id=elem_id
                )
            except Exception:
                logging.exception(
                    "[apply_cam_into_workplan] tool delete rollback failed: %s",
                    elem_id,
                )

        raise HTTPException(
            status_code=500,
            detail=f"apply_cam_into_workplan failed and rolled back: {type(e).__name__}: {e}",
        )


@router.post("/upload-platform")
async def upload_project_and_refs(
    global_asset_id: str = Query(..., description="프로젝트 global_asset_id"),
    asset_id: str = Query(..., description="프로젝트 asset_id"),
    element_id: str = Query(..., description="프로젝트 element_id"),
    project_service: V3ProjectService = Depends(get_v3_project_service),
    file_service: FileService = Depends(get_file_service),
):
    """
    특정 프로젝트와 모든 참조 XML을 데이터 플랫폼에 업로드한다.
    - 항상 전체 업로드 (dt_file, dt_material, dt_machine_tool, dt_cutting_tool_13399)
    """
    # ✅ 서비스에 존재하는 메서드명으로 호출
    result = await project_service.upload_project_and_related(
        global_asset_id=global_asset_id,
        asset_id=asset_id,
        project_element_id=element_id,
        file_service=file_service,
        include_ref_types=None,  # 항상 전체 업로드면 None 유지,
    )
    return result


@router.post("/upload-platform-one")
async def upload_one_asset(
    global_asset_id: str = Query(...),
    asset_id: str = Query(...),
    element_id: str = Query(...),
    type: str = Query(
        ...,
        description="dt_project | dt_file | dt_material | dt_machine_tool | dt_cutting_tool_13399",
    ),
    file_service: FileService = Depends(get_file_service),
    project_service: V3ProjectService = Depends(get_v3_project_service),
):
    return await project_service.upload_single_asset(
        global_asset_id=global_asset_id,
        asset_id=asset_id,
        type=type,
        element_id=element_id,
        file_service=file_service,
    )


@router.get("/{element_id}", response_model=AssetDocument, summary="프로젝트 상세 조회")
async def get_project(
    element_id: str = Path(..., description="조회할 프로젝트의 element_id"),
    global_asset_id: str = Query(..., description="조회할 프로젝트의 글로벌 에셋 Id"),
    asset_id: str = Query(..., description="조회할 프로젝트의 에셋 Id"),
    project_service: V3ProjectService = Depends(get_v3_project_service),
):
    """
    프로젝트를 조회하는 API입니다.

    - 저장된 프로젝트의 document를 반환합니다.
    - **반환값**: 프로젝트 도큐먼트
    """
    return await project_service.get_by_keys(
        global_asset_id=global_asset_id,
        asset_id=asset_id,
        type="dt_project",
        element_id=element_id,
    )


@router.get(
    "/{element_id}/extract",
    summary="project attribute 추출",
)
async def get_project_extract(
    element_id: str = Path(..., description="조회할 프로젝트의 element_id"),
    global_asset_id: str = Query(..., description="조회할 프로젝트의 글로벌 에셋 Id"),
    asset_id: str = Query(..., description="조회할 프로젝트의 에셋 Id"),
    attribute_path: str = Query(..., description="조회할 프로젝트의 속성 패스"),
    project_service: V3ProjectService = Depends(get_v3_project_service),
):
    """
    프로젝트의 xml을 조회하는 API입니다.

    - 저장된 프로젝트의 xml을 반환합니다.
    - **반환값**: 프로젝트 xml
    """
    project = await project_service.get_by_keys(
        global_asset_id=global_asset_id,
        asset_id=asset_id,
        type="dt_project",
        element_id=element_id,
    )
    project_data = project["data"]
    res = await project_service.extract_attribute_path(
        xml_string=project_data, path=attribute_path
    )

    return Response(content=res, media_type="application/xml")

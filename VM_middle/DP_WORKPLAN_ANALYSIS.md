# DP 연동 최종 설계 — API 검증 완료

> DP API 실제 호출로 모든 데이터 접근 경로 검증 완료 (2026-04-20)

---

## 1. 핵심 발견: `asset/element` API로 xmlStr 직접 조회 가능

### 검증 결과

| 타입 | API | xmlStr 반환 | 크기 예시 |
|------|-----|:-----------:|----------|
| **프로젝트** | `GET /openapi/v2/asset/element?gid=&aid=&eid=` | ✅ | 17,767자 |
| **공구** | `GET /openapi/v2/asset/element?gid=&aid=&eid=` | ✅ | 853자 |
| **소재** | `GET /openapi/v2/asset/element?gid=&aid=&eid=` | ✅ | 579자 |
| **dt_file** | `GET /openapi/v2/asset/element?gid=&aid=&eid=` | ✅ | 876자 |

> [!TIP]
> **XML 파일 다운로드(`files/download/asset/{seq}`) 없이도 `xmlStr` 필드에서 바로 XML을 얻을 수 있다.**
> 단, **NC 파일 텍스트**는 XML이 아니므로 `GET /openapi/v2/files/download/userdata?path={path}` 로 별도 다운로드 필요.

### 주의: 목록 API vs 개별 API

| API | xmlStr |
|-----|:------:|
| `GET /openapi/v2/asset/find/element?type=project` (목록) | ❌ null |
| `GET /openapi/v2/asset/element?gid=&aid=&eid=` (개별) | ✅ 반환 |

---

## 2. DP API 호출 전체 맵

```
인증: Authorization 헤더에 DP_API_KEY 값 (GET /openapi/v2/* 전체 공통)

[프로젝트 목록]
  GET /openapi/v2/asset/find/element?type=project&page=0&size=20
  → content[].{ assetGlobalId(gid), assetId(aid), elementId(eid),
                 displayName, description, assetSeq }

[프로젝트 XML 조회]
  GET /openapi/v2/asset/element?gid={gid}&aid={aid}&eid={eid}
  → xmlStr (dt_project XML)

[같은 gid 아래 전체 element 검색]
  GET /openapi/v2/asset/find/element?gid={gid}&page=0&size=100
  → typeCounts + content[] (소재/공구/파일 element 목록)

[개별 element XML 조회] (소재, 공구, dt_file 모두 동일)
  GET /openapi/v2/asset/element?gid={gid}&aid={aid}&eid={eid}
  → xmlStr

[NC 파일 다운로드]
  GET /openapi/v2/files/download/userdata?path={dt_file.path}
  → NC 텍스트 바이너리
```

---

## 3. 워크플랜 처리 — 3가지 패턴 모두 지원

### 패턴 A: main_workplan 아래 하위 workplan 1개

```xml
<main_workplan>
  <its_id>mainworkplan_001</its_id>
  <its_elements xsi:type="workplan">    ← 하위 WP 1개
    <its_id>wp_001</its_id>
    <its_elements xsi:type="machining_workingstep">...</its_elements>
    <its_elements xsi:type="machining_workingstep">...</its_elements>
  </its_elements>
</main_workplan>
```
→ VM 단위: `wp_001` (자동 선택)

### 패턴 B: main_workplan 아래 하위 workplan 여러 개

```xml
<main_workplan>
  <its_id>wp-001</its_id>
  <its_elements xsi:type="workplan">
    <its_id>wp_001</its_id> ...
  </its_elements>
  <its_elements xsi:type="workplan">
    <its_id>wp_002</its_id> ...
  </its_elements>
  ...
</main_workplan>
```
→ VM 단위: 각 `wp_001`, `wp_002` … 중 선택 (전체 실행 ❌)

### 패턴 C: main_workplan 아래 바로 workingstep (하위 workplan 없음)

```xml
<main_workplan>
  <its_id>wp_main</its_id>
  <its_elements xsi:type="machining_workingstep">...</its_elements>
  <its_elements xsi:type="machining_workingstep">...</its_elements>
</main_workplan>
```
→ VM 단위: `wp_main` 전체 (하위 workplan이 없으므로 main 자체가 실행 단위)

### 통합 판별 로직

```python
def extract_vm_workplans(project_xml: str) -> list[dict]:
    summary = extract_project_summary(project_xml)
    main_wpid = summary["main_wpid"]
    all_wpids = summary["workplan_ids"]
    
    child_wpids = [w for w in all_wpids if w != main_wpid]
    
    if not child_wpids:
        # 패턴 C: main 아래 직접 workingstep
        # → main_workplan 자체가 VM 실행 단위
        ws = extract_tool_refs_in_order(project_xml, wpid=None)
        return [{"wpid": main_wpid, "ws_count": len(ws)}]
    
    if len(child_wpids) == 1:
        # 패턴 A: 하위 workplan 1개
        ws = extract_tool_refs_in_order(project_xml, wpid=child_wpids[0])
        return [{"wpid": child_wpids[0], "ws_count": len(ws)}]
    
    # 패턴 B: 하위 workplan 여러 개
    return [
        {
            "wpid": cwp,
            "ws_count": len(extract_tool_refs_in_order(project_xml, wpid=cwp)),
        }
        for cwp in child_wpids
    ]
```

---

## 4. 공구 참조 없는 프로젝트 처리 — Graceful Degradation

### 전략: "빈 VM 프로젝트 + needs-fix" 생성

공구 참조(reflist)가 없거나 소재 정보가 없는 프로젝트도 VM 프로젝트를 생성할 수 있되, **유효성 검증에서 자동으로 `needs-fix` 상태**가 되어 사용자가 수기로 보충할 수 있도록 한다.

```
[프로젝트 데이터 수준]          [VM 프로젝트 생성 결과]

풀 데이터                       status: ready
(소재 + 공구 + NC 모두 있음)      → 바로 VM 실행 가능

NC만 있고 공구 정보 없음          status: needs-fix
                                 → process[].tool_data = "null,null,..."
                                 → validation.errors 에 상세 안내
                                 → 사용자: PATCH로 tool_data 수정 후 실행

NC도 없음                        status: needs-fix
                                 → process = []
                                 → 사용자: PATCH로 process 추가 후 실행

워크플랜만 있음                   status: needs-fix
(공구, NC 모두 없음)              → stock/process 모두 빈값
                                 → 사용자: stock + process 수기 입력
```

### 구현 상세

```python
async def create_from_dp(self, payload):
    # 1) 프로젝트 XML 조회 (항상 성공)
    proj_xml = await dp_client.get_element_xml(gid, aid, eid)
    workplans = extract_vm_workplans(proj_xml)
    
    # 2) 소재 조회 (실패 가능 → 빈값)
    try:
        material_xml = await dp_client.get_element_xml(gid, mat_aid, mat_eid)
        stock = compute_stock(material_xml)
    except:
        stock = {"stock_type": None, "stock_size": None}  # 빈값
    
    # 3) 공구 조회 (실패 가능 → null 채움)
    tool_data_map = {}
    for ref in tool_refs:
        try:
            tool_xml = await dp_client.get_element_xml(gid, tool_aid, tool_eid)
            tool_data_map[ref.eid] = parse_cutting_tool_13399_xml(tool_xml)
        except:
            tool_data_map[ref.eid] = None  # null → needs-fix 트리거
    
    # 4) NC 다운로드 (실패 가능 → process 비움)
    try:
        nc_bytes = await dp_client.download_file(nc_path)
        segments = split_nc(nc_bytes)
    except:
        segments = []  # 빈 process → needs-fix
    
    # 5) project.prj 조립 (빈값 허용)
    project_file = build_project_file(stock, segments, tool_data_map)
    
    # 6) 유효성 검증 → status 결정
    validation = validate(project_file)
    status = "ready" if validation.ok else "needs-fix"
    
    # 7) MongoDB 저장
    return await self.dao.insert(project_file, status, validation)
```

### 유효성 검증에서의 안내 메시지

```json
{
  "status": "needs-fix",
  "validation": {
    "valid": false,
    "errors": [
      {
        "field": "stock_type",
        "message": "소재 정보를 찾을 수 없습니다. PATCH /stock으로 수동 입력해주세요."
      },
      {
        "field": "process[0].tool_data",
        "message": "공구 T1의 정보를 조회할 수 없습니다. tool_data를 수동 입력해주세요."
      }
    ]
  }
}
```

---

## 5. 백엔드 API 설계

### VM_middle 새 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/dp/projects` | DP에서 프로젝트 목록 조회 (페이지네이션) |
| `GET` | `/api/v1/dp/projects/{gid}/{aid}/{eid}/workplans` | 특정 프로젝트의 VM 실행 가능 워크플랜 목록 |
| `POST` | `/api/v1/vm-project` | VM 프로젝트 생성 (**기존**. source="dp" 분기 추가) |

### `GET /api/v1/dp/projects` 응답 예시

```json
{
  "items": [
    {
      "gid": "https://digital-thread.re/kitech/mes_test2",
      "aid": "https://digital-thread.re/kitech/mes_test2/mes_test2",
      "eid": "mes_test2",
      "displayName": "mes test project.",
      "description": "mes test project.",
      "asset_types": ["project", "cutting_tool_13399", "file"],
      "has_material": false,
      "has_nc": true
    }
  ],
  "total": 226,
  "page": 0,
  "size": 20
}
```

### `GET /api/v1/dp/projects/.../workplans` 응답 예시

```json
{
  "gid": "...",
  "eid": "mes_test2",
  "pattern": "single_sub_workplan",
  "workplans": [
    {
      "wpid": "wp_001",
      "ws_count": 8,
      "has_nc": true,
      "has_tools": true
    }
  ]
}
```

### `POST /api/v1/vm-project` 기존 body에 source 필드 추가

```json
{
  "source": "dp",         // "dp" 또는 "iso" (기존 호환)
  "gid": "https://digital-thread.re/kitech/mes_test2",
  "aid": "https://digital-thread.re/kitech/mes_test2/mes_test2",
  "eid": "mes_test2",
  "wpid": "wp_001"        // 선택한 워크플랜 (필수)
}
```

---

## 6. 전체 호출 흐름 (End-to-End, 백엔드 only)

```
[Client / curl / Postman]
   │
   │ Step 1: 프로젝트 목록 조회
   │ GET /api/v1/dp/projects?page=0&size=20
   │   → 226개 프로젝트 목록 + 메타정보
   │
   │ Step 2: 워크플랜 확인
   │ GET /api/v1/dp/projects/{gid}/{aid}/{eid}/workplans
   │   → [wp_001 (WS 8개)]
   │
   │ Step 3: VM 프로젝트 생성
   │ POST /api/v1/vm-project
   │   body: { source: "dp", gid, aid, eid, wpid: "wp_001" }
   │   
   │   내부 처리:
   │   ├─ DP: asset/element → 프로젝트 XML → 워크플랜/공구참조 파싱
   │   ├─ DP: asset/element → 각 공구 XML → tool_data 구성
   │   ├─ DP: asset/element → 소재 XML → stock 계산 (없으면 빈값)
   │   ├─ DP: asset/find/element?type=file → dt_file 목록
   │   ├─ DP: asset/element → dt_file XML → WORKPLAN 매칭
   │   ├─ DP: files/download/userdata?path= → NC 텍스트
   │   ├─ NC 분할 + project.prj 생성
   │   └─ 유효성 검증 → ready 또는 needs-fix
   │
   │   → { vm_project_id, status, validation }
   │
   │ Step 4 (needs-fix인 경우):
   │ PATCH /api/v1/vm-project/{id}/project-file/stock
   │ PATCH /api/v1/vm-project/{id}/project-file/process
   │
   │ Step 5: VM 실행
   │ POST /api/v1/vm-project/{id}/start-vm
```

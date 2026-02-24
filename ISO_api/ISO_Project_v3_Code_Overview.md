# ISO Digital-Thread (v3 API) 코드베이스 정리

> 이 문서는 업로드된 `iso_project_code.zip`의 **현재 포함된 소스만** 기준으로 작성했습니다.  
> 사용하지 않는 코드는 제외되었다고 하셨지만, 일부 **누락된 파일(`__init__.py` 등)** 이 있을 수 있어 실행은 그대로 안 될 수도 있습니다.  
> 그럼에도 **v3 API 관점에서 “이 프로젝트가 무엇을 하고, 파일들이 어떻게 연결되는지”**를 초보자도 따라올 수 있게 최대한 자세히 설명합니다.

---

## 1. 프로젝트가 하는 일 (한 문장 요약)

이 프로젝트는 **ISO 기반 디지털쓰레드 자산(dt_asset XML)** 을 업로드/저장하고,  
특히 **프로젝트(dt_project) XML을 업로드한 뒤 CAM 정보를 가공(workingstep 추가/도구 13399 생성 등)하여**  
최종적으로 **데이터플랫폼(DP)으로 업로드**하는 기능을 제공합니다.

---

## 2. 큰 그림: 데이터 흐름(파이프라인)

대략적인 흐름은 다음과 같습니다.

1) 사용자가 **dt_asset XML**(여러 dt_element 포함 가능)을 API로 업로드  
2) 서버는 XML을 파싱해 **각 element(dt_project/dt_workplan/dt_file/...)를 분할 저장**  
3) 프로젝트 관련 API에서 CAM JSON/파일을 받아  
   - 프로젝트 XML 구조를 정규화하고  
   - workingstep을 추가하고  
   - 필요하면 dt_cutting_tool_13399를 만들거나(ref를 주입)  
4) 저장된 **프로젝트 + 연관 자산(dt_file, dt_material, dt_machine_tool, dt_cutting_tool_13399)** 을 모아서  
   **DP(OpenAPI v2)로 업로드**  
   - dt_file은 파일 바이너리가 있으면 `xml-with-file`, 없으면 `xml` 로 업로드

---

## 3. 폴더 구조(현재 zip 기준)

아래는 제공된 코드의 트리입니다.

```text
iso_project_code/
├── src/
│   ├── apis/
│   │   ├── v3/
│   │   │   ├── asset.py
│   │   │   └── project.py
│   │   └── .DS_Store
│   ├── entities/
│   │   ├── asset.py
│   │   ├── file.py
│   │   └── model_v31.py
│   ├── schemas/
│   │   ├── asset.py
│   │   ├── file.py
│   │   └── project.py
│   ├── services/
│   │   ├── asset.py
│   │   ├── file.py
│   │   └── v3_project.py
│   ├── utils/
│   │   ├── asset_xml_parser.py
│   │   ├── cam_common.py
│   │   ├── cam_nx_adapter.py
│   │   ├── cam_powermill_adapter.py
│   │   ├── env.py
│   │   ├── exceptions.py
│   │   ├── file_modifier.py
│   │   ├── nc_spliter.py
│   │   ├── stock.py
│   │   ├── v3_xml_parser.py
│   │   └── xml_parser.py
│   └── .DS_Store
├── .DS_Store
├── config.py
├── database.py
└── main.py
```

### 루트 파일 설명
- `main.py` : FastAPI 앱 엔트리포인트로 보이나, **현재 zip에는 없는 라우터를 import**하고 있어 “구버전/미사용”일 가능성이 큼
- `config.py` : `.env` 로부터 VM/DP 설정값 로드
- `database.py` : Mongo(Motor) 연결 + GridFS + (v3) assets 컬렉션 + 인덱스 생성 유틸
- `src/` : 실제 v3 API 구현 코드

---

## 4. 실행/환경 설정 (초보자 기준)

### 4.1 필수 기술 스택
- Python + FastAPI
- MongoDB (Motor async driver)
- GridFS (파일 저장용)
- XML 파싱/가공: `xmltodict`, `lxml`(스키마 검증에 쓰일 수 있음)
- 외부 업로드: DP API 호출 (`httpx`/`requests`)

### 4.2 환경변수(.env)로 관리되는 값
`config.py`에서 설명하는 값:

- VM 관련
  - `vm_api_url`, `vm_username`, `vm_password`
- DP 관련
  - `dp_base_url`, `dp_api_key`

`database.py`에서 사용하는 값:
- `MONGO_URL` (default: `mongodb://mongo:27017`)
- `DATABASE_NAME` (default: `iso14649`)

> 실 운영에서는 `.env`를 그대로 공유하지 말고 `.env.example`로 템플릿만 남기는 것을 권장합니다.

---

## 5. DB 저장 구조 (Mongo + GridFS)

### 5.1 컬렉션/버킷
`database.py` 기준:
- `assets` : v3에서 사용하는 dt_asset 문서 저장용 컬렉션
- `projects` : 구버전 또는 별도 로직에서 사용될 수 있는 컬렉션(현재 v3 중심이면 덜 중요할 수 있음)
- GridFS bucket `files` : dt_file에 대응되는 실제 바이너리 저장

### 5.2 v3용 인덱스
`ensure_asset_indexes()`에서 “유니크 인덱스”를 생성합니다.

- Unique Key: `(global_asset_id, asset_id, type, element_id)`
  - 같은 프로젝트/자산에 대해 동일 element를 중복 저장하지 못하게 막습니다.
- 검색용 인덱스: `asset_id`, `type`, `category`, `element_id`

> 초보자 관점 포인트  
> - `global_asset_id` = “자산 그룹(프로젝트/라인/회사 단위)”  
> - `asset_id` = “그 그룹 내 개별 자산 ID”  
> - `type` = `dt_project`, `dt_workplan`, `dt_file` 같은 자산 종류  
> - `element_id` = 문서 내부 element의 고유 ID

---

## 6. 핵심 도메인 개념(초보자용)

### 6.1 dt_asset 문서란?
이 프로젝트에서 다루는 XML은 “dt_asset” 루트 아래에 여러 종류의 element가 들어갈 수 있습니다.

예:
- dt_project (프로젝트)
- dt_workplan (공정 계획)
- dt_file (NC/STEP/문서 파일 등)
- dt_material, dt_machine_tool, dt_cutting_tool_13399 (참조되는 자산들)

### 6.2 “프로젝트 업로드”가 의미하는 것
`/api/v3/projects`에 프로젝트 XML을 업로드하면:
- XML이 스키마 검증을 통과하는지 확인하고
- XML에서 메타(`global_asset_id`, `asset_id`, `element_id`, `type`)를 추출해
- DB에 저장합니다.

---

## 7. v3 API 정리 (가장 중요)

이 zip에 포함된 v3 라우터는 두 개입니다.

- `src/apis/v3/asset.py`  → `/api/v3/assets`
- `src/apis/v3/project.py` → `/api/v3/projects`

---

# 7.1 Asset API (`/api/v3/assets`)

파일: `src/apis/v3/asset.py`  
목적: **dt_asset XML(여러 element 포함 가능)을 업로드/조회/추출**하고, NC 관련 기능도 제공합니다.

## (1) POST `/api/v3/assets`
**Asset 업로드(분할/부분성공, is_upload=False)**

- 입력:
  - `xml` : dt_asset XML 파일 (필수)
  - `upload_files` : dt_file 요소에 매칭되는 실제 파일들 (선택)
- 동작:
  - XML 내부의 여러 element를 **분리해서 각각 저장**
  - dt_file 요소는 **display_name과 업로드 파일명이 매칭**되어야 저장/업로드가 가능
  - 저장 시 `is_upload=False` (아직 DP 업로드 전)
  - 전체 실패가 아니라 element 단위로 성공/실패를 모아 **부분 성공(206)** 을 지원

> 초보자 팁  
> “부분성공”은 프로젝트 XML 하나에 dt_file이 여러 개 섞여 있을 때,  
> 어떤 파일은 정상, 어떤 파일은 누락 같은 상황을 안전하게 처리하려는 설계입니다.

## (2) POST `/api/v3/assets/nc`
NC 관련 처리(추가 기능)

## (3) GET `/api/v3/assets/{element_id}`
단일 asset 조회

## (4) GET `/api/v3/assets/extract`
XML에서 특정 경로(path)의 값을 추출(내부 함수 `get_inner_data` 기반)

## (5) GET `/api/v3/assets/file-download`
dt_file 다운로드(StreamingResponse)

## (6) GET `/api/v3/assets/global-assets`
global_asset_id 기준 목록 조회

## (7) GET `/api/v3/assets/global-assets/{global_asset_id}/asset-ids`
특정 global_asset_id의 asset_id 목록

## (8) GET `/api/v3/assets/global-assets/asset-ids`
전체 global_asset_id별 asset_id를 그룹핑해서 반환

---

# 7.2 Project API (`/api/v3/projects`)

파일: `src/apis/v3/project.py`  
목적: **프로젝트(dt_project)를 업로드하고, CAM 기반 가공을 수행하고, DP로 업로드**하는 파이프라인 제공.

## (1) POST `/api/v3/projects`
**프로젝트 업로드**

- 입력: `project_xml_file`
- 동작: 프로젝트 XML 파싱 → DB 저장 → 생성 결과 반환

## (2) POST `/api/v3/projects/cam-json`
**CAM JSON을 받아서 작업(workingstep/tool 등) 생성/가공에 쓰는 API**

- 내부에서 사용되는 유틸이 매우 많습니다:
  - `cam_common.py` : CAM을 ISO 구조로 맞추기 위한 정규화/보정 함수들
  - `cam_nx_adapter.py` / `cam_powermill_adapter.py` : NX, PowerMill 등 벤더별 CAM 형식에서 operation을 추출
  - `v3_xml_parser.py` : 프로젝트/워크플랜 구조 탐색, workingstep 추가, tool ref 주입 등

> “이 API가 정확히 무엇을 생성/수정하는지”는 실제 요청 JSON 포맷과 함께 코드를 기준으로 더 상세 분석 가능합니다.

## (3) POST `/api/v3/projects/add-ref`
**프로젝트 XML 내부에 참조(ref)를 추가**

- 참조 유형에 따라 “어디(anchor)에 넣는지” 규칙이 서비스에 정의돼 있습니다.
  - dt_machine_tool → workplan
  - dt_material → workpiece
  - dt_cutting_tool_13399 → operation(workingstep/operation)

이 규칙은 `src/services/v3_project.py`의 `REF_RULES`에 정리되어 있습니다.

## (4) PUT `/api/v3/projects/delete-ref`
참조(ref) 삭제

## (5) POST `/api/v3/projects/upload-platform`
**프로젝트 + 연관 자산을 DP로 업로드**

- 내부 로직 요약:
  1) DB에서 dt_project XML을 가져옴
  2) DP에 프로젝트 XML 업로드
  3) 프로젝트 XML을 기준으로 “관련 자산”을 수집  
     (dt_file, dt_material, dt_machine_tool, dt_cutting_tool_13399 등)
  4) 각 자산을 DP로 업로드
     - `dt_file`이고 file_oid가 있으면 `xml-with-file`
     - 그렇지 않으면 `xml`
  5) 업로드 성공한 문서는 DB에 `is_upload=True`로 표시

## (6) POST `/api/v3/projects/upload-platform-one`
단일 asset만 DP로 업로드(필요 시 디버깅/재시도용)

## (7) GET `/api/v3/projects/{element_id}`
프로젝트 단일 조회

## (8) GET `/api/v3/projects/{element_id}/extract`
프로젝트 XML에서 특정 경로의 값 추출

---

## 8. Service/Repository(비즈니스 로직) 구조

### 8.1 AssetRepository (`src/entities/asset.py`)
MongoDB의 `assets` 컬렉션을 대상으로 CRUD/검색을 제공합니다.

- **중복 방지**: unique index 기반으로 같은 키 저장 방지
- `extract_dtasset_meta()`를 이용해 XML에서 키(global_asset_id, asset_id, type, element_id)를 뽑아 저장 키로 씁니다.

### 8.2 AssetService (`src/services/asset.py`)
- `/api/v3/assets` 라우터가 호출하는 “업로드/조회/목록/추출”의 실제 처리 담당
- 업로드 시 **XML 분할 저장 + dt_file 바이너리(GridFS) 저장**을 수행할 가능성이 큼

### 8.3 FileService (`src/services/file.py`)
- GridFS를 통해 파일 byte를 읽고 쓰는 역할

### 8.4 V3ProjectService (`src/services/v3_project.py`)
프로젝트 관련 고급 기능 담당:

- 참조 추가/삭제: `attach_ref()`, `remove_ref()`
- DP 업로드:
  - `_dp_upload_xml()` / `_dp_upload_xml_with_file()`로 DP 호출
  - `upload_project_and_related()`에서 프로젝트+연관자산 업로드를 orchestration
- 연관 자산 수집:
  - `_collect_related_assets_by_project_xml()`
  - `_collect_dt_files_referencing_project()`

---

## 9. Utils(파서/보정 로직) 개요

현재 zip에서 가장 중요한 유틸은 이 라인입니다.

- `src/utils/v3_xml_parser.py`
  - 스키마 검증
  - dt_project에서 workplan/workpiece/operation 찾기
  - workingstep 추가(append)
  - tool ref 주입(inject)
  - XML 내부 경로 값 추출(get_nested_value 등)
- `src/utils/cam_common.py`
  - CAM 구조를 ISO 구조에 맞게 “정규화/보정/더미 노드 생성”
  - 13399 도구 생성용 값 추출/빌드(`build_cutting_tool_13399_dtasset_xml`)
- `src/utils/cam_nx_adapter.py`, `src/utils/cam_powermill_adapter.py`
  - 벤더별 CAM 데이터에서 operation들을 “추출(pick)”해서 표준 형태로 넘기는 역할
- `src/utils/nc_spliter.py`
  - NC 파일에서 tool sequence 추출 등

> 초보자에게 중요한 포인트  
> - “XML 파싱(v3_xml_parser)”은 **구조 탐색/삽입**  
> - “CAM 정규화(cam_common)”는 **CAM 데이터를 ISO 모델에 맞게 바꾸는 보정**  
> - “NX/PowerMill adapter”는 **입력 포맷 차이를 흡수하는 어댑터**입니다.

---

## 10. DP(데이터 플랫폼) 업로드 동작 (상세)

`V3ProjectService`는 DP 업로드를 아래 endpoint로 합니다.

- `POST {dp_base_url}/openapi/v2/asset/xml`
- `POST {dp_base_url}/openapi/v2/asset/xml-with-file`
- Header: `Authorization: {dp_api_key}`

업로드 전략:
- dt_project → 먼저 업로드
- 프로젝트 XML에서 참조를 따라 연관 자산 수집
- dt_file의 경우:
  - XML 내부에 file_oid가 있고
  - GridFS에서 바이너리를 읽을 수 있으면
  - `xml-with-file`로 업로드(파일명은 dt_file의 `display_name` 기반)
- 성공 시 DB의 해당 문서에 `is_upload=True` 세팅

---

## 11. “프로젝트 XML 업로드 → CAM 파싱 → workingstep 추가 → dt_cutting_tool_13399 생성 → 플랫폼 업로드”와의 연결

김지원님이 다시 집중하려는 시나리오를 이 코드에 매핑하면:

1) **프로젝트 XML 업로드**
   - `POST /api/v3/projects` (dt_project 저장)

2) **CAM 파싱(벤더별)**
   - `POST /api/v3/projects/cam-json`
   - 여기서 NX/PowerMill adapter로 operation 추출

3) **workingstep 추가**
   - `append_ws_into_project_xml` (v3_xml_parser)
   - `count_workingsteps_in_workplan_xml` 등으로 기존 step 수 파악 가능

4) **dt_cutting_tool_13399 만들기 / ref 주입**
   - `build_cutting_tool_13399_dtasset_xml` (cam_common)
   - `inject_cutting_tool_ref` (v3_xml_parser)
   - `invert_cam14649_to_cam13399`, `extract_13399_values_from_cam` 등으로 13399 값 추출/변환

5) **데이터 플랫폼 업로드**
   - `POST /api/v3/projects/upload-platform`
   - 프로젝트 + 연관자산(dt_file/material/machine_tool/cutting_tool_13399) 업로드

즉, “우리가 다시 개발할 핵심”은 대부분 다음 파일들에 있습니다.

- `src/apis/v3/project.py`
- `src/services/v3_project.py`
- `src/utils/v3_xml_parser.py`
- `src/utils/cam_common.py`
- (입력 포맷별) `src/utils/cam_nx_adapter.py`, `src/utils/cam_powermill_adapter.py`

---

## 12. 현재 zip 기준 “주의/보완 필요” 체크리스트

1) **패키지 인식 문제**  
   `src/` 이하에 `__init__.py`가 없어 보입니다.  
   실제 레포에서는 존재했는데 zip에서 제외됐을 가능성이 큽니다.  
   (없으면 `from src.services import ...` 같은 import가 실패합니다.)

2) **루트 main.py가 v3 라우터를 include하지 않음**  
   현재 `main.py`는 v3가 아닌 경로를 import하고 있어, 그대로 실행하면 실패할 수 있습니다.  
   v3 라우터만 동작하게 하려면 `main.py`에서 아래를 include하는 형태가 필요합니다.
   - `from src.apis.v3.asset import router as v3_asset_router`
   - `from src.apis.v3.project import router as v3_project_router`

3) **DP 업로드 endpoint 버전**  
   v3 API 서버지만, DP는 `openapi/v2` endpoint를 사용합니다.  
   (정상입니다. 서버 버전과 DP API 버전은 별개일 수 있습니다.)

---

## 13. 다음 단계(추가 개발을 위한 “코드 분석” 진행 방식)

이 MD는 “전체 구조 이해”용입니다.  
추가 개발을 정확히 하려면, 다음 3가지를 코드 레벨로 더 파고들면 됩니다.

1) `cam-json`의 **입력 포맷(JSON 스키마/필수필드)** 를 확정  
2) `append_ws_into_project_xml`가 **workingstep을 어떤 위치/형태로 넣는지**를 정확히 확인  
3) `build_cutting_tool_13399_dtasset_xml`가 생성하는 **dt_cutting_tool_13399 XML 구조**와  
   DP에서 요구하는 필드/태그가 맞는지 검증

원하시면 다음 문서로 이어서:
- `cam-json` 요청/응답 예시
- workingstep 추가 전/후 XML diff
- dt_cutting_tool_13399 생성 예시 XML
까지 “실제 샘플 기반”으로 더 상세하게 정리해드릴 수 있습니다.

---

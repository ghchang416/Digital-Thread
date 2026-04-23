# VM_middle — Virtual Machining Middleware

> ISO 14649 기반 Digital Thread 시스템과 Virtual Machining(VM) 시뮬레이션 서버를 연결하는 **미들웨어 백엔드**

---

## 1. 프로젝트 개요

`VM_middle`은 **ISO 14649 표준 기반 제조 데이터 관리 시스템(ISO API)**과 **클라우드 VM 시뮬레이션 서버(UNI CNC Solutions)**를 중계하는 FastAPI 기반 미들웨어이다.

### 핵심 역할
- ISO API에서 가공 프로젝트(dt_project), 소재(dt_material), 공구(dt_cutting_tool), NC파일(dt_file) 데이터를 수집
- 수집된 데이터를 VM 시뮬레이션에 필요한 형식(project.prj + ncdata.zip)으로 변환
- VM 서버에 시뮬레이션 작업(Job)을 생성하고, 완료될 때까지 폴링
- VM 결과(시뮬레이션 ZIP)를 다시 ISO 시스템에 dt_file 형태로 등록 (Closed-Loop)

---

## 2. 기술 스택

| 구분 | 기술 | 비고 |
|------|------|------|
| **Framework** | FastAPI (0.110+) | 비동기 REST API |
| **Runtime** | Python 3.10 (conda) | Dockerfile 기준 |
| **Database** | MongoDB (비동기, Motor 3.5+) | vm_project / vm_file 컬렉션 |
| **File Storage** | MongoDB GridFS | NC ZIP, Project JSON 저장 |
| **HTTP Client** | httpx 0.27+ | 비동기 HTTP 통신 |
| **XML Processing** | xmltodict, lxml, defusedxml | ISO 14649 XML 파싱 |
| **Scheduler** | APScheduler 3.10+ | (설정은 있으나 현재 asyncio loop 사용) |
| **Container** | Docker (Miniconda base) | uvicorn으로 서빙 |

---

## 3. 디렉토리 구조

```
VM_middle/
├── .env                    # 환경 변수 (VM 서버 인증 정보, ISO/DP API URL 등)
├── dockerfile              # Docker 빌드 설정 (conda + Python 3.10)
├── requirements.txt        # Python 의존성 목록
├── data/                   # (비어 있음, 정적 데이터용 예약)
├── tmp/                    # (비어 있음, NC 분할 작업 임시 디렉토리)
└── src/
    ├── main.py             # FastAPI 앱 + 라이프사이클(startup/shutdown)
    ├── database.py         # FastAPI Depends 기반 DI 팩토리
    ├── api/
    │   └── v1/
    │       ├── iso.py          # [GET] /api/v1/iso-projects — ISO 프로젝트 목록 조회
    │       └── vm_project.py   # /api/v1/vm-project — VM 프로젝트 CRUD + VM 실행
    ├── clients/
    │   ├── http.py         # 범용 비동기 HTTP 클라이언트 (재시도 지원)
    │   └── iso.py          # ISO API 전용 클라이언트 (글로벌 자산, 프로젝트, 에셋 조회)
    ├── core/
    │   ├── config.py       # pydantic-settings 기반 설정 (Settings 싱글톤)
    │   └── db.py           # MongoDB 연결 관리 + 인덱스 생성
    ├── dao/
    │   ├── files.py        # GridFS 파일 저장/조회/삭제 (GridFSFileStore)
    │   ├── vm_file.py      # vm_file 컬렉션 DAO (nc-split-zip, vm-project-json)
    │   └── vm_project.py   # vm_project 컬렉션 DAO (상태 관리, 폴링 정보 갱신)
    ├── schemas/
    │   ├── iso.py          # ISO 프로젝트 리스트 응답 스키마
    │   └── vm_project.py   # VM 프로젝트 입출력 스키마 (상태, Stock, Process 등)
    ├── services/
    │   ├── vm_file.py      # 파일 → GridFS 업로드 서비스
    │   └── vm_project.py   # ★ 핵심 비즈니스 로직 (1,849줄)
    └── utils/
        ├── nc_splitter.py  # NC 프로그램 분할 (공구 교환 기준), 리넘버링
        ├── stock.py        # 소재 타입 코드 매핑 (알루미늄, 강재, 티타늄 등 23종)
        └── xml_parser.py   # ISO 14649 XML 파싱 유틸리티 모음
```

---

## 4. 주요 기능

### 4.1 ISO 프로젝트 조회 (`/api/v1/iso-projects`)

ISO API로부터 가공 프로젝트 목록을 조회하고, dt_project XML에서 요약 정보를 추출한다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/iso-projects` | ISO 프로젝트 목록 (gid 필터, 페이지네이션) |

- 글로벌 에셋 ID(gid) 기반으로 프로젝트 순회
- 각 프로젝트의 dt_project XML에서 description, main_workplan id, workplan 목록 추출
- 응답 스키마: `ProjectRow` (gid, aid, eid, name, description, main_wpid, wpid[])

### 4.2 VM 프로젝트 생성 (`POST /api/v1/vm-project`)

ISO 프로젝트 키(gid, aid, eid, wpid)를 입력받아 VM 시뮬레이션 프로젝트를 생성하는 **풀 파이프라인**:

```
ISO 프로젝트 키 입력
  → dt_project XML 조회
    → dt_material XML에서 소재(Stock) 정보 추출
    → 워크플랜 → 워킹스텝 순서대로 공구 참조 추출
    → dt_file 매칭 → NC 파일 다운로드
    → NC 프로그램을 공구 교환(T*M6) 기준으로 분할
    → 각 세그먼트 리넘버링, 종료코드(M30) 보정
    → 워킹스텝별 공구 XML 파싱 → tool_data(CSV) 구성
    → project.prj(JSON) + ncdata.zip 생성
    → MongoDB GridFS에 저장
    → 유효성 검증 → 상태(ready/needs-fix) 결정
```

### 4.3 VM 프로젝트 관리

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/vm-project` | VM 프로젝트 목록 (상태/gid/aid/검색 필터) |
| `GET` | `/api/v1/vm-project/{id}` | VM 프로젝트 상세 조회 |
| `GET` | `/api/v1/vm-project/{id}/project-file` | project.prj 내용 조회 (DB draft 또는 GridFS 파일) |
| `PATCH` | `/api/v1/vm-project/{id}/project-file/stock` | Stock(소재) 정보 수정 |
| `PATCH` | `/api/v1/vm-project/{id}/project-file/process` | Process(가공 공정) 정보 수정 |
| `GET` | `/api/v1/vm-project/stocks` | 사용 가능한 Stock 타입 목록 (정적, 23종) |
| `POST` | `/api/v1/vm-project/{id}/start-vm` | VM 시뮬레이션 시작 요청 |

### 4.4 VM 시뮬레이션 실행 (`start-vm`)

```
status=ready 확인
  → GridFS에서 project.prj + ncdata.zip 바이트 로드
  → VM S3 업로드 API (/s3-upload)로 파일 전송
  → VM 인증 토큰 발급 (username/password)
  → VM Job 생성 API (/api/v1/macsim) 호출
  → status → running + vm_job_id 기록
```

### 4.5 VM 상태 폴링 (백그라운드 루프)

앱 시작 시 `asyncio.create_task`로 백그라운드 폴링 루프가 실행된다:

```
매 N초(기본 300초)마다:
  → status='running'인 모든 vm_project 조회
  → VM 토큰 1회 발급
  → 각 프로젝트의 vm_job_id로 VM 상태 API 폴링
    → WAIT / RUN  → 계속 running 유지
    → ERROR       → status = failed
    → COMPLETE    → VM 결과 다운로드 링크 확보
                    → ISO에 VM dt_file XML 등록 (Closed-Loop)
                    → status = completed
```

### 4.6 VM 결과 → ISO 등록 (Closed-Loop)

VM 시뮬레이션이 완료(`COMPLETE`)되면:

1. 기존 VM dt_file 들의 `SEQ_ID` 최댓값을 계산하여 다음 번호 결정
2. `vm_001`, `vm_002` ... 형식의 asset_id/element_id 생성
3. `make_vm_dt_file_xml()`로 dt_file XML 생성 (S3 다운로드 링크 포함)
4. ISO API (`POST /api/v3/assets`)에 multipart로 등록

---

## 5. 상태 머신 (VM Project Lifecycle)

```
┌──────────┐
│ needs-fix │◄────── 유효성 검증 실패
└────┬─────┘
     │ stock/process 수정 후 재검증 통과
     ▼
┌──────────┐
│  ready   │◄────── 유효성 검증 통과 (초기 생성 시 또는 수정 후)
└────┬─────┘
     │ POST /{id}/start-vm
     ▼
┌──────────┐
│ running  │◄────── VM Job 생성 성공, 폴링 중
└────┬─────┘
     │ 폴링 결과에 따라 분기
     ├──────────────────────┐
     ▼                      ▼
┌───────────┐         ┌──────────┐
│ completed │         │  failed  │
│ (+ ISO    │         │          │
│  등록완료) │         └──────────┘
└───────────┘
```

### 상태별 허용 동작

| 상태 | Stock/Process 수정 | VM 시작 | 폴링 대상 |
|------|:------------------:|:-------:|:---------:|
| `needs-fix` | ✅ | ❌ | ❌ |
| `ready` | ✅ | ✅ | ❌ |
| `running` | ❌ | ❌ | ✅ |
| `completed` | ❌ | ❌ | ❌ |
| `failed` | ❌ | ❌ | ❌ |

---

## 6. 외부 시스템 연동

### 6.1 ISO API (ISO 14649 Data Platform)

```
VM_middle ──HTTP──► ISO API (iso-api:8000)
```

| 용도 | 엔드포인트 | 방향 |
|------|-----------|:----:|
| 글로벌 에셋 목록 | `GET /api/v3/assets/global-assets` | → |
| 프로젝트 목록 | `GET /api/v3/projects?global_asset_id=` | → |
| 프로젝트 상세(XML) | `GET /api/v3/projects/{eid}` | → |
| 에셋 상세(XML) | `GET /api/v3/assets/{eid}?type=dt_material\|dt_cutting_tool_13399\|dt_file` | → |
| 에셋 목록 | `GET /api/v3/assets?global_asset_id=&type=` | → |
| NC 파일 다운로드 | `GET /api/v3/assets/file-download?global_asset_id=&asset_id=&element_id=` | → |
| VM 결과 dt_file 등록 | `POST /api/v3/assets` (multipart: xml) | → |

**주요 데이터 흐름:**
- **dt_project XML** → 워크플랜/워킹스텝 구조 파싱, 소재·공구 참조 추출
- **dt_material XML** → 소재 종류(Aluminum 7075-T6 등) + 치수(stock_size) 추출
- **dt_cutting_tool_13399 XML** → 유효 직경, 코너 반경, 날 수 등 공구 파라미터 추출
- **dt_file XML** → NC 파일 참조(프로젝트/워크플랜 키 매칭), 파일 다운로드

### 6.2 VM 서버 (UNI CNC Solutions)

```
VM_middle ──HTTPS──► api.unicncsolutions.com
```

| 용도 | 엔드포인트 | 방향 |
|------|-----------|:----:|
| 파일 업로드(S3) | `POST /s3-upload?parent_path=` | → |
| 인증 토큰 발급 | `POST /api/v1/auths/login/access-token` | → |
| 시뮬레이션 Job 생성 | `POST /api/v1/macsim` | → |
| Job 상태 조회 | `GET /api/v1/macsim/{macsim_id}` | → |

**인증:** Form-data 방식 username/password → access_token (Bearer)

**Job 생성 파라미터:**
- `machine_name`: ISO 프로젝트 element_id
- `upload_file_link1`: S3에 업로드된 project.prj 경로
- `upload_file_link2`: S3에 업로드된 ncdata.zip 경로

**Job 상태값:**
| VM state | MW 매핑 상태 |
|----------|-------------|
| `WAIT` | running |
| `RUN` | running |
| `COMPLETE` | completed |
| `ERROR` / `ERROR-AppsPro Down` | failed |

### 6.3 MongoDB

```
VM_middle ──async──► MongoDB (mongo:27017 / vm_mw DB)
```

**컬렉션:**

| 컬렉션 | 용도 | 주요 필드 |
|--------|------|----------|
| `vm_project` | VM 프로젝트 상태·메타데이터 | source, gid, aid, eid, wpid, status, project_file_draft, vm_job_id, validation |
| `vm_file` | 생성된 파일(prj, zip) 메타 | vm_project_id, kind, gridfs_id, original_name |
| `files.files` / `files.chunks` | GridFS 파일 본문 | (GridFS 표준 구조) |

**주요 인덱스:**
- `vm_project`: (source, gid, aid, eid, wpid, created_at), (status, created_at), (vm_id)
- `vm_file`: (vm_project_id, kind, created_at), (meta.origin.gid/aid/eid, created_at)

### 6.4 DP API (선택적)

```
VM_middle ──HTTP──► DP API (220.75.173.230:20220)
```

설정에 `DP_API_URL`이 정의되어 있으나, 현재 코드에서는 ISO를 기본 데이터 소스로 사용 (`SOURCE_DEFAULT: str = "iso"`).

---

## 7. 데이터 변환 상세

### 7.1 NC 프로그램 분할 (`nc_splitter.py`)

원본 NC 파일을 **공구 교환(Tool Change: T*M6 / M6T*)** 기준으로 분할:

1. 프리앰블(공구 교환 전 라인) 분리
2. O번호(프로그램 번호) 추출 및 세그먼트별 재생성 (O1001, O1002 ...)
3. N 라인번호 포맷 감지(패딩 여부, 자릿수) 후 리넘버링 (N10, N20 ...)
4. 종료코드(M30/M02) 정규화: 중간 세그먼트에는 M30 보장, 마지막은 원본 유지
5. 각 세그먼트에 `%` 시작/종료 마커 부여
6. 저장: `ncdata/<stem>_1/<stem>_1.nc`, `ncdata/<stem>_2/<stem>_2.nc` ...

### 7.2 Project File (project.prj) 구조

```json
{
  "stock_type": 9,                // 소재 코드 (23종 중 택1)
  "stock_size": "0,100,0,50,0,20", // x_min,x_max,y_min,y_max,z_min,z_max
  "process_count": 3,
  "process": [
    {
      "file_path": "ncdata\\program_1\\program_1.nc",   // NC 파일 상대경로
      "output_dir_path": "result\\program_1",           // 결과 출력 경로
      "tool_data": "1,10.000000,0.500000,4.500000,0.500000,null,null,null,4.000000"
      // T번호, 유효직경, 코너반경, (유효직경/2-코너반경), 코너반경, null*3, 날수
    }
  ]
}
```

### 7.3 소재 매핑 (`stock.py`)

ISO dt_material XML의 `material_identifier` 또는 `display_name`을 23종의 사전 정의된 소재 코드로 매핑:
- 예: `"Aluminum 7075-T6"` → `code: 9`
- 매칭은 **정확한 문자열 일치** (정규화/소문자화 없음)

### 7.4 XML 파싱 (`xml_parser.py`)

네임스페이스-무관(namespace-agnostic) 방식으로 ISO 14649 XML을 파싱:

| 함수 | 용도 |
|------|------|
| `parse_material_xml()` | dt_material → material_identifier, 치수(coordinates_mm, min/max) |
| `extract_material_ref_from_project_xml()` | dt_project → ref_dt_material 참조 (gid, aid, eid) 추출 |
| `extract_tool_refs_in_order()` | dt_project → 워킹스텝별 공구 참조 순서 추출 |
| `parse_cutting_tool_13399_xml()` | dt_cutting_tool_13399 → numerical_value 맵 (직경, 반경, 날수) |
| `parse_dt_file_xml()` | dt_file → element_id, category, 참조키(DT_GLOBAL_ASSET 등) |
| `match_dt_file_refs()` | dt_file 참조와 프로젝트 키 일치 여부 판단 |
| `make_vm_dt_file_xml()` | VM 결과를 ISO에 등록할 dt_file XML 생성 |
| `extract_project_summary()` | dt_project → description, workplan IDs 요약 |

---

## 8. 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│                        VM_middle (FastAPI)                       │
│                                                                 │
│  ┌───────────┐   ┌──────────────┐   ┌───────────────────────┐  │
│  │ API Layer │──►│ Service Layer│──►│     DAO Layer         │  │
│  │ (v1/iso,  │   │ (VmProject   │   │ (VmProjectDAO,       │  │
│  │  v1/vm_   │   │  Service)    │   │  VmFileDAO,          │  │
│  │  project) │   │              │   │  GridFSFileStore)     │  │
│  └───────────┘   └──────┬───────┘   └───────────┬───────────┘  │
│                         │                       │               │
│                    ┌────┴────┐            ┌─────┴─────┐        │
│                    │ Utils   │            │ MongoDB   │        │
│                    │ (xml_   │            │ (Motor)   │        │
│                    │ parser, │            │ - vm_project│       │
│                    │ nc_     │            │ - vm_file  │        │
│                    │ splitter│            │ - GridFS   │        │
│                    │ stock)  │            └───────────┘        │
│                    └─────────┘                                  │
│                         │                                       │
│         ┌───────────────┼───────────────────────┐              │
│         │               │                       │              │
│         ▼               ▼                       ▼              │
│  ┌────────────┐  ┌──────────────┐    ┌──────────────────┐     │
│  │ ISO API    │  │ VM Server    │    │ Background       │     │
│  │ Client     │  │ Client       │    │ Polling Loop     │     │
│  │ (iso.py)   │  │ (httpx)      │    │ (asyncio task)   │     │
│  └─────┬──────┘  └──────┬───────┘    └───────┬──────────┘     │
└────────┼────────────────┼────────────────────┼────────────────┘
         │                │                    │
         ▼                ▼                    ▼
  ┌──────────────┐ ┌──────────────┐   (매 300초마다
  │ ISO 14649    │ │ UNI CNC      │    running 프로젝트
  │ Data Platform│ │ Solutions    │    상태 폴링)
  │ (iso-api:    │ │ (api.unicnc  │
  │  8000)       │ │  solutions.  │
  │              │ │  com)        │
  └──────────────┘ └──────────────┘
```

---

## 9. 실행 방법

### 로컬 (conda)

```bash
conda create -n myenv python=3.10
conda activate myenv
pip install -r requirements.txt

# MongoDB 실행 필요 (기본: mongodb://mongo:27017)
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker

```bash
docker build -f dockerfile -t vm-middle .
docker run -p 8000:8000 --env-file .env vm-middle
```

### 환경 변수 (`.env`)

| 변수명 | 기본값 | 설명 |
|--------|--------|------|
| `MONGO_URI` | `mongodb://mongo:27017` | MongoDB 연결 URI |
| `MONGO_DB` | `vm_mw` | 데이터베이스 이름 |
| `ISO_API_URL` | `http://iso-api:8000` | ISO 14649 API 주소 |
| `VM_API_URL` | `https://api.unicncsolutions.com` | VM 서버 API 주소 |
| `VM_USERNAME` | (설정 필요) | VM 서버 로그인 계정 |
| `VM_PASSWORD` | (설정 필요) | VM 서버 로그인 비밀번호 |
| `DP_API_URL` | `http://220.75.173.230:20220` | DP API 주소 (선택) |
| `VM_POLL_INTERVAL_SEC` | `300` | VM 폴링 간격 (초) |
| `POLL_TIMEOUT_SEC` | `7200` | VM 폴링 타임아웃 (초) |
| `LOG_LEVEL` | `DEBUG` | 로그 레벨 |

---

## 10. API 엔드포인트 요약

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/healthz` | 헬스체크 |
| `GET` | `/api/v1/iso-projects` | ISO 프로젝트 목록 + 요약 |
| `POST` | `/api/v1/vm-project` | VM 프로젝트 생성 (풀 파이프라인) |
| `GET` | `/api/v1/vm-project` | VM 프로젝트 목록 |
| `GET` | `/api/v1/vm-project/stocks` | Stock 타입 목록 |
| `GET` | `/api/v1/vm-project/{id}` | VM 프로젝트 상세 |
| `GET` | `/api/v1/vm-project/{id}/project-file` | Project File 조회 |
| `PATCH` | `/api/v1/vm-project/{id}/project-file/stock` | Stock 정보 수정 |
| `PATCH` | `/api/v1/vm-project/{id}/project-file/process` | Process 정보 수정 |
| `POST` | `/api/v1/vm-project/{id}/start-vm` | VM 시뮬레이션 시작 |

---

## 11. 데이터 흐름 요약 (End-to-End)

```
[ISO 14649 Platform]                [VM_middle]                    [VM Server (UNI CNC)]
       │                                │                                │
       │ ◄─── GET projects/assets ──── │                                │
       │ ────► XML (project, material,  │                                │
       │        tool, dt_file) ────────►│                                │
       │                                │                                │
       │ ◄─── GET file-download ────── │                                │
       │ ────► NC text ───────────────►│                                │
       │                                │── NC Split + Build             │
       │                                │   project.prj                  │
       │                                │   ncdata.zip                   │
       │                                │── Store to GridFS/MongoDB      │
       │                                │                                │
       │                                │── POST /s3-upload ────────────►│
       │                                │── POST /auths/login ──────────►│
       │                                │◄── access_token ──────────────│
       │                                │── POST /macsim ───────────────►│
       │                                │◄── job_id, state ─────────────│
       │                                │                                │
       │                                │   (polling loop, every 300s)   │
       │                                │── GET /macsim/{id} ───────────►│
       │                                │◄── state: WAIT/RUN/COMPLETE ──│
       │                                │                                │
       │                                │   (when COMPLETE)              │
       │ ◄── POST /assets (dt_file) ── │◄── download_file_link ────────│
       │     (VM result XML with        │                                │
       │      S3 download link)         │                                │
       │                                │                                │
```

---

## 12. 유효성 검증 규칙

프로젝트 파일(project.prj)에 대해 VM 실행 전 유효성 검증을 수행한다. 실패 시 `status = needs-fix`:

| 항목 | 검증 규칙 |
|------|----------|
| `stock_type` | 필수, 사전 정의된 23종 코드 중 하나 |
| `stock_size` | 필수, 6개 숫자 콤마 구분 (x_min,x_max,y_min,y_max,z_min,z_max) |
| `process[]` | 최소 1개 이상 |
| `process[].file_path` | 비어 있으면 안 됨 |
| `process[].output_dir_path` | 비어 있으면 안 됨 |
| `process[].tool_data` | 9개 필드 콤마 구분, `null` 포함 시 에러 |
| NC ↔ WS 공구번호 | NC T번호와 워킹스텝 공구 번호 일치 검증 |

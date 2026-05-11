# VM Middle 작업 변경 이력

## 개요

VM Middle은 ISO 14649 기반의 디지털 스레드 플랫폼에서 가상가공(VM) 시뮬레이션을 관리하는 미들웨어입니다.
본 문서는 최근 진행된 주요 기능 추가 및 버그 수정 내역을 정리합니다.

---

## 문서 운영 원칙

앞으로 `VM_middle`에서 실제 개발한 내용은 이 문서에 계속 누적한다.

각 개발 내역은 가능하면 아래 순서로 작성한다.

1. 개발 배경: 왜 수정했는지, 어떤 사용자/운영 문제가 있었는지
2. 적용 범위: 수정한 파일과 영향받는 API
3. 구현 방식: 핵심 로직, 분기 조건, 기존 흐름과의 관계
4. 호환성/주의사항: 기존 DP/ISO/VM 동작에 영향을 주지 않기 위해 지킨 제약
5. 검증 내역: 실행한 명령, 컨테이너 기준 API 확인 결과
6. 남은 작업: 프론트 연결, 추가 테스트, 운영 반영 항목

특히 DP 연동은 이미 정상 동작 중인 VM 생성/NC 처리 흐름이 있으므로, 새 기능은 기존 경로를 직접 수정하기보다 가능한 한 독립된 함수/엔드포인트로 추가한다.

---

## 2026-05-08 — NC Toolpath + Stock 3D Alignment 구현

### 개발 배경
- Project Detail의 Stock 섹션에서 소재 min/max box와 NC toolpath를 같은 3D 좌표계에 겹쳐 표시하도록 구현했다.
- 목적은 VM 실행 전 소재 위치가 툴패스 범위와 맞는지 빠르게 확인하는 것이다.
- 소재 좌표는 저장 전 입력 draft도 즉시 반영되도록 하여, 사용자가 stock 값을 조정하면서 3D overlay를 확인할 수 있게 했다.

### 적용 범위
- 백엔드
  - `src/utils/nc_parser.py`
  - `src/utils/toolpath_preview.py`
  - `src/schemas/vm_project.py`
  - `src/services/vm_project.py`
  - `src/api/v1/vm_project.py`
- 프론트엔드
  - `frontend/src/features/vm-projects/api/vm-projects-api.ts`
  - `frontend/src/features/vm-projects/types/vm-project.ts`
  - `frontend/src/features/vm-projects/components/project-detail-drawer.tsx`
  - `frontend/src/features/vm-projects/components/toolpath-alignment-viewer.tsx`
  - `frontend/src/features/vm-projects/components/toolpath-alignment-canvas.tsx`
  - `frontend/src/shared/styles/base.css`
  - `frontend/vite.config.ts`
- 의존성
  - `three`
  - `@types/three`

### 구현 방식
- `GET /api/v1/vm-project/{id}/toolpath-preview` API를 추가했다.
- API는 VM 프로젝트의 `latest_files["nc-split-zip"]`에서 `ncdata.zip`을 읽고, `project_file_draft.process[].file_path`와 zip 내부 NC 파일을 매칭한다.
- 매칭된 NC 파일은 `src/utils/nc_parser.py`로 승격한 `NCParser`로 파싱해 `start`, `end`, `type`, `feedrate`, `mode`, arc 메타데이터를 포함한 segment JSON으로 변환한다.
- 최초 구현 때 `data/nc_visualizer_tool`을 직접 import하던 방식은 제거했다. `data` 폴더는 git/배포 대상이 아니므로, 실제 런타임 소스는 `src/utils/nc_parser.py`만 바라보게 정리했다.
- 응답에는 stock box, toolpath bounds, segment 목록, process별 file summary, segment type count, sampling 상태를 포함한다.
- 큰 NC 파일 대응을 위해 `max_segments` query를 두고, 전체 segment가 제한을 넘으면 균등 sampling으로 반환한다. 기본값은 `20000`, 최대값은 `50000`이다.
- React에서는 `toolpath-preview`를 독립 TanStack Query로 분리하고, Stock/Process 저장 성공 및 VM action 후 관련 query를 invalidate한다.
- Three.js viewer는 lazy import로 분리해 초기 bundle에 Three.js를 직접 포함하지 않게 했다.
- viewer는 소재 box를 반투명 박스와 edge line으로 표시하고, toolpath는 segment type별 색상 라인으로 표시한다.
- 좌표계는 NC `[x, y, z]`를 Three.js `[x, z, y]`로 매핑해 기계 Z축이 화면의 vertical 축으로 보이게 했다.
- `ISO`, `TOP`, `FRONT`, `SIDE`, `FIT` 뷰 버튼을 추가했다.

### 호환성/주의사항
- VM 실행 payload와 `project.prj` 포맷은 변경하지 않았다.
- 3D preview는 읽기 전용 표시 API이며, stock 저장 전 draft 변경은 프론트 상태에만 반영된다.
- 원호는 현재 `NCParser`가 제공하는 start/end chord 기준으로 표시하며, arc interpolation은 다음 개선 항목으로 남겼다.
- `ncdata.zip`이 없거나 파일 매칭에 실패해도 API는 500으로 실패하지 않고 빈 preview와 `summary.errors`를 반환하도록 했다.

### 검증 내역
- `docker exec vm_middle python -m py_compile ...`로 변경된 FastAPI 파일 문법 검증 통과.
- 실제 VM 프로젝트 `iso301 vm test project` 기준 toolpath preview API 응답 확인.
  - stock bounds: `[-51,-41,-50]` ~ `[51,41,1]`
  - toolpath bounds: `[-75,-49.038,-40.997]` ~ `[73,48.1,150]`
  - segment: `6869`개 반환, errors 없음.
- `docker exec vm_middle_front npm run typecheck` 통과.
- `docker exec vm_middle_front npm run build` 통과.
- FastAPI `/ui/` 정적 asset 및 lazy Three.js chunk 200 응답 확인.
- 브라우저에서 Project Detail > Stock 영역을 열어 3D canvas 렌더링 확인.
- `x_max`를 `51`에서 `101`로 임시 변경했을 때 저장 없이 `x_span`이 `102 mm`에서 `152 mm`로 즉시 변경되고 소재 box가 갱신되는 것을 확인한 뒤 원복했다.

### 남은 작업
- G2/G3 원호 interpolation을 추가해 곡선 toolpath 표시 정확도를 높인다.
- 매우 큰 NC 파일은 서버 캐시 또는 precomputed preview 저장 방식으로 응답 시간을 더 줄일 수 있다.
- toolpath process별 on/off 필터, segment type 필터, stock/toolpath bounds 자동 비교 경고를 추가할 수 있다.

---

## 2026-05-08 — NC Toolpath 3D 표시 기능 사전 분석

### 개발 배경
- Project Detail의 Stock 섹션에 추가한 `Toolpath Alignment` 영역을 실제 기능으로 확장하기 위해, `data/nc_visualizer_tool` 아래 기존 시각화 도구를 분석했다.
- 목표는 NC 파일에서 추출한 툴패스 좌표와 `project_file_draft.stock_size`의 소재 min/max 박스를 같은 3D 좌표계에 표시해 소재 위치가 툴패스와 맞는지 확인하는 것이다.

### 적용 범위
- `data/nc_visualizer_tool/libs/occ_viewer/README.md`
- `data/nc_visualizer_tool/libs/occ_viewer/interaction.py`
- `data/nc_visualizer_tool/libs/nc_toolkit/README.md`
- `data/nc_visualizer_tool/libs/nc_toolkit/nc_parser.py`
- `data/nc_visualizer_tool/libs/nc_toolkit/dnc_sender.py`
- `data/test_data/merge.tap`

### 분석 결과
- `occ_viewer`는 `pythonOCC(OpenCASCADE)`와 `PySide6` 기반의 데스크톱 3D 뷰어 인터랙션 모듈이다.
- `occ_viewer`는 `AIS_ViewController`, `AIS_AnimationCamera`, `QTimer`, Qt mouse event에 강하게 의존하므로 React 브라우저 UI에 직접 재사용하기는 어렵다.
- 다만 ViewCube, 회전, 이동, 줌, 선택, fit-to-view 같은 3D 조작 UX는 React Three.js viewer 설계에 참고할 수 있다.
- `nc_toolkit`의 `NCParser`는 Python 표준 라이브러리만 사용하는 NC/G-Code 파서이므로 FastAPI 백엔드에서 재사용 가능하다.
- `NCParser.parse_as_segments()`는 `start`, `end`, `type`, `feedrate`, `mode`, 원호용 `arc_i/j/k`를 포함한 segment 목록을 반환한다.
- `dnc_sender`는 NC Main/Sub 프로그램 변환과 DNC 전송 placeholder 성격이므로 이번 3D 표시 기능에는 직접 사용하지 않는다.

### 샘플 검증
- `data/test_data/merge.tap`를 `NCParser.parse_as_segments()`로 파싱했다.
- 결과는 segment `6883`개이며, 유형별로 `FEED 6798`, `RAPID 66`, `SKIM 17`, `PLUNGE 2`가 추출되었다.
- 추출된 toolpath bounds는 `x=-75.0~73.0`, `y=-49.038~48.1`, `z=-40.997~150.0`이었다.
- G2/G3 원호 segment는 `225`개로 감지되었다.

### 구현 방향
- 백엔드에 `GET /api/v1/vm-project/{id}/toolpath-preview` API를 추가한다.
- API는 `latest_files["nc-split-zip"]`에서 `ncdata.zip`을 읽고, `project_file_draft.process[].file_path` 기준으로 NC 파일을 찾아 `NCParser`로 segment JSON을 생성한다.
- API 응답에는 stock min/max, toolpath bounds, segment 목록, segment type별 count, process별 file summary를 포함한다.
- 프론트는 기존 `Toolpath Alignment` placeholder를 Three.js 기반 3D viewer로 교체하고, stock box와 toolpath polyline을 같은 좌표계에 렌더링한다.
- 원호는 1차 구현에서는 start/end chord로 표시하고, 이후 arc interpolation을 추가해 곡선 정확도를 높인다.

### 호환성/주의사항
- `project.prj` 포맷과 VM 실행 payload는 변경하지 않는다.
- 3D preview 데이터는 UI 표시용 API 응답으로만 제공하며, VM 실행에 필요한 `project_file_draft`에는 새로운 시각화 메타데이터를 섞지 않는다.
- 큰 NC 파일은 segment 수가 많을 수 있으므로 API에서 `max_segments` 또는 sampling/truncation 정책을 둔다.
- `nc_toolkit` README에는 원호 16분할 보간이 언급되어 있으나, 현재 `nc_parser.py` 구현은 원호 정보를 보존할 뿐 실제 중간점 보간은 수행하지 않는다.

### 남은 작업
- 백엔드 schema/service/router 추가
- `ncdata.zip` GridFS 로드 및 zip 내부 파일 매칭 구현
- React API/type/query 추가
- Three.js 또는 경량 canvas 기반 3D viewer 구현
- 실제 VM 프로젝트 데이터와 샘플 `merge.tap` 기준 화면 검증

### 구현 계획 문서
- `docs/toolpath_alignment_implementation_plan.md`를 작성했다.
- 문서에는 백엔드 `toolpath-preview` API, `NCParser` 활용 방식, `ncdata.zip` GridFS 로드, zip 내부 NC 파일 매칭, segment 제한 정책, React TanStack Query 연결, Three.js viewer, stock 좌표 live preview, 검증 계획을 포함했다.
- 핵심 설계는 toolpath는 서버 API segment를 사용하고, 소재 box는 현재 Stock form draft 값을 우선 사용해 저장 전에도 3D viewer에 즉시 반영하는 방식이다.

---

## 2026-05-07 — React frontend Skill 활용 보고서 작성

### 개발 배경
- React 프론트 전환 과정에서 사용한 `vercel-react-best-practices`와 `impeccable` skill의 역할을 보고서/PPT 자료로 설명할 필요가 있었다.
- 단순 적용 내역이 아니라, 각 skill의 구성 방식과 VM Middle 프론트 구조 및 디자인 개선에 어떻게 반영되었는지를 문서화했다.

### 적용 범위
- `docs/react_frontend_skill_usage_report.md`

### 구현 방식
- Vercel skill의 8개 규칙 범주와 VM Middle 적용 항목을 정리했다.
- Impeccable skill의 `PRODUCT.md`, `DESIGN.md`, register, preflight gate, command 체계를 정리했다.
- React frontend 구조, 데이터 흐름, 디자인 수정 절차, 검증 방식, 향후 3D Toolpath Alignment 확장 방향을 PPT용 슬라이드 구성안과 상세 본문으로 분리해 작성했다.

### 검증 내역
- 문서 전용 변경으로 frontend typecheck/build는 실행하지 않았다.
- 작성된 Markdown 내용을 확인해 보고서 목차와 skill 설명이 포함된 것을 검토했다.

---

## 2026-05-07 — React 생성 workflow 1차 연결

### 개발 배경
- 정적 HTML 기반 VM Middle UI를 React 프론트로 전환하는 과정에서, placeholder 상태였던 VM 프로젝트 생성 영역을 실제 DP/ISO 소스 선택 workflow로 연결했다.
- 이번 작업은 Vercel React Best Practices의 feature/API 분리, TanStack Query 기반 server state 관리, 직접 import 원칙을 따르고, Impeccable의 제품형 콘솔 원칙에 맞춰 KITECH 컬러 토큰과 조밀한 운영 UI 패턴을 적용했다.

### 적용 범위
- `frontend/src/features/source-projects/`
  - DP 프로젝트 목록 조회
  - DP workplan 조회
  - ISO 프로젝트 목록 조회
  - 소스 프로젝트 선택 패널
- `frontend/src/features/vm-projects/`
  - `POST /api/v1/vm-project` 생성 mutation 추가
  - 생성 payload/response 타입 추가
- `frontend/src/app/app.tsx`
  - 기존 생성 placeholder를 `SourceProjectPanel`로 교체
  - 생성 성공 시 VM 프로젝트 목록 invalidate 후 상세 drawer 오픈
- `frontend/src/shared/styles/base.css`
  - segmented control, source list, pager, workplan radio, primary button, success/error notice 스타일 추가

### 구현 방식
- DP와 ISO 목록 조회는 source mode에 따라 각각 독립 query key로 분리했다.
- DP 프로젝트 선택 시 `GET /api/v1/dp/projects/workplans`로 workplan 후보를 조회하고, ISO는 응답의 `wpid` 배열 또는 `main_wpid`를 workplan 후보로 사용한다.
- 생성 payload는 백엔드 스키마와 동일하게 `source`, `gid`, `aid`, `eid`, 선택 `wpid`만 전송한다.
- 생성 성공 후 `["vm-projects"]` query를 invalidate하여 목록을 갱신하고, 응답의 `vm_project_id` 또는 `id`로 상세 drawer를 연다.

### 검증 내역
- 컨테이너 기준 `npm run typecheck` 통과.
- 컨테이너 기준 `npm run build` 통과.
- `vm_middle_front` 컨테이너에서 Vite 프록시를 통해 `GET /api/v1/dp/projects?page=0&size=1` 200 응답 확인.
- `vm_middle_front` 컨테이너에서 선택 DP 프로젝트 기준 `GET /api/v1/dp/projects/workplans` 200 응답 확인.
- `vm_middle_front` 컨테이너에서 Vite 프록시를 통해 `GET /api/v1/iso-projects?offset=0&limit=1` 200 응답 확인.
- `vm_middle` 컨테이너에서 `GET /ui/` 및 새 빌드 asset JS/CSS 200 응답 확인.

### 주의사항 및 남은 작업
- `npx impeccable detect vm_middle/frontend`는 최초 실행 시 npm registry 접근 이후 `install.mjs` 단계에서 출력 없이 멈춰 수동 종료했다. 별도 환경에서 재실행하거나 설치 상태를 확인해야 한다.
- 다음 단계는 생성된 VM 프로젝트의 stock/process 편집, validation 표시, VM start/poll/reset 액션을 상세 drawer에 연결하는 것이다.

### 기존 DP VM 프로젝트 display_name backfill

**파일**: `scripts/backfill_vm_project_display_names.py`

기존 VM 프로젝트 중 `source="dp"`이면서 `display_name`이 비어 있던 문서를 대상으로, DP 원본 프로젝트 XML을 다시 조회해 `<display_name>` 값을 채웠다.

구현 방식:
- `display_name`이 이미 있는 문서는 수정하지 않는다.
- `proj_name`은 VM Middle 내부 작업명으로 그대로 보존한다.
- `updated_at`은 건드리지 않아 기존 목록 정렬이 바뀌지 않게 했다.
- DP `aid`가 짧은 ID로 저장된 예전 문서까지 대비해 `aid`와 `gid/aid` 후보를 순서대로 시도한다.

실행 및 검증:
- dry-run `--limit 5`에서 누락 문서의 원본 `display_name` 추출 확인.
- `--apply` 실행 결과 `matched=12`, `updated=12`, `skipped=0`, `failed=0`.
- 재 dry-run 결과 `matched=0`.
- VM 프로젝트 목록 API에서 기존 날짜형 제목들이 `iso301 vm test project` 등 원본 프로젝트 이름으로 표시되는 것 확인.

### 상세 drawer validation 표시 및 Stock 편집 연결

**파일**: `frontend/src/features/vm-projects/`, `frontend/src/shared/api/client.ts`, `frontend/src/shared/styles/base.css`

VM 프로젝트 상세 drawer에서 validation 오류를 더 명확히 보고, Stock 값을 직접 수정할 수 있도록 1차 편집 workflow를 연결했다.

구현 내용:
- validation 오류를 `Stock`, `Process`, `VM`, `Other` 그룹으로 분류해 summary와 상세 목록으로 표시한다.
- validation 오류가 없을 때는 성공 상태 패널을 표시한다.
- Stock 섹션을 `stock_type`, `stock_size` 입력 form으로 변경했다.
- `GET /api/v1/vm-project/stocks`를 datalist 후보로 연결했다.
- `PATCH /api/v1/vm-project/{id}/project-file/stock` mutation을 연결했다.
- 저장 성공 시 상세 query와 목록 query를 invalidate해 validation/status를 다시 불러온다.
- `ready`, `needs-fix` 상태에서만 수정 가능하도록 UI disabled 상태를 맞췄다.

검증:
- `docker exec vm_middle_front npm run typecheck` 통과.
- `docker exec vm_middle_front npm run build` 통과.
- 컨테이너 프록시 기준 `GET /api/v1/vm-project/stocks` 200 응답 확인.
- 컨테이너 프록시 기준 VM 프로젝트 상세 API의 validation/stock 필드 응답 확인.
- FastAPI `/ui/`에서 새 빌드 asset JS/CSS 200 응답 확인.

### Stock Size 구조화 입력 UI 적용

**파일**: `frontend/src/features/vm-projects/`, `frontend/src/shared/styles/base.css`

기존 정적 UI에서 제공하던 stock size 축별 입력 경험을 React 상세 drawer에 반영했다.

구현 내용:
- `stock_size`를 한 줄 CSV 입력 대신 `x_min`, `x_max`, `y_min`, `y_max`, `z_min`, `z_max` 6개 입력으로 분리했다.
- 저장 시 백엔드 계약에 맞춰 `x_min,x_max,y_min,y_max,z_min,z_max` 순서의 CSV 문자열로 직렬화한다.
- 기존 VM 프로젝트의 CSV 값을 drawer 진입 시 축별 값으로 파싱한다.
- 비어 있는 값, 숫자가 아닌 값, 축별 min/max 역전 상태를 저장 전에 막는다.
- 현재 직렬화 결과를 작은 monospace preview로 표시해 백엔드 전송 형식을 확인할 수 있게 했다.
- `stock_type` 후보 datalist와 `ready`, `needs-fix` 상태 제한은 기존 Stock 편집 workflow를 그대로 유지했다.

검증:
- `docker exec vm_middle_front npm run typecheck` 통과.
- `docker exec vm_middle_front npm run build` 통과.
- FastAPI `/ui/`에서 새 build asset JS/CSS 200 응답 확인.

### Process 편집 1차 연결

**파일**: `frontend/src/features/vm-projects/`, `frontend/src/shared/styles/base.css`

상세 drawer의 Process 섹션을 읽기 전용 표시에서 편집 가능한 form으로 전환했다.

구현 내용:
- 각 process row에서 `file_path`, `output_dir_path`, `tool_data`를 직접 수정할 수 있게 했다.
- `tool_data`는 1차 구현으로 CSV 문자열 그대로 편집한다.
- `PATCH /api/v1/vm-project/{id}/project-file/process` mutation을 연결했다.
- 저장 payload는 백엔드 스키마에 맞게 `process` 전체 배열을 전송한다.
- 저장 성공 시 상세 query, process annotation query, 목록 query를 invalidate한다.
- validation error 중 `process[n]` 패턴을 감지해 해당 process row에 오류를 표시한다.
- `ready`, `needs-fix` 상태에서만 수정 가능하도록 UI disabled 상태를 맞췄다.

검증:
- `docker exec vm_middle_front npm run typecheck` 통과.
- `docker exec vm_middle_front npm run build` 통과.
- 상세 API에서 `process_count`, 첫 process, `process[n].tool_data` validation 오류 응답 확인.
- FastAPI `/ui/`에서 새 빌드 asset JS/CSS 200 응답 확인.
- 새 build asset 반영을 위해 `vm-middle` 컨테이너를 재시작했다.

### Tool Data 구조화 입력 및 항목 설명 복원

**파일**: `frontend/src/features/vm-projects/`, `frontend/src/shared/styles/base.css`

기존 정적 UI에 있던 공구 데이터 칸별 입력과 항목 설명 UI를 React 상세 drawer의 Process 섹션에 반영했다.

구현 내용:
- `tool_data` textarea를 `T No`, `Dia`, `Rad`, `eDis`, `fDis`, `bangl`, `sangl`, `Len`, `flut` 9개 입력으로 분리했다.
- 저장 시 기존 백엔드 계약에 맞춰 9개 값을 CSV 문자열로 직렬화한다.
- 기존 `null` placeholder는 화면에서는 빈 값으로 표시하고, 저장 payload에서는 다시 `null` 문자열로 보존한다.
- 각 process row에 현재 직렬화 결과를 작은 monospace preview로 표시한다.
- 비어 있는 항목이나 숫자가 아닌 항목은 row 안에서 inline error로 표시한다.
- `항목 설명` 버튼으로 9개 공구 필드 설명과 기존 tool guide 이미지를 inline으로 확인할 수 있게 했다.

검증:
- `docker exec vm_middle_front npm run typecheck` 통과.
- `docker exec vm_middle_front npm run build` 통과.
- FastAPI `/ui/`에서 새 build asset JS/CSS와 tool guide 이미지 200 응답 확인.

### KITECH 컬러 팔레트 기반 UI polish

**파일**: `frontend/src/shared/styles/tokens.css`, `frontend/src/shared/styles/base.css`

Impeccable product register 기준으로 React UI의 색상 token과 주요 상태 표현을 KITECH 팔레트에 맞춰 정리했다.

구현 내용:
- `--kitech-blue`, `--kitech-green`, `--kitech-muted` primitive token을 추가했다.
- semantic color token을 OKLCH 기반으로 정리해 surface, border, text, status 색이 같은 톤으로 보이게 했다.
- primary action, focus ring, selected row, selected workplan, upload mode 선택 상태를 KITECH Blue 중심으로 통일했다.
- ready/completed 상태는 KITECH Green 계열을 사용하되, 텍스트 대비를 위해 success text와 soft background를 분리했다.
- drawer 배경과 backdrop, panel shadow를 푸른 tint의 중립색으로 조정해 운영 콘솔 느낌을 강화했다.
- status badge와 validation pill에 border를 추가해 색상만으로 상태를 구분하지 않도록 보완했다.

검증:
- `docker exec vm_middle_front npm run typecheck` 통과.
- `docker exec vm_middle_front npm run build` 통과.
- FastAPI `/ui/`에서 새 build asset JS/CSS와 tool guide 이미지 200 응답 확인.

### Manufacturing Data Workbench 방향 Stock alignment 화면 추가

**파일**: `frontend/src/features/vm-projects/`, `frontend/src/shared/styles/base.css`

Project Detail drawer를 제조 데이터 작업대 흐름에 맞게 다듬고, Stock 섹션에 NC toolpath와 소재 bounds를 겹쳐 보는 위치 검증 화면의 1차 UI를 추가했다.

구현 내용:
- 상세 상단에 validation, process, stock 요약 strip을 추가했다.
- 각 상세 섹션에 eyebrow가 있는 header를 추가해 Metadata, Validation, Execution, Stock, Process의 작업 맥락을 분리했다.
- Stock 섹션을 `stock_size` 편집 form과 `Toolpath Alignment` preview가 나란히 보이는 workbench layout으로 변경했다.
- `Toolpath Alignment`는 실제 NC 파싱 연결 전 화면 구성만 제공하며, 현재는 SVG 기반 stock box와 toolpath overlay placeholder를 표시한다.
- stock box는 `stock_size` 6개 좌표에서 X/Y/Z span을 계산해 metric으로 표시한다.
- 향후 NC 파일 파싱 결과를 연결할 때 현재 preview panel에 실제 toolpath 좌표를 주입할 수 있도록 화면 영역을 먼저 확보했다.

검증:
- `docker exec vm_middle_front npm run typecheck` 통과.
- `docker exec vm_middle_front npm run build` 통과.
- FastAPI `/ui/`에서 새 build asset JS/CSS와 tool guide 이미지 200 응답 확인.

### Create VM Project 단계 strip 제거

**파일**: `frontend/src/features/source-projects/`, `frontend/src/shared/styles/base.css`

Create VM Project 패널의 `Source / Project / Workplan / Create` 단계 strip이 클릭 가능한 탭처럼 보이지만 실제 조작 기능은 없어 사용자 혼란을 줄 수 있어 제거했다.

구현 내용:
- `SourceProjectPanel`에서 단계 strip markup을 삭제했다.
- 더 이상 사용하지 않는 `.step-strip` CSS를 삭제했다.
- 생성 workflow는 기존처럼 검색, 프로젝트 선택, workplan 선택, `VM 프로젝트 생성` 버튼 순서로 유지했다.

검증:
- `docker exec vm_middle_front npm run typecheck` 통과.
- `docker exec vm_middle_front npm run build` 통과.
- FastAPI `/ui/`에서 새 build asset JS/CSS 200 응답 확인.

### VM 브랜드 마크 KITECH Green accent 적용

**파일**: `frontend/src/shared/styles/base.css`

좌상단 `VM` 브랜드 마크의 글자색을 KITECH Green accent로 변경해 KITECH 컬러 팔레트가 화면 첫 인상에서 더 명확히 보이도록 조정했다.

검증:
- `docker exec vm_middle_front npm run typecheck` 통과.
- `docker exec vm_middle_front npm run build` 통과.
- FastAPI `/ui/`에서 새 build asset JS/CSS 200 응답 확인.

### VM Start 실행 UI 연결

**파일**: `frontend/src/features/vm-projects/`, `frontend/src/shared/styles/base.css`

상세 drawer에 `VM Execution` 섹션을 추가해 VM 서버 실행 시작 workflow를 연결했다.

구현 내용:
- `ready` 상태에서만 `Start VM` 버튼을 활성화한다.
- `needs-fix`, `running`, `completed`, `failed` 상태에서는 실행 불가 이유를 표시한다.
- upload mode를 `file`, `link`, `json` 중 선택할 수 있게 했다.
- `POST /api/v1/vm-project/{id}/start-vm` mutation을 연결했다.
- 저장 payload는 `{ "upload_mode": "file" | "link" | "json" }` 형식이다.
- `json` 모드 선택 시 일부 dt_file이 먼저 등록될 수 있다는 주의 문구를 표시한다.
- 실행 성공 시 상세 query와 목록 query를 invalidate한다.

검증:
- `docker exec vm_middle_front npm run typecheck` 통과.
- `docker exec vm_middle_front npm run build` 통과.
- VM 프로젝트 목록 API에서 상태/validation count 응답 확인.
- 실제 `start-vm` 호출은 VM 서버 실행과 DB 상태 변경을 유발하므로 자동 실행하지 않았다.
- FastAPI `/ui/`에서 새 빌드 asset JS/CSS 200 응답 확인.
- 새 build asset 반영을 위해 `vm-middle` 컨테이너를 재시작했다.

### Poll / Reset 실행 UI 연결

**파일**: `frontend/src/features/vm-projects/`

상세 drawer의 `VM Execution` 섹션에 수동 상태 조회와 failed 복구 action을 연결했다.

구현 내용:
- `running` 상태이면서 `vm_job_id`가 있는 프로젝트에서 `Poll Now` 버튼을 활성화한다.
- `failed` 상태 프로젝트에서 `Reset to Ready` 버튼을 활성화한다.
- `POST /api/v1/vm-project/{id}/poll` mutation을 연결했다.
- `POST /api/v1/vm-project/{id}/reset` mutation을 연결했다.
- poll/reset 성공 시 상세 query와 목록 query를 invalidate한다.
- 각 action별 pending, success, error 상태 메시지를 표시한다.
- Start VM, Poll, Reset 중 하나가 실행 중이면 나머지 action은 잠시 비활성화한다.

검증:
- `docker exec vm_middle_front npm run typecheck` 통과.
- `docker exec vm_middle_front npm run build` 통과.
- VM 프로젝트 목록 API에서 상태/validation count 응답 확인.
- 실제 poll/reset 호출은 VM 상태 조회 및 DB 상태 변경을 유발하므로 자동 실행하지 않았다.
- FastAPI `/ui/`에서 새 빌드 asset JS/CSS 200 응답 확인.
- 새 build asset 반영을 위해 `vm-middle` 컨테이너를 재시작했다.

---

## 2026-05-06 — React 프론트엔드 전환 준비용 Agent Skills 추가

### 1. 설치 배경

VM_middle 프론트를 기존 FastAPI 정적 HTML/JS 구현에서 React 기반 UI로 전환하기 전에, 프론트엔드 구조와 디자인 품질 기준을 맞추기 위한 Agent Skills를 프로젝트 scope로 추가했다.

### 2. 추가된 Skills

**파일**: `.agents/skills/`, `skills-lock.json`

추가된 skill:

- `vercel-react-best-practices`: React/Next.js 성능, 데이터 fetching, bundle size, re-render 최적화 기준으로 사용
- `impeccable`: UI 디자인 품질, 컬러/타이포그래피/레이아웃/상태 표현, anti-pattern 점검 기준으로 사용

### 3. 활용 계획

- React 전환 시 Vercel React Best Practices 기준으로 컴포넌트 구조, 상태 분리, API 호출 흐름을 설계한다.
- Impeccable 기준으로 VM Middle 운영 콘솔에 맞는 색상, 간격, 타이포그래피, 화면 밀도, 반응형 품질을 점검한다.
- `skills-lock.json`은 설치된 skill의 source와 hash를 기록하는 잠금 파일로, 프로젝트 내 동일한 skill 기준을 공유하기 위한 메타데이터로 관리한다.

### 4. PRODUCT.md / DESIGN.md 초안 작성

**파일**: `../PRODUCT.md`, `../DESIGN.md`

React 전환 전에 Impeccable preflight 기준으로 제품/디자인 컨텍스트 문서 초안을 작성했다.

정리한 내용:

- `PRODUCT.md`: VM Middle의 register를 `product`로 정의하고, 주요 사용자, 제품 목적, 브랜드 성격, anti-reference, 접근성 기준을 정리
- `DESIGN.md`: KITECH CI 기반 컬러 토큰, 제품 UI 타이포그래피, 레이아웃, 컴포넌트 규칙, responsive breakpoint, React 구현 기준을 정리

KITECH 컬러는 공식 CI 가이드를 웹 UI에 맞게 근사값으로 반영했다.

- KITECH Blue: `#0047BB`
- KITECH Green: `#84BD00`
- Muted institutional accent: `#736273`

추후 React 구현은 이 두 문서와 `vercel-react-best-practices`, `impeccable` skill을 기준으로 진행한다.

### 5. React 프론트엔드 스캐폴딩 및 컨테이너 실행 환경 추가

**파일**: `frontend/`, `frontend_legacy/`, `../docker-compose.yaml`, `src/main.py`

기존 FastAPI 정적 HTML/JS 프론트는 `frontend_legacy/`로 보존하고, `frontend/`를 Vite + React + TypeScript 앱으로 재구성했다.

구현 범위:

- Vite React TypeScript 기본 구조 추가
- TanStack Query 기반 provider 추가
- VM 프로젝트 목록 조회 API client와 타입 정의 추가
- VM 프로젝트 목록/필터/상세 drawer read-only 화면 1차 구현
- KITECH 컬러 기반 CSS token과 기본 layout/style 추가
- `frontend/Dockerfile`, `.dockerignore`, `.gitignore` 추가
- `package-lock.json` 생성 및 Dockerfile을 `npm ci` 기반으로 조정
- `docker-compose.yaml`에 `vm-middle-front` 서비스 추가
- `src/main.py`에서 `frontend/dist`가 있으면 `/ui`가 build 산출물을 우선 서빙하도록 수정

컨테이너 구성:

```yaml
vm-middle-front:
  build:
    context: ./VM_middle/frontend
  ports:
    - "3010:5173"
  environment:
    VITE_API_TARGET: http://vm-middle:8000
```

검증:

- `docker compose config --services`에서 `vm-middle-front` 인식 확인
- `docker compose up -d vm-middle-front`로 프론트 컨테이너 빌드/실행 확인
- `docker exec vm_middle_front npm run typecheck` 통과
- `docker exec vm_middle_front npm run build` 통과
- `docker compose build vm-middle-front`로 lockfile 기반 이미지 재빌드 확인
- `docker exec vm_middle_front node -e "...fetch('http://localhost:5173/api/v1/vm-project?page=1&size=1')..."` → `200`
- `docker exec vm_middle ... http://localhost:8000/ui/` → `200`

접속 URL:

- 개발 서버: `http://localhost:3010`
- FastAPI static build: `http://localhost:8010/ui/`

## 2026-04-30 — VM JSON dt_file XML 예시 추가

### 1. JSON 결과 업로드 XML 샘플 작성

**파일**: `data/vm_json_dt_file_sample.xml`

#### 작성 기준
- 성공한 DP VM 프로젝트 `69e894e50174217b7eff872e`를 기준으로 실제 `gid/aid/eid/wpid` 값을 사용했다.
- 해당 프로젝트의 process annotation 중 process 1을 사용해 `WORKINGSTEP=페이스1`, `PROCESS_INDEX=1` 예시를 작성했다.
- 기존 ZIP 결과 `vm_001`이 이미 있는 프로젝트이므로, JSON 모드로 다음 실행 결과를 등록하는 상황을 가정해 `SEQ_ID=2`, `element_id=vm_json_002_001`로 작성했다.

#### 구조
- `category=VM`
- `content_type=application/json`
- `reference`에는 기존 `DT_GLOBAL_ASSET`, `DT_ASSET`, `DT_PROJECT`, `WORKPLAN`에 더해 `WORKINGSTEP`을 포함한다.
- `properties`에는 `NO_CODE`, `SEQ_ID`, `PROCESS_INDEX`, `Date`를 포함한다.

---

## 2026-04-28 — VM 결과 JSON 업로드 모드 추가

### 1. VM Start 업로드 모드를 bool에서 enum 개념으로 확장

**파일**: `src/schemas/vm_project.py`, `src/api/v1/vm_project.py`, `frontend/app.js`

#### 개발 배경
- 기존 `start-vm`은 `upload_result: true/false`만 지원해 ZIP 파일 업로드 또는 링크 저장 두 경우만 표현할 수 있었다.
- 새 요구사항은 VM 결과 ZIP 내부의 workingstep별 JSON 파일들을 개별 `dt_file`로 등록하는 세 번째 방식이 필요했다.

#### 구현 방식
- 스키마에 `VmResultUploadMode(file | link | json)`를 추가했다.
- `StartVmIn`은 새 필드 `upload_mode`를 우선 사용하고, 기존 `upload_result`는 레거시 호환용으로 유지했다.
- 라우터에서는 `body.resolved_upload_mode()`로 최종 모드를 해석해 서비스에 전달한다.
- 프론트 `VM Start` 섹션도 다음 세 옵션으로 확장했다.
  - `file`
  - `link`
  - `json`

### 2. VM 프로젝트 문서에 JSON 업로드 진행 상태 저장

**파일**: `src/dao/vm_project.py`, `src/schemas/vm_project.py`, `src/services/vm_project.py`

#### 저장 위치
- 데이터플랫폼이 아니라 `VM_middle`의 MongoDB `vm_project` 문서 안에 저장한다.
- 저장 단위는 데이터플랫폼 프로젝트 전체가 아니라, 특정 `gid/aid/eid/wpid` 조합으로 생성된 **VM 프로젝트 1건**이다.

#### 저장 구조
- `upload_mode`
- `vm_result_upload`

예시:

```json
{
  "upload_mode": "json",
  "vm_result_upload": {
    "mode": "json",
    "seq_id": 7,
    "total_count": 8,
    "uploaded_indices": [1, 2, 3],
    "uploaded_element_ids": [
      "vm_json_007_001",
      "vm_json_007_002",
      "vm_json_007_003"
    ],
    "last_uploaded_index": 3,
    "last_uploaded_element_id": "vm_json_007_003",
    "failed_index": 4,
    "error_message": "process 4 (vm_json_007_004) 업로드 실패: ...",
    "updated_at": "2026-04-28T..."
  }
}
```

#### 구현 포인트
- `set_vm_job_started()`에서 `upload_mode`와 빈 `vm_result_upload` 상태를 초기화한다.
- `VmProjectDetailOut`에 `upload_mode`, `vm_result_upload`를 추가해 프론트가 그대로 읽을 수 있게 했다.
- `reset_failed_to_ready()` 시 `vm_result_upload`와 업로드 시도 카운트도 함께 초기화한다.

### 3. JSON 업로드용 dt_file XML 구조 확장

**파일**: `src/utils/xml_parser.py`

#### 구현 방식
- 기존 `make_vm_dt_file_xml()`을 공용화해 다음 값을 파라미터로 받을 수 있게 확장했다.
  - `content_type`
  - `display_name`
  - `element_description`
  - `vm_element_id`
  - `workingstep_id`
  - `process_index`
- JSON 결과 업로드 시:
  - `content_type = application/json`
  - `WORKPLAN` 아래에 `WORKINGSTEP` reference 추가
  - `PROCESS_INDEX` property 추가
- `parse_dt_file_xml()`도 `WORKINGSTEP` reference를 파싱할 수 있게 보완했다.

### 4. JSON 업로드용 preflight + 순차 등록 로직 추가

**파일**: `src/services/vm_project.py`, `src/clients/dp.py`

#### 구현 원칙
- 배치 업로드/자동 롤백 API가 불분명하므로, JSON 모드는 **순차 업로드**로 구현했다.
- 대신 업로드 시작 전 로컬 preflight를 강하게 수행하고, 중간 실패 시 즉시 `failed`로 전환한다.

#### preflight 내용
- `process_annotations` 없으면 source XML에서 재계산
- `project_file_draft.process` 수와 `process_annotations` 수 일치 확인
- 결과 ZIP 다운로드 및 압축 해제
- 각 `output_dir_path` 폴더 존재 확인
- 각 process 결과 폴더 안의 `.json` 파일이 정확히 1개인지 확인
- 각 process에 대응하는 `workingstep_id`가 비어 있지 않은지 확인

#### 업로드 규칙
- `SEQ_ID`는 한 번의 VM 실행 배치에서 동일한 값을 공유한다.
- 개별 파일 구분은 `PROCESS_INDEX`와 `element_id`로 한다.
- `element_id`/`asset_id` 규칙:

```text
vm_json_{seq:03d}_{process_index:03d}
```

예:

```text
vm_json_007_001
vm_json_007_002
```

#### 실패 정책
- JSON 업로드 도중 하나라도 실패하면 즉시 중단한다.
- 이미 등록된 일부 dt_file은 자동 롤백하지 않는다.
- 해당 VM 프로젝트는 `failed`로 전환하고, `vm_result_upload`에 어디까지 올라갔는지 기록한다.
- 남은 쓰레기 데이터는 어드민 계정 정리 또는 플랫폼 업체 지원을 전제로 한다.

### 5. 프론트 상세 화면에 업로드 진행 상태 표시

**파일**: `frontend/app.js`

#### 표시 항목
- `upload_mode`
- `result_seq_id`
- `uploaded`
- `last_uploaded`
- `failed_process`
- `upload_error`

#### UI 변경
- `VM Start`에 `JSON 업로드` 라디오 옵션 추가
- `json` 선택 시, 중간 실패하면 관리자 정리가 필요할 수 있다는 안내 문구를 함께 표시하도록 했다.

### 6. 검증

- `python3 -m py_compile VM_middle/src/api/v1/vm_project.py VM_middle/src/dao/vm_project.py VM_middle/src/schemas/vm_project.py VM_middle/src/services/vm_project.py VM_middle/src/clients/dp.py VM_middle/src/utils/xml_parser.py`
- `node --check VM_middle/frontend/app.js`
- 컨테이너 내부 API 확인:
  - `GET /api/v1/vm-project/69e894e50174217b7eff872e` 응답에 `upload_mode`, `vm_result_upload` 필드 노출 확인
  - `POST /api/v1/vm-project/69e894e50174217b7eff872e/start-vm` with `{"upload_mode":"json"}` 요청이 스키마 레벨에서 정상 수용되는 것 확인

### 7. DP 프로젝트 생성 에러 응답 정리

**파일**: `src/services/vm_project.py`, `src/api/v1/vm_project.py`

#### 개발 배경
- DP 원본 프로젝트로 VM 프로젝트를 생성할 때, 데이터플랫폼 `find/element`가 일시적으로 `503 Service Temporarily Unavailable`를 반환하면 내부에서 `ValueError`로 감싼 뒤 FastAPI 바깥까지 전파됐다.
- 그 결과 프론트에서는 원인이 DP 업스트림 장애임에도 `500 Internal Server Error`로만 보였다.

#### 구현 방식
- 서비스 계층에 DP 업스트림 예외를 `HTTPException`으로 변환하는 헬퍼를 추가했다.
- 특히 `503`은 그대로 `503`으로 노출하고, 그 외 DP HTTP 에러나 네트워크 에러는 `502`로 정리했다.
- `create_full` 라우터에는 `ValueError`를 `400 Bad Request`로 바꾸는 방어를 추가해, 앞으로 입력/도메인 오류가 다시 애매한 `500`으로 보이지 않게 했다.

#### 기대 효과
- DP 일시 장애 시 프론트와 운영 로그에서 원인을 바로 구분할 수 있다.
- 사용자에게는 “DP upstream 문제”와 “우리 입력/도메인 문제”가 서로 다른 상태코드로 보인다.

#### 추가 보완
- 같은 생성 흐름 안에서 `dt_file` 매칭 후 NC 원본 파일을 `/files/download/userdata`로 받는 단계도 DP 업스트림 `503`이 날 수 있어서, 이 경로 역시 `500`이 아니라 `502/503`으로 노출되도록 정리했다.
- DP `dt_cutting_tool_13399` 조회가 실패해 tool 값이 `null`로 떨어지는 경우를 추적하기 쉽도록, `process_index`, `workingstep_id`, `tool_asset_id`, `tool_element_id`, `error`를 경고 로그와 `debug.tool_fetch_failures`에 남기도록 보강했다.

## 2026-04-24 — VM 프론트 상세 편집 UX 정리 및 DP 소스 검색 보완

### 1. 프로젝트 상세의 stock size 입력 방식 개선

**파일**: `frontend/app.js`, `frontend/styles.css`

#### 개발 배경
- 기존 프론트는 `stock_size`를 하나의 문자열 입력으로 노출했다.
- 값 형식이 `"min_x,max_x,min_y,max_y,min_z,max_z"` 형태라 사용자가 각 좌표가 어떤 의미인지 바로 알기 어려웠다.

#### 구현 방식
- 상세 패널의 Stock 섹션에서 `stock_size`를 바로 입력하지 않도록 변경했다.
- 대신 아래 6개 필드를 각각 분리해 표시/수정하도록 구성했다.
  - `min_x`
  - `max_x`
  - `min_y`
  - `max_y`
  - `min_z`
  - `max_z`
- 프론트 내부에서는:
  - `parseStockSize()`로 기존 문자열을 6개 필드로 분해
  - `serializeStockSize()`로 저장 시 다시 기존 백엔드 포맷 문자열로 조립
- 따라서 백엔드 `PATCH /project-file/stock` 요청 포맷은 유지하면서 UI만 이해하기 쉬운 형태로 바뀌었다.

#### 호환성
- 백엔드 API 스펙은 바꾸지 않았다.
- 기존 DB/응답의 `stock_size` 문자열 포맷을 그대로 사용한다.

---

### 2. Process 편집 화면을 공구 정보 중심으로 단순화

**파일**: `frontend/app.js`, `frontend/styles.css`

#### 개발 배경
- Process 항목은 NC/XML 기준으로 자동 생성되므로 사용자가 행을 추가하거나 삭제하면 안 된다.
- `file_path`, `output_dir_path`는 시스템이 자동으로 채우므로 편집 UI에서 굳이 직접 보여줄 필요가 적다.
- 실제 수정이 필요한 것은 각 process별 공구 정보(`tool_data`)이다.

#### 구현 방식
- Process 섹션에서 add/remove UI를 제거했다.
- 각 process row는 고정 개수로만 보여주고, 아래 공구 필드만 수정 가능하게 변경했다.
  - `T No`
  - `Dia`
  - `Rad`
  - `eDis`
  - `fDis`
  - `bangl`
  - `sangl`
  - `Len`
  - `flut`
- `tool_data`는 기존의 CSV 문자열 포맷을 그대로 사용하되:
  - `parseToolData()`로 화면용 객체로 분해
  - `serializeToolData()`로 저장 시 다시 CSV 문자열로 조립
- 저장 시에는 기존 `file_path`, `output_dir_path`를 숨긴 상태로 그대로 유지하여 백엔드에 다시 전송한다.

#### 항목 설명 UI
- Process 섹션 상단에 `항목 설명` 버튼을 두고, 누르면 각 항목 의미를 한 번에 볼 수 있는 안내 블록을 표시하도록 했다.
- 개발 과정 설명처럼 보이던 상단 안내 문구는 실제 사용자용 설명으로 정리했다.
- 공구 형상 참고 이미지는 프론트 정적 자산 `frontend/src/cutting-tool-guide.svg`로 추가해, `항목 설명`을 열면 텍스트 설명과 함께 같이 표시되도록 했다.
- 이후 사용자가 제공한 실제 이미지 파일 `frontend/src/tool_spec.png`를 사용하도록 교체했다.
- 설명 카드 영역은 더 작고 촘촘하게 줄이고, 이미지가 더 잘 보이도록 아래쪽 시각 영역을 넓히는 형태로 다시 조정했다.
- 항목 의미는 다음과 같이 표현했다.
  - `Dia`: cutter diameter
  - `Rad`: cutter radius
  - `eDis`: radial corner offset
  - `fDis`: axial corner offset
  - `bangl`: tip angle
  - `sangl`: flank angle
  - `Len`: cutter height
  - `flut`: flut number

#### 호환성
- 백엔드 `PATCH /project-file/process`의 입력 형식은 유지했다.
- process 개수와 순서는 그대로 두고, UI에서만 행 편집 범위를 제한했다.

---

### 3. DP 원본 프로젝트 목록 페이지 이동 및 검색 추가

**파일**: `src/clients/dp.py`, `src/api/v1/dp.py`, `frontend/app.js`, `frontend/styles.css`

#### 개발 배경
- DP 원본 프로젝트 목록은 기본적으로 10개만 보여서 다음 결과를 보기 어렵다는 문제가 있었다.
- 사용자 요청에 따라 "페이지 이동" 또는 "검색"이 가능해야 했다.

#### 현재 구조 확인 결과
- 기존 프론트는 `GET /api/v1/dp/projects?page={page}&size={size}`만 호출하고 있었다.
- 기존 백엔드도 내부적으로 DP OpenAPI `/openapi/v2/asset/find/element`에 `type=project`, `page`, `size`만 전달하고 있었다.
- 확인 결과 상위 DP API는 `allSearch` 파라미터를 지원하므로, 백엔드에서 이 값을 그대로 전달하면 검색이 가능하다.

#### 구현 방식
- 프론트 생성 패널에 DP 전용 검색 입력과 `검색`, `초기화` 버튼을 추가했다.
- 목록 하단에는 `이전`, `다음` 페이지 버튼과 현재 페이지 표시를 유지했다.
- 백엔드에서는:
  - `GET /api/v1/dp/projects`에 `q` 파라미터를 추가
  - 내부 DP 클라이언트 `list_projects()`가 `q`를 상위 API의 `allSearch`로 전달

#### 추가 수정
- DP 페이지 번호는 내부적으로 0-base인데 프론트 초기값이 `1`이라 첫 화면부터 두 번째 페이지를 보고 있을 가능성이 있었다.
- 이를 `0`으로 바로잡아 첫 로딩이 실제 첫 페이지를 보도록 수정했다.

#### 검증
- `python3 -m py_compile VM_middle/src/api/v1/dp.py VM_middle/src/clients/dp.py`
- `node --check VM_middle/frontend/app.js`
- 컨테이너 내부 확인:
  - `GET /api/v1/dp/projects?page=0&size=5` → `200`
  - `GET /api/v1/dp/projects?page=0&size=5&q=iso` → `200`
  - 응답 예시: `page=0`, `size=5`, `total=27`

---

### 4. 화면 검증 결과

#### 확인한 내용
- VM 상세 패널의 Stock 섹션에 `min_x ~ max_z` 입력 필드 6개가 분리되어 표시됨
- Process 섹션에서 파일 경로 입력 UI 없이 공구 필드만 표시됨
- `항목 설명` 안내 블록이 Process 상단에 표시됨
- Create VM Project 패널에 DP 검색 입력 및 페이지 버튼이 표시됨

#### 주의사항
- 브라우저 자동완성 오버레이 때문에 검색 버튼 클릭 시 시각적 반응은 일시적으로 애매할 수 있었지만, 백엔드 검색 응답 자체는 정상 확인했다.

---

### 5. Process별 workingstep its_id 표시용 보조 메타데이터 추가

**파일**: `src/schemas/vm_project.py`, `src/dao/vm_project.py`, `src/services/vm_project.py`, `src/api/v1/vm_project.py`, `frontend/app.js`, `frontend/styles.css`

#### 개발 배경
- Process는 NC/XML 파싱 결과를 기반으로 만들어지며, 각 row가 어떤 workingstep에서 왔는지 UI에서 바로 알기 어려웠다.
- 사용자 요청은 각 process 항목 옆에 해당 workingstep의 `its_id`를 보여주는 것이었다.
- 다만 이 정보를 `project_file_draft.process` 또는 실제 `project.prj` 포맷 안에 넣으면 VM이 기존 형식 외 데이터를 에러로 처리할 위험이 있다.

#### 구현 원칙
- `project_file_draft` 포맷은 그대로 유지한다.
- VM 실행에 사용되는 `prj` 데이터에는 아무 필드도 추가하지 않는다.
- 대신 VM 프로젝트 문서에 UI 전용 메타데이터 `process_annotations`를 별도 저장한다.
- 프론트는 이 메타데이터를 별도 읽기 API로 받아 화면에만 표시한다.

#### 저장 구조
- `vm_project` 문서에 아래와 같은 필드를 추가했다.

```json
{
  "process_annotations": [
    {
      "index": 0,
      "workingstep_id": "페이스1",
      "tool_element_id": "T1"
    }
  ]
}
```

- `index`는 `project_file_draft.process[index]`와 매칭된다.
- `workingstep_id`는 source XML의 workingstep `its_id`이다.
- `tool_element_id`는 해당 workingstep이 참조한 tool element id이다.

#### 백엔드 구현 방식
- `extract_tool_refs_in_order()`가 이미 `ws_id`를 반환하고 있었기 때문에 이 값을 재사용했다.
- 서비스에 `_build_process_annotations()`를 추가해 `ws_refs`를 `process_annotations` 형식으로 변환하도록 했다.
- ISO/DP VM 프로젝트 생성 시점에 `process_annotations`를 같이 저장하도록 DAO insert 경로를 확장했다.
- 기존 문서에는 이 필드가 없을 수 있으므로, `GET /api/v1/vm-project/{id}/process-annotations` 호출 시:
  1. DB에 값이 있으면 그대로 반환
  2. 없으면 source XML을 다시 읽어서 재계산
  3. 재계산 성공 시 DB에 backfill 저장
  4. 이후 응답 반환

#### API 추가
- 새 읽기 전용 endpoint를 추가했다.

```text
GET /api/v1/vm-project/{id}/process-annotations
```

- 응답 예시:

```json
{
  "items": [
    { "index": 0, "workingstep_id": "페이스1", "tool_element_id": "T1" },
    { "index": 1, "workingstep_id": "2D 포켓4", "tool_element_id": "T2" }
  ]
}
```

- 이 endpoint는 `project_file_draft`를 수정하지 않고, UI 보조 정보만 제공한다.
- 또한 서비스에서 발생한 `HTTPException`은 그대로 유지하도록 라우터 예외 처리도 정리했다.

#### 프론트 반영
- 프로젝트 상세를 열 때 기존 상세 API와 함께 `process-annotations`를 병렬 조회하도록 했다.
- 각 Process row 제목 아래에 `WS: {workingstep_id}` 형태의 배지를 표시하도록 추가했다.
- 상세 패널 폭 안에서도 잘 읽히도록, 우측 정렬 배지 대신 제목 아래에 붙는 작은 monospace badge 형태로 정리했다.

#### 호환성
- `project_file_draft.process` 구조는 변경하지 않았다.
- `PATCH /project-file/process` 입력 구조도 유지했다.
- VM 실행에 전달되는 `project.prj` 포맷도 유지된다.
- 따라서 기존 VM 로직과의 충돌 없이, 화면에서만 workingstep 정보를 추가로 볼 수 있게 됐다.

#### 검증
- `python3 -m py_compile VM_middle/src/api/v1/vm_project.py VM_middle/src/dao/vm_project.py VM_middle/src/schemas/vm_project.py VM_middle/src/services/vm_project.py`
- `node --check VM_middle/frontend/app.js`
- 컨테이너 내부 API 확인:
  - `GET /api/v1/vm-project/69e894e50174217b7eff872e/process-annotations` → `200`
  - 응답 항목 수 `8`, 각 항목에 `workingstep_id`와 `tool_element_id` 포함
- 기존 프로젝트 상세 process 개수와 annotation 개수가 일치하는지 확인했다.

---

## 2026-04-23 — VM 프론트엔드 준비 및 DP 썸네일 백엔드 보완

### 1. 개발 배경

VM_middle에 프론트엔드 화면을 추가하기 위해 필요한 백엔드/프론트 준비 작업을 진행했다.

프론트에서 요구하는 핵심 기능은 다음이다.

- VM 프로젝트 목록 표시
- 프로젝트 선택 시 상세 `project.prj` 데이터 표시
- `ready`, `needs-fix` 상태의 stock/process 수정
- ISO 또는 DP 프로젝트 선택 후 workplan 선택을 통한 VM 프로젝트 생성
- `ready` 상태에서 VM start 실행
- VM 결과 등록 방식을 파일 업로드 또는 링크 저장 중 선택
- 프로젝트 썸네일 이미지 표시

이 중 DP 프로젝트 썸네일은 DP에 등록된 `dt_file` asset을 통해 가져와야 한다. 샘플 XML과 실제 DP 데이터를 확인한 결과, 프로젝트를 참조하는 `dt_file` 중 `<category>TITLE_IMAGE</category>`인 파일의 `<path>` 값을 사용하면 썸네일 이미지를 다운로드할 수 있다.

### 2. 프론트엔드 작업계획 문서 추가

**파일**: `VM_FRONTEND_WORK_PLAN.md`

VM_middle 프론트엔드 개발을 위한 작업계획 문서를 추가했다.

문서에 정리한 주요 내용:

- 현재 `docker-compose.yaml` 기준 서비스 구조
- 실행 중인 컨테이너 확인 결과
- 현재 사용 가능한 VM_middle API 목록
- React + Vite 기반 프론트 구성 제안
- 별도 `vm-middle-front` 컨테이너 구성안
- VM 프로젝트 목록/상세/수정/생성 wizard/VM start 화면 구성안
- DP `TITLE_IMAGE` 썸네일 조회 방식
- 컨테이너 기반 테스트 계획

프론트 구성 방향은 1차 개발에서는 `Vite + React + TypeScript`를 권장했다.

선택 이유:

- VM_middle 프론트는 SEO/SSR이 필요한 공개 웹사이트가 아니라 내부 운영용 콘솔에 가깝다.
- FastAPI API를 호출하는 SPA 구조가 단순하고 적합하다.
- 빌드 결과물을 FastAPI static 또는 별도 nginx/static 컨테이너로 배포하기 쉽다.
- Next.js는 인증/권한/포털 통합/서버 렌더링이 중요해질 때 2차 검토 대상으로 두는 것이 적절하다.

### 3. 프론트엔드 정적 화면 시안 추가

**파일**: `frontend_mockup/index.html`

React 구현 전에 화면 흐름을 빠르게 검토할 수 있도록 정적 HTML 프로토타입을 추가했다.

시안 구성:

| 영역 | 내용 |
|---|---|
| 좌측 패널 | 프로젝트 프리뷰, DP `TITLE_IMAGE`/No image 상태, 생성 wizard |
| 중앙 패널 | VM 프로젝트 목록, 검색, 상태 필터, source 표시 |
| 우측 패널 | 프로젝트 상세, source metadata, stock editor, process table, validation, VM start |

주요 UX 반영:

- DP 프로젝트는 썸네일이 있으면 이미지 영역에 표시하는 것을 전제로 구성
- 이미지가 없으면 `No image` placeholder 표시
- `ready` 상태에서만 VM start 버튼이 의미 있게 활성화되는 구조
- 결과 처리 방식은 `upload_result: true`와 `upload_result: false` 중 선택
- process는 1차 구현에서 table 기반 raw editing을 전제로 설계

검증:

```bash
python3 -m html.parser VM_middle/frontend_mockup/index.html
```

결과:

- HTML parser 통과

### 4. DP 썸네일 조회 API 추가

**추가 API**:

```http
GET /api/v1/vm-project/{vm_project_id}/thumbnail
GET /api/v1/dp/projects/thumbnail?gid=&aid=&eid=
```

동작:

- `source == "dp"`인 VM 프로젝트만 지원
- 같은 `gid` 아래 file element 목록 조회
- 각 file element의 XML을 조회
- `dt_file` XML에서 `category`, `path`, `content_type`, `reference`를 파싱
- `category == "TITLE_IMAGE"`이고 현재 VM 프로젝트를 참조하면 선택
- 선택한 `path`로 DP 파일 다운로드 API 호출
- 이미지 bytes를 `Response`로 반환
- 이미지가 없으면 `404 {"detail":"thumbnail not found"}` 반환

ISO 프로젝트는 현재 이미지가 있는 프로젝트가 확인되지 않았으므로 우선 404 fallback으로 처리한다.

추가된 `GET /api/v1/dp/projects/thumbnail?gid=&aid=&eid=` endpoint는 VM 프로젝트가 아직 생성되지 않은 단계, 즉 DP 프로젝트 선택 wizard에서 바로 썸네일을 보여주기 위한 용도다.

#### 4-1. 라우터 추가

**파일**: `src/api/v1/vm_project.py`, `src/api/v1/dp.py`

추가 내용:

```python
@router.get("/{vm_project_id}/thumbnail", summary="VM 프로젝트 썸네일 이미지")
async def get_vm_project_thumbnail(
    vm_project_id: str,
    svc: VmProjectService = Depends(get_vm_project_service),
):
    content, media_type = await svc.get_thumbnail(ObjectId(vm_project_id))
    return Response(content=content, media_type=media_type)
```

라우터는 HTTP 요청 처리만 담당하고, 썸네일 탐색/다운로드 로직은 `VmProjectService`에 둔다.

추가로 DP 원본 프로젝트용 라우터를 아래와 같이 추가했다.

```python
@router.get("/projects/thumbnail", summary="DP 원본 프로젝트 썸네일 이미지")
async def get_dp_project_thumbnail(
    gid: str = Query(...),
    aid: str = Query(...),
    eid: str = Query(...),
    svc: VmProjectService = Depends(get_vm_project_service),
):
    content, media_type = await svc.get_dp_project_thumbnail(
        gid=gid,
        aid=aid,
        eid=eid,
    )
    return Response(content=content, media_type=media_type)
```

#### 4-2. DP 클라이언트에 bytes 다운로드 함수 추가

**파일**: `src/clients/dp.py`

기존 함수:

```python
download_nc_file(path: str) -> str
```

이 함수는 NC 텍스트 다운로드에 이미 사용 중이므로 수정하지 않았다.

새 함수:

```python
download_user_file_bytes(path: str) -> tuple[bytes, Optional[str]]
```

동일한 DP API를 사용하지만 bytes를 그대로 반환한다.

```text
GET /openapi/v2/files/download/userdata?path={path}
```

분리 이유:

- 기존 DP VM 생성/NC split 흐름이 `download_nc_file()`에 의존하고 있다.
- 이미지 다운로드 때문에 기존 텍스트 디코딩 흐름을 바꾸면 정상 동작 중인 NC 처리에 영향을 줄 수 있다.
- 따라서 이미지/바이너리 다운로드는 새 함수로 독립시켰다.

#### 4-3. dt_file XML 파서 보완

**파일**: `src/utils/xml_parser.py`

기존 `parse_dt_file_xml()`은 이미 아래 값을 파싱하고 있었다.

- `element_id`
- `display_name`
- `category`
- `content_oid`
- `refs`
- `properties`

썸네일 다운로드에는 `<path>`와 `<content_type>`이 필요하므로 반환값에 두 필드를 추가했다.

추가 반환 필드:

```python
{
    "content_type": "image/png",
    "path": "/userdata/4/2fa8e_301_thumbnail.png",
}
```

기존 반환 필드명과 구조는 변경하지 않았다.

#### 4-4. 서비스 로직 추가

**파일**: `src/services/vm_project.py`

추가된 주요 함수:

```python
_dp_asset_ref_matches(ref_aid, project_aid)
_match_dp_title_image(info, gid, aid, eid)
get_dp_project_thumbnail(gid, aid, eid)
get_thumbnail(vm_project_id)
```

`_dp_asset_ref_matches()`:

- DP의 `DT_ASSET` 값은 short id와 full URI가 섞일 수 있다.
- 예: VM 프로젝트 `aid`는 `https://digital-thread.re/kitech/vm_test_iso301/vm_test_project`
- `dt_file` reference의 `DT_ASSET`은 `vm_test_project`
- 따라서 full match 또는 마지막 path segment match를 모두 허용한다.

`_match_dp_title_image()`:

아래 조건을 모두 만족해야 썸네일 후보로 판단한다.

```text
category == TITLE_IMAGE
DT_GLOBAL_ASSET == vm_project.gid
DT_PROJECT == vm_project.eid
DT_ASSET == vm_project.aid 또는 vm_project.aid의 마지막 segment
```

`get_thumbnail()`:

전체 흐름:

1. `vm_project` 문서 조회
2. `source == "dp"`인지 확인
3. `gid`, `aid`, `eid` 확인
4. `dp_client.list_elements_by_gid(gid)` 호출
5. `type`이 `file` 또는 `dt_file`인 후보 순회
6. 후보별 `dp_client.get_element_xml(aid, eid)` 호출
7. `parse_dt_file_xml(xml)`로 `category/path/content_type/reference` 파싱
8. `TITLE_IMAGE` reference match 확인
9. `path`가 있으면 `download_user_file_bytes(path)` 호출
10. 이미지 bytes와 media type 반환

`get_dp_project_thumbnail()`:

- `gid/aid/eid` 기준으로 DP 원본 프로젝트의 썸네일을 직접 조회한다.
- 내부 후보 탐색/우선순위/다운로드 로직은 `get_thumbnail()`과 동일하다.
- `get_thumbnail(vm_project_id)`는 이제 VM 프로젝트 문서에서 `gid/aid/eid`를 꺼낸 뒤 `get_dp_project_thumbnail()`을 재사용한다.

#### 4-5. TITLE_IMAGE 후보 선택 우선순위 정책 추가

`TITLE_IMAGE` 파일이 여러 개 등록될 수 있으므로, 단순히 DP 목록에서 먼저 발견한 항목을 반환하지 않고 대표 썸네일 후보를 안정적으로 고르는 정렬 정책을 추가했다.

적용된 우선순위:

1. `content_type`이 `image/*`인 후보
2. `content_type`이 없지만 `path` 또는 `display_name`이 이미지 확장자인 후보
3. `updateDate`가 최신인 후보
4. `createDate`가 최신인 후보
5. `assetSeq`가 큰 후보
6. `elementId` 사전순 기준으로 뒤에 오는 후보

또한 `content_type`이 명시되어 있는데 `image/*`가 아닌 후보는 제외한다.

다운로드 실패 처리:

- 우선순위가 높은 후보 다운로드에 실패하면 다음 후보를 시도한다.
- 모든 후보 다운로드가 실패하면 기존처럼 `502`를 반환한다.
- 후보 자체가 없으면 `404 {"detail":"thumbnail not found"}`를 반환한다.

### 5. 기존 DP 동작 보호를 위해 지킨 제약

DP 백엔드는 현재 VM 프로젝트 생성, NC 파일 매칭, NC 다운로드, split, GridFS 저장, VM 실행까지 정상 동작 중이므로 아래 제약을 지켰다.

- 기존 `download_nc_file()` 수정 없음
- 기존 `_match_dt_file_dp()` 수정 없음
- 기존 `create_full_from_dp()` 흐름 수정 없음
- 기존 DP workplan 조회 API 수정 없음
- 기존 VM 프로젝트 목록/상세/stock/process/start-vm API 응답 구조 변경 없음
- 썸네일 기능은 전용 endpoint와 전용 service method로만 추가
- 이미지가 없거나 path가 비어 있어도 VM 프로젝트 생성/조회에는 영향 없음

### 6. 실제 DP 데이터 검증

대상 프로젝트:

```text
gid = https://digital-thread.re/kitech/vm_test_iso301
aid = https://digital-thread.re/kitech/vm_test_iso301/vm_test_project
eid = v1
```

DP `list_elements_by_gid()` 결과에서 확인한 file 후보:

```text
type      = file
assetId   = https://digital-thread.re/kitech/vm_test_iso301/image_asset
elementId = vm_test_iso301_thumbnail_001
display   = 301_thumbnail.png
path      = /userdata/4/2fa8e_301_thumbnail.png
```

해당 XML 파싱 결과:

```text
category     = TITLE_IMAGE
display_name = 301_thumbnail.png
content_type = image/png
path         = /userdata/4/2fa8e_301_thumbnail.png
DT_GLOBAL_ASSET = https://digital-thread.re/kitech/vm_test_iso301
DT_ASSET        = vm_test_project
DT_PROJECT      = v1
```

새 thumbnail endpoint 검증:

```text
GET /api/v1/vm-project/69e894e50174217b7eff872e/thumbnail
```

응답:

```text
200 image/png
29452 bytes
PNG header: b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
```

즉, DP `TITLE_IMAGE` 탐색 → `path` 추출 → DP 파일 다운로드 → 이미지 응답까지 정상 확인했다.

### 7. 컨테이너 기준 검증 명령

문법 검증:

```bash
docker exec vm_middle conda run -n myenv python -m compileall src
```

결과:

- 통과

기존 VM 프로젝트 목록 API:

```bash
docker exec vm_middle conda run -n myenv python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/api/v1/vm-project?page=1&size=1', timeout=10).read().decode()[:500])"
```

결과:

- 정상 응답
- 총 13개 프로젝트 확인

기존 DP workplan API:

```bash
docker exec vm_middle conda run -n myenv python -c "import urllib.parse, urllib.request; gid='https://digital-thread.re/kitech/vm_test_iso301'; aid='https://digital-thread.re/kitech/vm_test_iso301/vm_test_project'; eid='v1'; qs=urllib.parse.urlencode({'gid':gid,'aid':aid,'eid':eid}); print(urllib.request.urlopen('http://localhost:8000/api/v1/dp/projects/workplans?'+qs, timeout=15).read().decode()[:1000])"
```

결과:

```json
{
  "gid": "https://digital-thread.re/kitech/vm_test_iso301",
  "aid": "https://digital-thread.re/kitech/vm_test_iso301/vm_test_project",
  "eid": "v1",
  "workplans": [
    {
      "wpid": "wp_001",
      "ws_count": 8,
      "pattern": "single_sub"
    }
  ]
}
```

썸네일 API:

```bash
docker exec vm_middle conda run -n myenv python -c "import urllib.request; r=urllib.request.urlopen('http://localhost:8000/api/v1/vm-project/69e894e50174217b7eff872e/thumbnail', timeout=30); b=r.read(); print(r.status, r.headers.get('content-type'), len(b), b[:16])"
```

결과:

```text
200 image/png 29452 b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
```

DP 원본 프로젝트 썸네일 API:

```bash
docker exec vm_middle conda run -n myenv python -c "import urllib.parse, urllib.request; qs=urllib.parse.urlencode({'gid':'https://digital-thread.re/kitech/vm_test_iso301','aid':'https://digital-thread.re/kitech/vm_test_iso301/vm_test_project','eid':'v1'}); url='http://localhost:8000/api/v1/dp/projects/thumbnail?'+qs; r=urllib.request.urlopen(url, timeout=30); b=r.read(); print(r.status, r.headers.get('content-type'), len(b), b[:16])"
```

결과:

```text
200 image/png 29452 b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
```

### 8. 현재 변경 파일

이번 작업에서 실제 백엔드 기능 변경이 들어간 파일:

```text
src/main.py
src/api/v1/vm_project.py
src/clients/dp.py
src/services/vm_project.py
src/utils/xml_parser.py
```

프론트 준비/문서 파일:

```text
VM_FRONTEND_WORK_PLAN.md
frontend/index.html
frontend/app.js
frontend/styles.css
frontend_mockup/index.html
CHANGELOG.md
```

### 9. 남은 작업

프론트 구현 시 연결할 부분:

- 프로젝트 목록/상세 화면에서 `thumbnail` URL 사용
- 이미지 로드 실패 또는 404 시 `No image` placeholder 표시
- DP 프로젝트 생성 wizard에서는 `GET /api/v1/dp/projects/thumbnail?gid=&aid=&eid=`를 사용해 프로젝트 선택 단계에서 thumbnail preview 표시
- ISO 프로젝트는 우선 No image 처리

백엔드 추가 개선 후보:

- 목록 응답에 `thumbnail_available` 또는 `thumbnail_url` 추가 여부 검토
- 썸네일 metadata endpoint 추가 여부 검토
- 이미지 다운로드 실패 시 502 대신 UI fallback 친화적인 응답을 줄지 검토

현재 판단:

- `thumbnail_available`, `thumbnail_url`, thumbnail metadata endpoint는 캐싱 없이 추가하면 결국 프로젝트별 DP 조회를 한 번 더 수행해야 하므로 1차 구현에서는 보류한다.
- 프론트는 우선 `<img src="/api/v1/vm-project/{id}/thumbnail">` 형태로 이미지를 요청하고, 404/502/onError는 `No image` placeholder로 처리한다.
- 목록 응답에 썸네일 정보를 넣는 개선은 thumbnail metadata를 DB에 캐싱하는 시점에 다시 검토한다.

### 10. 설치 없는 정적 프론트 실제 구현

초기 계획 문서에서는 React + Vite 기반 구성을 검토했지만, 실제 1차 구현은 추가 설치나 별도 프론트 컨테이너 없이 바로 실행 가능한 형태가 더 적절하다고 판단했다.

이유:

- 현재 `vm_middle` 컨테이너가 이미 실행 중이고 `/app` 볼륨 마운트 + `uvicorn --reload` 구조를 사용하고 있다.
- 사용자는 로컬에 새 패키지 설치 없이 바로 프론트 동작을 확인하길 원했다.
- 내부 운영용 화면의 1차 구현에서는 정적 `html/js/css`만으로도 필요한 기능을 충분히 구현할 수 있다.

구현 방향:

- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`

위 세 파일을 추가하고, FastAPI에서 `/ui` 경로로 정적 서빙하도록 연결했다.

```python
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(frontend_dir), html=True), name="vm-ui")
```

즉, 별도 npm install 없이 아래 주소로 화면을 바로 볼 수 있게 만들었다.

```text
http://localhost:8010/ui/
```

#### 10-1. 실제 구현한 화면 기능

1차 구현에 포함한 기능:

- VM 프로젝트 목록 조회
- 상태 필터 / 검색어 기반 목록 재조회
- 프로젝트 선택 시 상세 조회
- DP VM 프로젝트 썸네일 표시
- stock type / stock size 편집
- process row 추가 / 삭제 / 직접 수정
- validation error / vm 상태 표시
- `ready` 상태에서만 VM Start 가능
- `failed` 상태에서 Reset 가능
- `running` 상태에서 Poll 가능
- DP / ISO 원본 프로젝트 선택 기반 VM 프로젝트 생성
- DP 원본 프로젝트 선택 시 썸네일 preview 표시
- ISO 프로젝트는 `No image` fallback 처리

#### 10-2. 프론트 정책 반영

프론트 정책은 백엔드 현재 규칙에 맞췄다.

- `ready`, `needs-fix`만 stock / process 수정 가능
- `running`, `completed`, `failed`는 읽기 전용
- `ready`일 때만 Start 버튼 활성화
- `failed`일 때만 Reset 버튼 활성화
- `running`일 때만 Poll 버튼 활성화
- 썸네일 API 실패(404/502/onError)는 모두 `No image` placeholder로 처리

#### 10-3. 검증 결과

문법/정적 검증:

```bash
python3 -m py_compile VM_middle/src/main.py
python3 -m html.parser VM_middle/frontend/index.html
node --check VM_middle/frontend/app.js
```

결과:

- 모두 통과

실행 중 컨테이너 기준 검증:

```bash
docker exec vm_middle conda run -n myenv python -c "..."
```

확인 항목:

- `GET /healthz` → 200
- `GET /ui/` → 200
- `GET /ui/app.js` → 200
- `GET /ui/styles.css` → 200

또한 실제 브라우저에서 `http://127.0.0.1:8010/ui/`를 열어 아래를 확인했다.

- VM 프로젝트 목록/상세 화면 렌더링
- 기존 DP 프로젝트 상세 데이터 표시
- 편집 불가 상태(completed)에서 입력창/버튼 disabled 표시
- `/docs` 링크 연결

#### 10-4. 현재 1차 구현의 한계

현재 구현은 빠르게 연결 가능한 운영용 1차 버전이다.

- 디자인 시스템이나 컴포넌트 프레임워크는 아직 적용하지 않았다.
- 목록 pagination / source list pagination은 1차 구현에서 단순 조회 위주로 두었다.
- process 편집은 raw table 기반이며, 도메인별 입력 보조는 아직 없다.
- source project 선택 시 자동 prefetch/cache는 최소화했다.

하지만 지금 목표였던 “백엔드와 실제 연결되는 동작 가능한 프론트” 기준으로는 바로 사용 가능한 수준까지 연결되었다.

### 11. 프론트 UI 레이아웃 재정리

1차 프론트 연결 후 실제 화면을 확인해보니 다음 문제가 있었다.

- 좌측 프로젝트 생성 영역 폭이 좁아 source project 정보가 제대로 보이지 않음
- 가운데 VM 프로젝트 리스트는 표시 정보에 비해 row 높이가 커서 한 화면에 보이는 항목 수가 적음
- 프로젝트 상세 영역이 메인 화면에 고정되어 있어 process/validation 구간 때문에 세로 길이가 지나치게 길어짐

이를 해결하기 위해 메인 화면 레이아웃을 다시 정리했다.

#### 11-1. 레이아웃 구조 변경

변경 전:

- 좌측: 생성
- 가운데: VM 프로젝트 리스트
- 우측: 상세 고정 패널

변경 후:

- 좌측: 생성 패널
- 우측: VM 프로젝트 리스트
- 상세: 프로젝트 선택 시 우측에서 열리는 슬라이드오버 패널

즉, 메인 화면은 2단으로 단순화하고, 상세는 overlay 패널로 분리했다.

#### 11-2. 적용 파일

```text
frontend/app.js
frontend/styles.css
```

#### 11-3. 주요 변경 내용

`frontend/app.js`

- `state.ui.detailOpen` 상태 추가
- 프로젝트 row 클릭 시 상세를 즉시 우측 슬라이드오버로 오픈
- `renderDetailDrawer()` 추가
- 기존 3단 `app-grid` 렌더 제거
- 메인 화면을 `workspace` 2단 구조로 재구성

`frontend/styles.css`

- `.workspace` 2단 그리드로 변경
- 생성 패널 폭 확대
- 리스트 패널 row height 축소 및 썸네일 축소
- source project 목록에 scroll shell 추가
- `.detail-drawer`, `.drawer-backdrop`, `.drawer-panel` 스타일 추가

#### 11-4. UX 개선 효과

- 생성 화면에서 긴 `gid/aid/eid` 정보가 이전보다 훨씬 읽기 쉬워짐
- 리스트가 조밀해져 한 화면에 더 많은 VM 프로젝트를 볼 수 있음
- 상세는 필요할 때만 열리므로 메인 화면이 덜 답답해짐
- process가 긴 프로젝트도 메인 레이아웃을 무너뜨리지 않음
- 리스트 탐색 컨텍스트를 유지한 채 상세 편집 가능

#### 11-5. 검증

문법/실행 검증:

```bash
node --check VM_middle/frontend/app.js
docker exec vm_middle conda run -n myenv python -c "..."
```

확인 내용:

- `/ui/` 응답 정상
- 브라우저에서 새 레이아웃 반영 확인
- 프로젝트 클릭 시 상세 슬라이드오버 표시 확인
- 상세 닫기 버튼 존재 확인

---

## 2026-04-22 — 기존 VM Middle 백엔드 개선 내역

### 1. 소재 크기 추출 방식 변경

**파일**: `src/utils/xml_parser.py`, `src/services/vm_project.py`

#### 변경 전
- `dt_material` 엘리먼트 XML에서 소재 크기를 파싱

#### 변경 후
- 프로젝트 XML의 `its_workpieces.its_bounding_geometry.block.x/y/z` 값으로 소재 크기(min/max) 직접 추출
- `its_workpiece_setup.its_origin.location.coordinates`에서 원점 좌표 추출
- `its_workpiece_setup.its_workpiece.its_id` ↔ `its_workpieces.its_id` 매칭으로 원점과 크기 페어링
- 데이터 없으면 기존과 동일하게 `null` 처리

#### 추가된 함수 (`xml_parser.py`)
- `_extract_block_size(wp_raw)` — bounding geometry에서 x/y/z 추출
- `_extract_origin_coords(its_origin)` — 원점 좌표 추출
- `_walk_setups(workplan)` — 중첩 workplan의 setup 순회
- `extract_stock_bounds_from_project_xml(project_xml)` — 최종 min/max 딕셔너리 반환

#### stock 포맷 (`services/vm_project.py`)
- `_fmt_stock_size(bounds)` 추가: bounds 딕셔너리 → `"min_x,max_x,min_y,max_y,min_z,max_z"` 문자열 변환

---

### 2. stock_type 타입 변경 (int → str)

**파일**: `src/utils/stock.py`, `src/schemas/vm_project.py`, `src/services/vm_project.py`

#### 변경 이유
- 성공 사례인 `301_test.prj`의 `stock_type`이 문자열(`"9"`)인 반면, 기존 코드는 정수(`45`)로 처리
- VM 시스템과의 호환성을 위해 전면 문자열로 통일

#### 변경 내용
| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| `KNOWN_STOCK_CODES` | `set[int]` | `set[str]` |
| `lookup_stock_code()` 반환값 | `int \| None` | `str \| None` |
| `StockInfo.stock_type` | `Optional[int]` | `Optional[str]` |
| `ProjectFileOut.stock_type` | `Optional[int]` | `Optional[str]` |
| `StockPatchIn.stock_type` | `Optional[int]` | `Optional[str]` |
| `StockItemOut.code` | `int` | `str` |
| `list_stock_items()` 응답 | `int(it["code"])` | `str(it["code"])` |

---

### 3. DP 데이터 소스 연동 (source="dp")

**파일**: `src/clients/dp.py`, `src/services/vm_project.py`, `src/api/v1/vm_project.py`

#### 개요
ISO API 외에 DP(데이터 플랫폼) API를 두 번째 데이터 소스로 추가.
`POST /api/v1/vm-project` 요청 시 `source: "dp"` 필드로 분기.

#### DP API 인증
- `Authorization: {API_KEY}` (Bearer 아님)

#### DP API aid 포맷 수정
- **문제**: DP API는 `aid`를 전체 URL 형태(`gid/short_aid`)로 요구하나 단축 ID만 전달되어 400 오류 발생
- **수정**: 소재 및 공구 조회 시 `f"{gid}/{short_aid}"` 형태로 full URL 구성

```python
# 소재
dp_mat_aid = f"{mat_gid}/{mat_aid}"

# 공구
tool_aid = f"{tool_gid}/{tool_short_aid}" if tool_short_aid else None
```

---

### 4. ncdata.zip 압축 구조 변경

**파일**: `src/services/vm_project.py`

#### 변경 전
```
ncdata.zip 압축 해제 시:
  ncdata/
    분할폴더1/파일.nc
    분할폴더2/파일.nc
```

#### 변경 후
```
ncdata.zip 압축 해제 시:
  분할폴더1/파일.nc
  분할폴더2/파일.nc
```

#### 수정 내용
```python
# 변경 전
shutil.make_archive(zip_out, "zip", root_dir=work_dir, base_dir="ncdata")

# 변경 후
shutil.make_archive(zip_out, "zip", root_dir=ncdata_dir)
```
ISO flow, DP flow 두 곳 모두 적용.

## 2026-04-22 — 기존 VM Middle 백엔드 개선 내역 (계속)

### 5. VM start-vm API에 upload_result 옵션 추가

**파일**: `src/schemas/vm_project.py`, `src/dao/vm_project.py`, `src/services/vm_project.py`, `src/api/v1/vm_project.py`

#### 개요
VM 가상가공 완료 후 결과 파일 처리 방식을 사용자가 선택할 수 있도록 추가.

| 값 | 동작 |
|---|---|
| `upload_result: true` (기본값) | 결과 ZIP을 스트리밍으로 다운로드하여 DP에 파일+XML 업로드 |
| `upload_result: false` | 결과 파일 S3 링크만 dt_file XML의 `<path>`에 저장 |

#### 추가된 스키마
```python
class StartVmIn(BaseModel):
    upload_result: bool = Field(True, description="...")
```

#### 대용량 파일 처리
- 수백MB~GB 크기의 VM 결과 파일을 메모리에 올리지 않고 스트리밍으로 처리
- `_stream_download_to_tempfile(url)`: 4MB 청크 단위 스트리밍 다운로드 → 임시 파일 저장
- `finally` 블록에서 임시 파일 반드시 삭제

---

### 6. VM dt_file 플랫폼 업로드 기능 추가

**파일**: `src/clients/dp.py`, `src/services/vm_project.py`

#### 개요
VM 가상가공 COMPLETE 후 결과 dt_file XML을 생성하여 플랫폼에 등록.

#### dt_file XML 구조
- `element_id`: `vm_001`, `vm_002` ... (SEQ_ID 기반 자동 채번)
- `category`: `VM`
- `reference`: `DT_GLOBAL_ASSET`, `DT_ASSET`, `DT_PROJECT`, `WORKPLAN` 키로 원본 프로젝트 참조
- `properties`: `NO_CODE`, `SEQ_ID`, `Date`

#### DP API 분기
| upload_result | DP API | Content-Type |
|---|---|---|
| `true` | `POST /openapi/v2/asset/xml-with-file` | `multipart/form-data` (xmlData + files) |
| `false` | `POST /openapi/v2/asset/xml` | `application/xml` (raw body) |

> `/openapi/v2/asset/xml-with-file`은 파일 첨부 필수이므로 링크만 저장할 때는 반드시 `/openapi/v2/asset/xml`을 사용해야 함.

---

### 7. VM 상태 머신 개선

**파일**: `src/services/vm_project.py`

#### 7-1. ERROR 상태 처리 수정
- **문제**: `ERROR-ERR-UNKNOWN` 등 ERR 포함 상태값이 `else` 분기로 떨어져 `running` 유지
- **수정**: `"ERR" in (vm_state or "").upper()` 조건으로 ERR 포함 문자열 전부 `failed` 처리

#### 7-2. UPLOADING 상태 추가
- `"UPLOADING"` 상태를 `"WAIT"`, `"RUN"`과 동일하게 `running` 유지

```python
if vm_state in ("WAIT", "RUN", "UPLOADING"):
    new_status = "running"
```

---

### 8. dt_file 업로드 실패 시 폴링 루프 안정화 및 재시도 로직 추가

**파일**: `src/dao/vm_project.py`, `src/services/vm_project.py`

#### 문제
- dt_file 업로드 실패 시 예외가 `poll_vm_status`에서 올라가면서 DB 상태가 갱신되지 않음
- 재시도 횟수 제한 없이 무한 반복 가능성 존재

#### 해결

**DAO에 추가된 메서드**: `set_dt_file_upload_failed()`
- status는 `running` 유지
- `vm_dt_file_upload_attempts`, `vm_error_message`, `vm_raw_status` 갱신

**재시도 로직** (`poll_vm_status` COMPLETE 분기):
- 최대 3회 재시도
- 3회 미만 실패: `running` 유지 + 에러 메시지 기록 → 다음 폴링 주기에 재시도
- 3회 이상 실패: `failed` 처리 + `"VM dt_file 플랫폼 업로드 실패 (3/3회 시도): ..."` 메시지 저장

---

### 9. VM 프로젝트 리셋 엔드포인트 추가

**파일**: `src/dao/vm_project.py`, `src/services/vm_project.py`, `src/api/v1/vm_project.py`

#### 개요
`failed` 상태의 VM 프로젝트를 `ready`로 복원하여 재실행 가능하게 하는 엔드포인트.

```
POST /api/v1/vm-project/{vm_project_id}/reset
```

#### 동작
- `failed` 상태에서만 허용 (다른 상태는 400 반환)
- `vm_job_id`, `vm_error_message`, `vm_raw_status`, `vm_last_polled_at` 초기화
- `status` → `ready` 로 복원

#### 상태별 재실행 정책
| 상태 | 재실행 방법 |
|---|---|
| `failed` | `/reset` → `ready` 전환 후 `/start-vm` |
| `needs-fix` | stock/process 수정 API 호출 → validation 재실행 → `ready` 자동 전환 |
| `running` | 불가 (이미 실행 중) |
| `completed` | 불가 (새 프로젝트 생성 필요) |

---

### 10. 수동 폴링 엔드포인트 추가

**파일**: `src/api/v1/vm_project.py`

```
POST /api/v1/vm-project/{vm_project_id}/poll
```

- `running` 상태 프로젝트의 VM 상태를 즉시 조회
- 백그라운드 폴링 주기를 기다리지 않고 즉시 상태 확인 가능

---

### 11. 공구 데이터 숫자 포맷 변경

**파일**: `src/services/vm_project.py`

#### 변경 전
모든 숫자를 소수점 6자리로 고정 출력
```
1,40.000000,0.000000,20.000000,0.000000,...
```

#### 변경 후
정수면 소수점 없이, 소수점이 있는 경우만 소수점 표기
```
1,40,0,20,0,...
1,12.5,0,6.25,0,...
```

```python
def _fmt6(x):
    if not isinstance(x, (int, float)):
        return "null"
    return str(int(x)) if x % 1 == 0 else "{:g}".format(x)
```
ISO flow, DP flow, fill_tool_data 세 곳 모두 적용.

---

### 12. VM 프로젝트에 source 및 display_name 필드 추가

**파일**: `src/utils/xml_parser.py`, `src/schemas/vm_project.py`, `src/dao/vm_project.py`, `src/services/vm_project.py`

#### 추가된 필드

| 필드 | 설명 |
|---|---|
| `source` | 데이터 소스 구분 (`"iso"` 또는 `"dp"`) |
| `display_name` | 프로젝트 XML의 `<display_name>` 태그 값 |

#### display_name 활용
- 프로젝트 생성 시 XML에서 추출하여 DB 저장
- `start_vm_job`의 `machine_name` 파라미터에 `display_name` 우선 사용, 없으면 `eid` 폴백

```python
machine_name=str(doc.get("display_name") or doc.get("eid") or "")
```

#### 노출 위치
- `GET /api/v1/vm-project` (목록)
- `GET /api/v1/vm-project/{id}` (상세)

---

### 수정 파일 목록

| 파일 | 주요 변경 내용 |
|---|---|
| `src/utils/xml_parser.py` | 소재 크기 추출 함수 추가, `extract_project_summary`에 `display_name` 추가 |
| `src/utils/stock.py` | stock_type 전체 str 타입으로 변경 |
| `src/clients/dp.py` | `upload_xml()` 추가 (application/xml raw body), `upload_xml_with_file()` 스트리밍 업로드 |
| `src/schemas/vm_project.py` | `StartVmIn`, `source`, `display_name` 필드 추가, stock 타입 str 변경 |
| `src/dao/vm_project.py` | `insert_initial_from_iso`에 `display_name` 파라미터, `set_dt_file_upload_failed`, `reset_failed_to_ready` 추가 |
| `src/services/vm_project.py` | 소재 크기 추출, DP aid 포맷, 업로드 재시도, 상태머신, 숫자 포맷 등 다수 |
| `src/api/v1/vm_project.py` | `/reset`, `/poll` 엔드포인트 추가, `start_vm`에 `StartVmIn` 바디 추가 |

---

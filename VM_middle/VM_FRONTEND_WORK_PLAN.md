# VM_middle Frontend Work Plan

작성일: 2026-04-23

## 1. 목표

`VM_middle`에 VM 프로젝트를 관리하는 프론트엔드를 추가한다.

주요 사용자 흐름은 다음과 같다.

1. VM 프로젝트 목록을 조회한다.
2. 프로젝트를 선택해 `project.prj` 초안 데이터를 확인하고, 수정 가능한 상태에서는 stock/process를 수정한다.
3. ISO 또는 DP 소스 프로젝트와 workplan을 선택해 VM 프로젝트를 생성한다.
4. VM 프로젝트가 `ready` 상태가 되면 VM 실행 버튼을 활성화하고, 결과 등록 방식을 파일 업로드 또는 링크 저장 중 선택한다.

## 2. 현재 코드/컨테이너 확인 결과

### 2.1 Docker Compose

루트 `docker-compose.yaml` 기준 현재 서비스 구조는 다음과 같다.

| 서비스 | 역할 | 포트 | 비고 |
| --- | --- | --- | --- |
| `mongo` | MongoDB | `27017:27017` | `vm_project`, `vm_file`, GridFS 저장 |
| `iso-api` | ISO API | `8000:8000` | VM_middle의 ISO 데이터 소스 |
| `om` | Operation Manager | `8888:8000`, `8050:8050` | 별도 모듈 |
| `redis` | Redis | `6379:6379` | VM_middle dependency |
| `vm-middle` | FastAPI VM middleware | `8010:8000` | `./VM_middle:/app`, `./VM_middle/data:/data` bind mount |

네트워크는 외부 네트워크 `kitech_network`를 사용한다.

### 2.2 실행 중인 컨테이너

2026-04-23 기준 Docker에서 확인한 실행 컨테이너는 다음과 같다.

| 컨테이너 | 상태 |
| --- | --- |
| `vm_middle` | 실행 중, `8010 -> 8000` |
| `iso_api` | 실행 중, `8000 -> 8000` |
| `mongo_container` | 실행 중 |
| `redis_container` | 실행 중 |

컨테이너 내부 기준으로 `vm_middle` API 헬스체크는 정상이다.

```bash
docker exec vm_middle conda run -n myenv python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/healthz', timeout=5).read().decode())"
```

응답:

```json
{"ok": true}
```

### 2.3 현재 VM_middle API

프론트에서 바로 사용할 수 있는 API는 이미 대부분 준비되어 있다.

| 기능 | API |
| --- | --- |
| VM 프로젝트 목록 | `GET /api/v1/vm-project` |
| VM 프로젝트 상세 | `GET /api/v1/vm-project/{id}` |
| project.prj 조회 | `GET /api/v1/vm-project/{id}/project-file` |
| stock 목록 | `GET /api/v1/vm-project/stocks` |
| stock 수정 | `PATCH /api/v1/vm-project/{id}/project-file/stock` |
| process 수정 | `PATCH /api/v1/vm-project/{id}/project-file/process` |
| VM 시작 | `POST /api/v1/vm-project/{id}/start-vm` |
| failed -> ready 리셋 | `POST /api/v1/vm-project/{id}/reset` |
| 단일 VM 상태 폴링 | `POST /api/v1/vm-project/{id}/poll` |
| ISO 프로젝트 목록 | `GET /api/v1/iso-projects` |
| DP 프로젝트 목록 | `GET /api/v1/dp/projects` |
| DP workplan 목록 | `GET /api/v1/dp/projects/workplans` |

확인된 샘플 데이터:

- `GET /api/v1/vm-project?page=1&size=3` 결과: 총 13개 VM 프로젝트 존재
- `GET /api/v1/vm-project/stocks` 결과: 23개 stock type 반환
- DP 샘플 프로젝트 `v1`의 workplan 결과: `wp_001`, workingstep 8개

## 3. 권장 프론트 구성 방식

### 3.1 결론

1차 개발/테스트는 `VM_middle/frontend`에 React + TypeScript 프론트를 두고, 별도 `vm-middle-front` 컨테이너로 실행하는 방식을 권장한다.

운영 배포가 단순해야 한다면 2차에서 빌드 산출물만 FastAPI 컨테이너가 static으로 서빙하도록 바꾸는 하이브리드 방식을 추천한다.

### 3.2 별도 프론트 컨테이너를 권장하는 이유

| 항목 | 별도 프론트 컨테이너 | 기존 VM_middle 컨테이너에 포함 |
| --- | --- | --- |
| 개발 속도 | Vite HMR 사용 가능 | Python/Conda 이미지에 Node까지 추가 필요 |
| 책임 분리 | 프론트 의존성 격리 | 백엔드 이미지가 무거워짐 |
| 현재 컨테이너 테스트 | `vm-middle` API를 docker network로 호출 가능 | 백엔드 컨테이너 재빌드 빈도 증가 |
| CORS | Vite proxy로 회피 가능 | same-origin 가능 |
| 운영 단순성 | 컨테이너 1개 추가 | 컨테이너 수 유지 |

`VM_middle`은 현재 Miniconda 기반 Python 컨테이너이므로, 여기에 Node 개발 서버까지 같이 넣는 방식은 이미지와 런타임 책임이 섞인다. 개발 단계에서는 별도 컨테이너가 더 명확하다.

다만 운영에서는 다음 중 하나를 선택할 수 있다.

| 운영 방식 | 권장 시점 |
| --- | --- |
| 별도 nginx/static 컨테이너 유지 | OM 등 다른 웹 모듈과 독립 운영할 때 |
| FastAPI가 `frontend/dist`를 static mount | VM_middle을 단일 배포 단위로 유지하고 싶을 때 |

## 4. 제안 기술 스택

| 영역 | 선택 |
| --- | --- |
| Framework | Vite + React + TypeScript |
| Data fetching | TanStack Query |
| Form validation | React Hook Form 또는 TanStack Form + Zod |
| UI | TailwindCSS + shadcn/ui |
| API client | OpenAPI 기반 생성 또는 수동 typed client |
| 테스트 | Vitest, Testing Library, Playwright |

폴더 구조 초안:

```text
VM_middle/
  frontend/
    Dockerfile
    package.json
    vite.config.ts
    src/
      app/
      features/
        vm-projects/
          api/
          components/
          pages/
          types/
          utils/
      shared/
        api/
        components/
        lib/
```

## 5. 화면 구성 계획

### 5.1 VM 프로젝트 목록 화면

목표:

- VM 프로젝트 리스트를 보여준다.
- 좌측에는 선택된 프로젝트의 이미지 또는 프리뷰 영역을 둔다.
- 우측에는 프로젝트 테이블/카드 리스트를 둔다.

구성:

| 영역 | 내용 |
| --- | --- |
| 좌측 프리뷰 | 프로젝트 이미지, 없으면 stock/process 기반 schematic placeholder |
| 상단 필터 | 상태 필터, 검색어, source 필터, 새로고침 |
| 리스트 | 이름, source, status, validation error count, gid/aid/eid, wpid, updated_at |
| 액션 | 상세 열기, failed reset, ready start shortcut |

현재 백엔드에는 프로젝트 이미지/thumbnail API가 없다. DP는 `dt_file` XML의 `TITLE_IMAGE` 규칙으로 썸네일을 가져올 수 있으므로, 1차부터 DP 프로젝트 이미지는 실제 이미지 조회를 목표로 한다.

1. DP 프로젝트는 프로젝트를 참조하는 `dt_file` 중 `<category>TITLE_IMAGE</category>`인 asset을 찾는다.
2. 해당 asset의 `<path>` 값으로 DP 파일 다운로드 API를 호출해 썸네일 이미지를 가져온다.
3. 이미지가 없거나 다운로드 실패 시 UI는 `No image` placeholder를 보여준다.
4. ISO 프로젝트는 현재 이미지가 있는 프로젝트가 확인되지 않았으므로, 우선 `No image` 또는 `project_file_draft.stock_size` 기반 schematic preview로 처리한다.

추가 API 후보:

```text
GET /api/v1/vm-project/{id}/thumbnail
```

또는 목록 응답에 `thumbnail_url`을 추가한다.

DP 썸네일 탐색 규칙:

```text
1. vm_project의 source가 "dp"인지 확인한다.
2. dp_client.list_elements_by_gid(gid)로 같은 global asset 아래 element 목록을 조회한다.
3. type이 file 또는 dt_file인 후보를 순회한다.
4. 각 후보의 xmlStr을 dp_client.get_element_xml(aid, eid)로 조회한다.
5. dt_file XML에서 category, path, content_type, reference keys를 파싱한다.
6. category == "TITLE_IMAGE"이고 reference가 현재 프로젝트를 가리키면 선택한다.
   - DT_GLOBAL_ASSET == vm_project.gid
   - DT_PROJECT == vm_project.eid
   - DT_ASSET은 DP에서는 short id와 full URI가 섞일 수 있으므로 보조 검증으로 사용한다.
7. path가 있으면 DP 다운로드 API로 bytes를 내려받아 image response로 반환한다.
8. 후보가 없거나 path가 비어 있으면 404 또는 no-image 응답을 반환한다.
```

샘플 XML 기준:

```xml
<dt_elements xsi:type="dt_file">
  <category>TITLE_IMAGE</category>
  <display_name>301_thumbnail.png</display_name>
  <content_type>image/png</content_type>
  <path>...</path>
  <reference>
    <keys>
      <key>DT_GLOBAL_ASSET</key>
      <value>https://digital-thread.re/kitech/iso301_verification_test</value>
    </keys>
    <keys>
      <key>DT_ASSET</key>
      <value>iso301</value>
    </keys>
    <keys>
      <key>DT_PROJECT</key>
      <value>iso301_test_cut</value>
    </keys>
  </reference>
</dt_elements>
```

### 5.2 VM 프로젝트 상세/수정 화면

목표:

- 선택한 프로젝트의 `prj` 데이터를 보여준다.
- 수정 가능한 상태에서는 stock/process를 수정한다.
- stock type 선택 시 stock 목록을 보여준다.

구성:

| 섹션 | 내용 |
| --- | --- |
| Header | display_name/proj_name, status badge, source, validation 상태 |
| Source metadata | gid, aid, eid, wpid |
| Stock editor | stock_type combobox, stock_size 6개 좌표 입력 |
| Process editor | process table, file_path, output_dir_path, tool_data |
| Validation panel | validation_errors 목록, 수정 후 재검증 결과 |
| VM panel | ready 상태에서 VM start 버튼, upload_result 선택 |

수정 정책:

- 현재 백엔드 기준 수정 가능 상태는 `ready`, `needs-fix`이다.
- `running`, `completed`, `failed`는 수정 API에서 차단된다.
- 사용자는 "completed, failed가 아니면 수정"을 원했지만, `running` 중 수정은 VM job 정합성 문제가 생길 수 있으므로 UI도 `ready`, `needs-fix`만 편집 가능으로 시작하는 것을 권장한다.
- 필요하면 정책을 바꿔 `running` 제외, `ready/needs-fix` 허용으로 명시한다.

Stock type UX:

- `GET /api/v1/vm-project/stocks?q=`로 검색 가능한 combobox를 구성한다.
- 선택값은 stock code를 저장하고, name은 표시용으로만 사용한다.
- 저장 시 `PATCH /api/v1/vm-project/{id}/project-file/stock` 호출.

Process UX:

- process가 8개 이상으로 길 수 있으므로 table 기반 편집을 우선한다.
- `tool_data`는 9개 comma-separated field이므로 1차는 원문 편집 + validation 표시로 시작한다.
- 2차에서 tool_data field editor로 나눈다.

### 5.3 VM 프로젝트 생성 Wizard

목표:

- source를 `iso` 또는 `dp`로 선택한다.
- 선택한 source의 프로젝트 목록을 보여준다.
- 프로젝트 선택 후 workplan 목록을 보여준다.
- workplan까지 선택하면 VM 프로젝트를 생성한다.

Step 구성:

1. Source 선택: `iso`, `dp`
2. 프로젝트 선택
3. Workplan 선택
4. 생성 확인
5. 생성 결과 상세로 이동

Source별 API:

| Source | 프로젝트 목록 | Workplan 목록 |
| --- | --- | --- |
| ISO | `GET /api/v1/iso-projects` | 목록 응답의 `wpid[]` 사용 |
| DP | `GET /api/v1/dp/projects` | `GET /api/v1/dp/projects/workplans?gid=&aid=&eid=` |

DP 프로젝트 선택 화면에서는 썸네일 preview를 위해 아래 API를 함께 사용한다.

```text
GET /api/v1/dp/projects/thumbnail?gid=&aid=&eid=
```

ISO의 경우 현재 프로젝트 목록 응답에 `main_wpid`, `wpid[]`가 포함되어 있으므로 1차 UI 구현은 가능하다. 다만 DP와 동일하게 `ws_count`, `pattern`을 보여주려면 ISO에도 별도 workplan endpoint를 추가하는 것이 좋다.

추가 API 후보:

```text
GET /api/v1/iso-projects/workplans?gid=&aid=&eid=
```

생성 API:

```http
POST /api/v1/vm-project
Content-Type: application/json

{
  "source": "dp",
  "gid": "...",
  "aid": "...",
  "eid": "...",
  "wpid": "wp_001"
}
```

생성은 NC 다운로드, split, GridFS 저장, validation까지 수행하므로 오래 걸릴 수 있다. UI는 생성 중 progress 상태와 timeout/error 처리를 갖춰야 한다.

### 5.4 VM Start 패널

목표:

- 프로젝트가 `ready` 상태일 때만 VM start 버튼을 활성화한다.
- 결과 업로드 방식을 선택한다.

옵션:

| UI 라벨 | API 값 | 의미 |
| --- | --- | --- |
| 결과 ZIP 파일 직접 업로드 | `upload_result: true` | VM 완료 후 ZIP을 받아 데이터 플랫폼에 파일로 업로드 |
| 결과 링크만 저장 | `upload_result: false` | VM 결과 download link를 `dt_file.path`에 저장 |

API:

```http
POST /api/v1/vm-project/{id}/start-vm
Content-Type: application/json

{
  "upload_result": true
}
```

주의:

- 이 API는 외부 VM 서버와 DP/ISO 등록까지 이어질 수 있으므로 자동 테스트에서는 호출하지 않는다.
- UI/E2E에서는 mock 또는 테스트 전용 프로젝트로만 확인한다.

## 6. Backend 보완 항목

1차 프론트 구현 전에 꼭 필요한 보완은 많지 않다. 다만 사용성이 좋아지는 보완 항목은 다음과 같다.

| 우선순위 | 항목 | 이유 |
| --- | --- | --- |
| P0 | API proxy 또는 CORS 정책 결정 | 별도 프론트 컨테이너 사용 시 필요 |
| P1 | ISO workplan endpoint 추가 | DP와 동일한 생성 wizard UX 제공 |
| P1 | 목록 응답에 project_file 요약 추가 | 리스트에서 stock/process 요약 표시 |
| P1 | DP thumbnail/image endpoint 추가 | `TITLE_IMAGE` dt_file을 찾아 좌측 프로젝트 이미지 표시 |
| P2 | structured validation error schema | 필드별 에러 하이라이트 개선 |
| P2 | process item patch API | 전체 process 배열 대신 한 row만 저장 가능 |

P0는 Vite proxy를 쓰면 백엔드 CORS 없이 해결할 수 있다.

DP thumbnail endpoint를 위해 필요한 백엔드 보완:

- `parse_dt_file_xml()` 반환값에 `<path>`와 `<content_type>`을 추가한다.
- `dp_client.download_nc_file()`과 동일한 `/openapi/v2/files/download/userdata?path=` 경로를 bytes 반환용 `download_user_file(path)`로 일반화한다.
- `VmProjectService`에 `find_dp_title_image()` 또는 `get_thumbnail()`을 추가해 `TITLE_IMAGE` 후보 탐색과 reference 매칭을 담당하게 한다.
- API는 이미지가 있으면 `StreamingResponse` 또는 `Response(bytes, media_type=content_type)`를 반환하고, 없으면 `404` 또는 `{ "has_image": false }` 형태의 metadata endpoint를 함께 제공한다.

## 7. Docker 적용 계획

### 7.1 개발용 compose 추가

루트 `docker-compose.yaml`에 다음 서비스를 추가하는 방향을 권장한다.

```yaml
vm-middle-front:
  build:
    context: ./VM_middle/frontend
  container_name: vm_middle_front
  depends_on:
    - vm-middle
  volumes:
    - ./VM_middle/frontend:/app
    - /app/node_modules
  ports:
    - "3010:5173"
  environment:
    VITE_API_BASE_URL: /api
  networks:
    - kitech_network
```

`vite.config.ts`에서는 API proxy를 둔다.

```ts
server: {
  host: "0.0.0.0",
  port: 5173,
  proxy: {
    "/api": {
      target: "http://vm-middle:8000",
      changeOrigin: true,
    },
  },
}
```

브라우저는 `http://localhost:3010`으로 접근하고, API는 프론트 컨테이너가 docker network 내부에서 `http://vm-middle:8000`으로 프록시한다.

### 7.2 운영 배포 후보

운영에서 컨테이너 수를 줄이고 싶으면 다음 방식을 2차로 적용한다.

1. frontend를 build한다.
2. `VM_middle/frontend/dist`를 FastAPI static route로 mount한다.
3. `http://vm-middle-host:8010/vm` 또는 `/`에서 UI를 제공한다.

FastAPI 예시:

```python
from fastapi.staticfiles import StaticFiles

app.mount("/vm", StaticFiles(directory="frontend/dist", html=True), name="vm-ui")
```

## 8. 구현 순서

### Phase 0. 계약 정리와 스캐폴딩

- `VM_middle/frontend` 생성
- Vite React TypeScript 설정
- API base/proxy 설정
- Dockerfile 및 compose service 추가
- 공통 API client와 타입 정의

완료 기준:

- `vm_middle_front` 컨테이너가 실행된다.
- 브라우저에서 프론트가 열린다.
- 프론트에서 `/api/v1/vm-project` 호출이 성공한다.

### Phase 1. 프로젝트 목록/상세 조회

- VM 프로젝트 목록 화면
- 상태 필터, 검색, 페이지네이션
- 좌측 프리뷰 placeholder
- 상세 패널/페이지 연결

완료 기준:

- 현재 컨테이너의 13개 프로젝트 목록을 UI에서 볼 수 있다.
- 프로젝트 선택 시 상세 API가 호출되고 `project_file_draft`가 표시된다.

### Phase 2. 상세 수정 기능

- stock combobox
- stock_size 입력
- process table 편집
- validation error 표시
- 저장 후 상세 재조회

완료 기준:

- `ready`, `needs-fix`에서 stock/process 저장 가능
- `running`, `completed`, `failed`에서는 UI가 read-only
- 백엔드 validation error가 UI에 반영됨

### Phase 3. 생성 Wizard

- source 선택
- ISO 프로젝트 목록 조회 및 workplan 선택
- DP 프로젝트 목록 조회 및 workplan 선택
- 생성 요청
- 생성 완료 후 상세로 이동

완료 기준:

- DP 샘플 프로젝트에서 `wp_001`을 선택해 생성 요청 가능
- 생성 실패 시 upstream/API 에러 메시지를 사용자에게 보여줌

### Phase 4. VM Start

- ready 상태에서만 start 버튼 활성화
- upload_result 선택 UI
- start-vm 호출 후 running 상태 반영
- 수동 poll 버튼 또는 자동 refetch

완료 기준:

- ready 프로젝트에서 `upload_result` true/false payload가 정확히 전송됨
- running 전환 후 편집 UI가 비활성화됨

### Phase 5. 테스트/정리

- API smoke test 스크립트 추가
- 프론트 unit test 추가
- Playwright E2E 추가
- README 또는 운영 문서 보강

## 9. 컨테이너 기반 테스트 계획

사용자 요청대로 테스트는 실행 중인 컨테이너 기준으로 수행한다.

### 9.1 Backend smoke test

컨테이너 내부에서 실행한다.

```bash
docker exec vm_middle conda run -n myenv python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/healthz', timeout=5).read().decode())"
```

```bash
docker exec vm_middle conda run -n myenv python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/api/v1/vm-project?page=1&size=3', timeout=10).read().decode()[:2000])"
```

```bash
docker exec vm_middle conda run -n myenv python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/api/v1/vm-project/stocks', timeout=10).read().decode()[:2000])"
```

DP workplan 확인:

```bash
docker exec vm_middle conda run -n myenv python -c "import urllib.parse, urllib.request; gid='https://digital-thread.re/kitech/vm_test_iso301'; aid='https://digital-thread.re/kitech/vm_test_iso301/vm_test_project'; eid='v1'; qs=urllib.parse.urlencode({'gid':gid,'aid':aid,'eid':eid}); print(urllib.request.urlopen('http://localhost:8000/api/v1/dp/projects/workplans?'+qs, timeout=15).read().decode()[:2000])"
```

### 9.2 Frontend container test

프론트 컨테이너 추가 후:

```bash
docker compose up -d vm-middle-front
docker compose exec vm-middle-front npm run lint
docker compose exec vm-middle-front npm run test
```

프론트 API proxy 확인:

```bash
docker compose exec vm-middle-front node -e "fetch('http://localhost:5173/api/v1/vm-project?page=1&size=1').then(r=>r.text()).then(t=>console.log(t.slice(0,1000)))"
```

### 9.3 E2E 시나리오

Playwright 기준 최소 시나리오:

1. 프로젝트 목록 화면 진입
2. 첫 번째 프로젝트 선택
3. 상세 데이터 표시 확인
4. `needs-fix` 프로젝트에서 validation error 표시 확인
5. stock combobox 검색 및 선택
6. `completed` 프로젝트에서 편집 비활성화 확인
7. 생성 wizard에서 DP 프로젝트 선택 후 workplan 목록 표시 확인
8. ready 프로젝트에서 upload_result 옵션 변경 후 start 버튼 payload 확인

외부 VM 서버를 호출하는 실제 `start-vm` E2E는 자동화하지 않고, 테스트 전용 ready 프로젝트를 대상으로 수동 검증한다.

## 10. 주요 리스크와 대응

| 리스크 | 영향 | 대응 |
| --- | --- | --- |
| 프로젝트 이미지 데이터 부재 | 좌측 이미지 요구사항 미충족 | 1차 schematic preview, 2차 thumbnail API |
| ISO/DP upstream 지연 | 생성 wizard UX 저하 | loading, timeout, retry, 에러 메시지 |
| VM 프로젝트 생성 시간이 김 | 사용자가 멈춘 것으로 오해 | 생성 중 상태 표시, 중복 제출 방지 |
| running 중 수정 정책 불명확 | VM job 정합성 문제 | `ready/needs-fix`만 편집 가능으로 시작 |
| `tool_data` 원문 편집 어려움 | 사용성 저하 | 1차 raw editor, 2차 structured editor |
| 실제 VM start의 외부 부작용 | 테스트 데이터 오염 | 자동 테스트에서 제외, 수동 승인 기반 검증 |

## 11. 첫 구현 범위 제안

1차 PR 범위는 아래로 제한하는 것이 좋다.

1. `VM_middle/frontend` 스캐폴딩
2. 개발용 `vm-middle-front` 컨테이너 추가
3. VM 프로젝트 목록/상세 조회
4. stock 목록 combobox와 stock 저장
5. ready 상태 VM start UI와 `upload_result` payload 연결

생성 wizard와 process table 편집은 2차 PR로 분리하면 검증과 리뷰가 쉬워진다.

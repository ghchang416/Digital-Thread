# Toolpath Alignment 3D Viewer Implementation Plan

작성일: 2026-05-08

대상: VM Middle React frontend, FastAPI backend

관련 기능: Project Detail > Stock > Toolpath Alignment

---

## 1. 목표

VM 프로젝트 상세 화면의 Stock 섹션에서 NC 파일 기반 toolpath와 소재 `stock_size` min/max box를 같은 3D 좌표계에 표시한다.

사용자는 VM 실행 전에 다음을 확인할 수 있어야 한다.

- NC toolpath가 소재 box 안쪽 또는 의도한 위치에 놓여 있는지
- `stock_size`의 `x_min`, `x_max`, `y_min`, `y_max`, `z_min`, `z_max` 값이 toolpath와 정합적인지
- 소재 좌표를 수정할 때 viewer의 소재 box가 즉시 바뀌는지
- 저장 후 서버 데이터와 viewer가 다시 동기화되는지

이 기능은 시각화 보조 기능이다. VM 실행에 쓰이는 `project.prj` 계약과 `ncdata.zip` 업로드 구조는 변경하지 않는다.

---

## 2. 적용 원칙

### Vercel React Best Practices 적용

| 원칙 | 적용 방식 |
| --- | --- |
| Client-side data fetching | Toolpath preview를 TanStack Query 독립 query로 관리 |
| Stable query key | `["toolpath-preview", projectId]` 사용 |
| Server state와 local state 분리 | toolpath segment는 서버 query, stock 입력 draft는 React local state |
| Mutation 후 invalidate | stock/process 저장 성공 후 detail, list, toolpath-preview query 갱신 |
| 직접 import | viewer, API, type을 필요한 파일에서 직접 import |
| Feature 근접 배치 | VM project 관련 API/type/component는 `features/vm-projects` 아래 유지 |

### Impeccable Product UI 적용

| 원칙 | 적용 방식 |
| --- | --- |
| Product register | 업무용 제조 데이터 검증 도구로 설계 |
| Restrained color strategy | 중립 작업면 위에 KITECH blue, green, semantic status color만 사용 |
| 상태 가독성 | loading, empty, error, truncated, invalid stock 상태를 텍스트와 함께 표시 |
| Predictable controls | Top, Front, Side, Fit 같은 명확한 view control 제공 |
| Dense but calm | viewer, metric, legend, action을 한 섹션 안에서 조밀하게 구성 |
| Data contract 보존 | viewer용 metadata는 API 응답에만 두고 `project.prj`에는 섞지 않음 |

---

## 3. 1차 구현 범위

1차 구현은 실제 사용 가능한 3D preview를 목표로 한다.

- FastAPI `toolpath-preview` API 추가
- GridFS의 `ncdata.zip` 로드
- zip 내부 NC 파일과 `project_file_draft.process[].file_path` 매칭
- `NCParser.parse_as_segments()` 활용
- 소재 box와 toolpath bounds 계산
- React에서 TanStack Query로 preview 데이터 조회
- Three.js 기반 3D viewer 구현
- 소재 `stock_size` 입력값을 저장 전에도 viewer에 즉시 반영
- segment type별 색상 구분
- loading, empty, error, truncated 상태 표시
- Top, Front, Side, Fit 버튼 제공

1차에서 제외한다.

- G2/G3 원호 중간점 보간
- 실제 3D ViewCube 위젯
- segment 클릭 선택 및 tooltip
- process별 visibility toggle
- tool number별 색상 필터
- WebWorker 기반 대용량 렌더링 최적화

---

## 4. 기존 도구 분석 반영

### `occ_viewer`

위치:

```text
VM_middle/data/nc_visualizer_tool/libs/occ_viewer/
```

성격:

- `pythonOCC(OpenCASCADE)`와 `PySide6` 기반 데스크톱 3D viewer interaction 모듈
- `AIS_ViewController`, `AIS_AnimationCamera`, `QTimer`, Qt mouse event 사용

활용 방식:

- React 브라우저 UI에 직접 재사용하지 않는다.
- 회전, 이동, 줌, ViewCube, fit-to-view 같은 UX 개념만 참고한다.

### `nc_toolkit`

위치:

```text
VM_middle/data/nc_visualizer_tool/libs/nc_toolkit/
```

성격:

- Python 표준 라이브러리 기반 NC/G-Code parser
- 외부 의존성이 없어 FastAPI backend에서 재사용 가능
- 실제 구현에서는 `data` 폴더를 런타임 import 대상으로 두지 않는다.
- `NCParser` 구현은 `VM_middle/src/utils/nc_parser.py`로 복사해 배포 가능한 backend source로 관리한다.

활용 방식:

- `NCParser.parse_as_segments(file_path)`를 사용한다.
- 반환 segment의 `start`, `end`, `type`, `mode`, `feedrate`, `arc_i/j/k`를 preview API 응답으로 변환한다.
- 원호는 1차에서는 start/end 직선 segment로 표시하고, 2차에서 interpolation을 추가한다.

---

## 5. 백엔드 설계

### 5.1 API

추가 endpoint:

```text
GET /api/v1/vm-project/{vm_project_id}/toolpath-preview
```

Query parameters:

| 이름 | 기본값 | 설명 |
| --- | --- | --- |
| `max_segments` | `20000` | 응답에 포함할 최대 segment 수 |
| `include_rapid` | `true` | `RAPID` segment 포함 여부 |
| `process_index` | 없음 | 특정 process만 보고 싶을 때 사용, 1차에서는 optional |

### 5.2 응답 schema

```json
{
  "stock": {
    "min": [0, 0, 0],
    "max": [100, 50, 20],
    "source": "project_file_draft.stock_size"
  },
  "toolpath_bounds": {
    "min": [-75, -49.038, -40.997],
    "max": [73, 48.1, 150]
  },
  "segments": [
    {
      "process_index": 0,
      "file_path": "ncdata\\merge_1\\merge_1.tap",
      "type": "FEED",
      "mode": "FEED",
      "start": [-70.1, -36.6, -0.5],
      "end": [-69.0, -36.6, -0.5],
      "feedrate": 500
    }
  ],
  "files": [
    {
      "process_index": 0,
      "file_path": "ncdata\\merge_1\\merge_1.tap",
      "segment_count": 1240,
      "type_counts": {
        "FEED": 1200,
        "RAPID": 25,
        "PLUNGE": 1
      }
    }
  ],
  "summary": {
    "segment_count": 6883,
    "returned_segment_count": 6883,
    "truncated": false,
    "process_count": 2,
    "type_counts": {
      "FEED": 6798,
      "RAPID": 66,
      "SKIM": 17,
      "PLUNGE": 2
    }
  }
}
```

### 5.3 Backend file changes

예상 수정 파일:

```text
VM_middle/src/schemas/vm_project.py
VM_middle/src/services/vm_project.py
VM_middle/src/api/v1/vm_project.py
```

예상 추가 파일:

```text
VM_middle/src/utils/toolpath_preview.py
```

### 5.4 Backend processing flow

```text
GET /toolpath-preview
  ↓
VmProjectService.get_toolpath_preview()
  ↓
vm_project 문서 조회
  ↓
project_file_draft.stock_size 파싱
  ↓
latest_files["nc-split-zip"] 확인
  ↓
vm_file 조회
  ↓
GridFS bytes 로드
  ↓
zip 내부 파일 목록 확인
  ↓
process[].file_path를 zip path로 normalize
  ↓
NC 파일 임시 추출 또는 bytes 기반 임시 파일 생성
  ↓
NCParser.parse_as_segments()
  ↓
segment normalize, bounds 계산, max_segments 제한
  ↓
ToolpathPreviewOut 반환
```

### 5.5 Path matching policy

`project_file_draft.process[].file_path`는 Windows style 경로일 수 있다.

예:

```text
ncdata\\merge_1\\merge_1.tap
```

zip 내부 경로는 POSIX style일 가능성이 높다.

예:

```text
merge_1/merge_1.tap
ncdata/merge_1/merge_1.tap
```

매칭 정책:

1. `\\`를 `/`로 변환한다.
2. 앞의 `ncdata/` prefix가 있으면 제거한 후보도 만든다.
3. zip entry 전체 경로와 exact match를 먼저 시도한다.
4. exact match 실패 시 basename과 suffix match를 시도한다.
5. 그래도 실패하면 해당 process file summary에 error를 남기고 나머지 process를 계속 처리한다.

### 5.6 Segment limit policy

NC 파일은 수천에서 수만 segment가 될 수 있다.

1차 정책:

- 기본 `max_segments=20000`
- 전체 segment 수가 제한 이하이면 그대로 반환
- 제한 초과 시 균등 sampling으로 반환하고 `truncated=true`
- `summary.segment_count`와 `summary.returned_segment_count`를 모두 제공

이 정책은 큰 파일에서도 UI가 멈추지 않게 하기 위한 최소 안전장치다.

---

## 6. 프론트엔드 설계

### 6.1 API와 type

수정 파일:

```text
VM_middle/frontend/src/features/vm-projects/api/vm-projects-api.ts
VM_middle/frontend/src/features/vm-projects/types/vm-project.ts
```

추가 type 예시:

```ts
export type ToolpathSegmentType =
  | "RAPID"
  | "FEED"
  | "PLUNGE"
  | "RETRACT"
  | "SKIM"
  | "LEAD_LINK";

export interface ToolpathSegment {
  process_index: number;
  file_path: string;
  type: ToolpathSegmentType | string;
  mode: string;
  start: [number, number, number];
  end: [number, number, number];
  feedrate: number | null;
}

export interface ToolpathPreviewResponse {
  stock: {
    min: [number, number, number];
    max: [number, number, number];
    source: string;
  } | null;
  toolpath_bounds: {
    min: [number, number, number];
    max: [number, number, number];
  } | null;
  segments: ToolpathSegment[];
  summary: {
    segment_count: number;
    returned_segment_count: number;
    truncated: boolean;
    process_count: number;
    type_counts: Record<string, number>;
  };
}
```

API function:

```ts
export function getToolpathPreview(id: string) {
  return apiGet<ToolpathPreviewResponse>(
    `${VM_PROJECTS_BASE}/${encodeURIComponent(id)}/toolpath-preview`,
  );
}
```

Query key:

```ts
["toolpath-preview", projectId]
```

### 6.2 Component structure

예상 추가 컴포넌트:

```text
frontend/src/features/vm-projects/components/toolpath-alignment-viewer.tsx
```

기존 `StockToolpathPreview`는 다음 역할로 교체한다.

```tsx
<ToolpathAlignmentPanel
  projectId={detail.id}
  stockSizeFields={stockSizeFields}
  savedStockSize={draft.stock_size}
  processCount={draft.process_count}
/>
```

내부 구조:

```text
ToolpathAlignmentPanel
  ├── useQuery(["toolpath-preview", projectId])
  ├── Stock draft validation
  ├── ToolpathAlignmentViewer
  ├── Legend
  ├── Bounds metrics
  └── State notices
```

### 6.3 Three.js viewer

필요 dependency:

```bash
npm install three
```

1차 viewer 구성:

- `Scene`
- `PerspectiveCamera`
- `WebGLRenderer`
- `OrbitControls`
- `AxesHelper`
- `GridHelper`
- stock box mesh
- stock box edge line
- toolpath line segments

segment 색상:

| Type | 의미 | 색상 역할 |
| --- | --- | --- |
| `FEED` | 절삭 이송 | KITECH green 또는 success 계열 |
| `RAPID` | 급속 이동 | danger 또는 red 계열 |
| `PLUNGE` | 하강 진입 | info blue 계열 |
| `RETRACT` | 상승 퇴피 | warning 계열 |
| `SKIM` | 링크 이동 | muted accent 계열 |

색상은 CSS token 값을 읽어 사용하거나 TS 상수로 semantic color를 정의한다.

### 6.4 Stock 좌표 live preview

중요한 UX:

사용자가 stock 좌표를 수정하면 저장 전에도 viewer의 소재 box가 즉시 바뀌어야 한다.

데이터 우선순위:

```text
stock box 렌더링
  1순위: 현재 form draft stockSizeFields
  2순위: toolpath-preview API의 stock
```

toolpath 데이터:

```text
toolpath line 렌더링
  항상 toolpath-preview API의 segments 사용
```

즉, NC toolpath는 서버 preview API에서 가져오고, 소재 box는 현재 입력 중인 프론트 local state를 우선 사용한다.

흐름:

```text
사용자 stock 좌표 수정
  ↓
stockSizeFields local state 변경
  ↓
ToolpathAlignmentViewer props 변경
  ↓
stock box geometry 업데이트
  ↓
저장 전에도 화면 즉시 반영
```

저장 성공 후:

```ts
queryClient.invalidateQueries({ queryKey: ["vm-project", projectId] });
queryClient.invalidateQueries({ queryKey: ["vm-projects"] });
queryClient.invalidateQueries({ queryKey: ["toolpath-preview", projectId] });
```

### 6.5 UI states

| 상태 | 표시 내용 |
| --- | --- |
| Loading | skeleton 또는 canvas overlay로 `Loading toolpath` 표시 |
| Empty | `ncdata.zip` 또는 process file이 없다는 안내 |
| Error | API error message와 retry 버튼 |
| Invalid stock draft | viewer stock box 업데이트 중지, 입력 오류와 함께 안내 |
| Truncated | 전체 segment 중 일부만 표시 중이라는 badge 표시 |
| Ready | viewer, bounds metric, legend, segment count 표시 |

---

## 7. 데이터 계약과 저장 정책

이 기능은 UI preview 기능이다.

변경하지 않는 것:

- `project.prj` JSON 구조
- `project_file_draft.process[].file_path`
- `project_file_draft.stock_size` CSV 포맷
- VM start payload
- VM server upload payload

추가되는 것:

- preview 전용 API response
- preview 전용 frontend type/component
- 필요 시 preview helper 함수

저장 정책:

- Stock 좌표 수정은 기존 `PATCH /project-file/stock`만 사용한다.
- Viewer에서 만든 camera 상태, selected segment, view mode 같은 UI 상태는 서버에 저장하지 않는다.
- 2차에서 사용자별 viewer preference가 필요해지면 별도 UI preference 저장으로 분리한다.

---

## 8. 검증 계획

### Backend

확인 항목:

- `stock_size` 6개 값 파싱
- `ncdata.zip` GridFS 로드
- zip 내부 NC 파일 매칭
- `NCParser.parse_as_segments()` 결과 변환
- segment bounds 계산
- `max_segments` 제한 동작
- zip 없음, file_path 없음, NC 파싱 실패 시 graceful error

명령:

```bash
docker exec vm_middle python -m pytest
```

테스트가 부족한 경우 최소 수동 확인:

```bash
docker exec vm_middle bash -lc "python - <<'PY'
# call service or endpoint-level smoke test
PY"
```

### Frontend

확인 항목:

- TypeScript typecheck
- production build
- `Toolpath Alignment` panel loading, empty, error, ready 상태
- stock 좌표 변경 시 viewer box 즉시 업데이트
- Save 성공 후 detail/list/toolpath-preview query 갱신
- 320px, 768px, 1024px, 1440px responsive layout

명령:

```bash
docker exec vm_middle_front npm run typecheck
docker exec vm_middle_front npm run build
```

브라우저 확인:

```text
http://localhost:3010
http://localhost:8010/ui/
```

---

## 9. 구현 순서

### Phase 1. Backend preview data

1. `ToolpathPreviewOut` 관련 schema 추가
2. `src/utils/toolpath_preview.py` 추가
3. `VmProjectService.get_toolpath_preview()` 추가
4. router endpoint 추가
5. 샘플 NC 또는 실제 VM 프로젝트 기준 API 응답 확인

완료 기준:

- `GET /api/v1/vm-project/{id}/toolpath-preview`가 stock, bounds, segments, summary를 반환한다.

### Phase 2. Frontend data connection

1. TypeScript response type 추가
2. `getToolpathPreview()` API 함수 추가
3. `project-detail-drawer.tsx`에서 TanStack Query 연결
4. stock/process 저장 성공 후 `toolpath-preview` invalidate 추가

완료 기준:

- React에서 toolpath preview API 응답을 안정적으로 조회한다.

### Phase 3. 3D viewer

1. `three` dependency 추가
2. `ToolpathAlignmentViewer` 구현
3. stock box geometry 구현
4. toolpath line segments 구현
5. OrbitControls, axes, grid, fit-to-view 구현
6. legend와 metrics 표시

완료 기준:

- 실제 NC toolpath와 stock box가 같은 3D canvas에 표시된다.

### Phase 4. Stock live preview

1. viewer가 `stockSizeFields` draft를 우선 사용하도록 연결
2. invalid draft일 때 viewer box 업데이트 중지
3. reset/save 동작과 viewer 상태 동기화

완료 기준:

- 사용자가 stock 좌표를 수정하면 저장 전에도 소재 box가 즉시 반영된다.

### Phase 5. Polish and hardening

1. loading, empty, error, truncated 상태 정리
2. large segment performance 확인
3. keyboard 접근 가능한 view buttons 추가
4. responsive layout 확인
5. changelog 업데이트

완료 기준:

- 운영자가 실제 VM 프로젝트 detail drawer에서 toolpath와 소재 정합성을 확인할 수 있다.

---

## 10. 2차 개선 후보

| 개선 항목 | 설명 |
| --- | --- |
| Arc interpolation | G2/G3 원호를 16분할 또는 adaptive segment로 보간 |
| ViewCube | `occ_viewer`의 UX를 참고한 브라우저용 ViewCube 구현 |
| Process visibility | process별 toolpath 표시/숨김 |
| Type filter | FEED, RAPID, PLUNGE 등 segment type별 toggle |
| Segment hover | segment hover 시 process index, feedrate, 좌표 표시 |
| Tool number filter | tool number별 색상 또는 필터 |
| WebWorker | 대용량 segment geometry 생성 작업을 worker로 분리 |
| Cached preview | 동일 VM 프로젝트의 preview 계산 결과 cache |

---

## 11. 결정이 필요한 사항

구현 전에 확인하면 좋은 결정이다.

| 항목 | 추천안 |
| --- | --- |
| 3D library | `three` 직접 사용 |
| ViewCube 1차 범위 | 실제 ViewCube 대신 `Top`, `Front`, `Side`, `Fit` 버튼 |
| 원호 표시 | 1차는 chord, 2차에서 interpolation |
| segment 제한 | 기본 `max_segments=20000`, 초과 시 균등 sampling |
| stock draft 반영 | 저장 전 local state를 viewer에 즉시 반영 |
| API cache | 1차는 TanStack Query cache, 서버 cache는 2차 |

---

## 12. 요약

1차 구현은 `src/utils/nc_parser.py`의 `NCParser`를 백엔드 preview API에 연결하고, React에서는 Three.js viewer로 stock box와 toolpath를 표시하는 방향으로 진행한다.

가장 중요한 설계 결정은 toolpath와 stock의 데이터 출처를 분리하는 것이다.

```text
toolpath = 서버 API에서 계산한 NC segment
stock box = 현재 프론트 form draft 값을 우선 사용
```

이렇게 하면 사용자는 stock 좌표를 저장하기 전에 3D viewer에서 위치 변화를 바로 확인할 수 있고, 저장 후에는 query invalidate를 통해 서버 상태와 다시 동기화할 수 있다.

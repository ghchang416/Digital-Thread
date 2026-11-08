# DT 프로젝트 생성기 개발 인계서

기준일: **2026-11-08 (Asia/Seoul)**

대상: 새 맥북에서 이 문서와 저장소 소스를 읽고 개발을 이어갈 개발자/Codex

범위: 기존 DT 생성기, 수동 누락값 보완 개선, ELS G0~G2b 및 G3a-1 저장 계층

문서 내 경로는 별도 표시가 없으면 **저장소 루트 기준**이다.

## 1. 먼저 알아야 하는 현재 상태

**기존 CAM/NC 수동 생성기는 사용 가능하다. ELS는 서버 후보 생성·XML 검토와 로컬 적용/복원 저장 함수까지 구현됐지만, 사용자 화면·자동저장·활성 편집 계약 연결은 아직 안 됐다.**

- 다음 개발은 ELS **활성 편집 계약/보호 규칙 → 자동저장 큐와 적용·복원 연결 → 가져오기 UI → 검토/다운로드 연결 → 브라우저 검증 → reader 배포** 순서다.
- MongoDB/GridFS 저장, 데이터 플랫폼 업로드는 사용자의 명시적 결정으로 **계속 제외**한다. 브라우저 로컬 복구용 IndexedDB는 이 제외 범위에 해당하지 않는다.
- 기존 `iso_api`는 다른 시스템도 사용한다. 기존 CAM/NC API의 동작·저장 경로·응답 계약을 깨뜨리면 안 된다.
- 별도의 상시 API 서버를 복제할 필요는 없다. 지금까지 추가 Docker 이미지는 **일회성 테스트 이미지**다.
- ELS `enabled:false`는 의도된 보호 상태다. Java 설치나 환경변수 변경만으로 `true`로 바꾸지 않는다.
- 실제 작성 중인 브라우저 데이터를 테스트/마이그레이션 실험 대상으로 사용하지 않는다.
- XML 검증은 모델 metadata 및 xsdata 직렬화/재파싱과 참조/워크플로 검사다. ISO/XSD 인증, 5축 운동학 복원, NC 실행/가공 안전 검증이 아니다.

### Git 기준

원격: `https://github.com/ghchang416/Digital-Thread.git`

현재 브랜치: `vm_middle` (main이 아님)

| 커밋 | 내용 |
| --- | --- |
| `2e144af` | CAM·NC 수동 입력을 지원하는 기본 생성기 |
| `eed2e5d` | 구 Excel 기반 변환 도구 및 통합 테스트 |
| `004e56e` | 로컬 산출물·계획서·중첩 작업 폴더 ignore |
| `945d671` | 수동 누락값 보완·13399 동기화·NC 확인 안내 개선 |
| `e47fc17` | ELS Access/후보/XML 및 안전한 로컬 적용·복원 기반 |

이 문서는 별도 `docs(creator)` 커밋으로 추가한다. 이 인계 작업에서는 **push하지 않는다**. 새 맥북에서 pull하려면 먼저 사용자가 승인한 push가 필요하다. 새 브랜치를 만들 때는 저장소 규칙이 따로 없다면 `codex/` 접두어를 사용한다.

### 새 세션 첫 점검

```sh
git status --short
git branch -vv
git log -5 --oneline
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
```

그다음 12장의 테스트를 실행하고 14장의 다음 작업부터 시작한다. 로컬 수정이 있으면 덮어쓰거나 `reset --hard`하지 않는다.

## 2. 사용자 목적과 합의

사용자는 공장 CAM 작업자가 보유한 장비/재료 정보, CAM JSON, NC 파일로 프로젝트 관련 XML을 쉽게 만드는 생성기를 원한다.

1. 생성기는 일회성 작성 도구로 사용한다. 프로젝트 명, 장비·재료 입력, 파일 등록, 가공 단계 확인만으로 작성 흐름이 이어져야 한다.
2. 작업자용 간편 화면과 상세 스키마 편집 화면은 **같은 초안**을 공유한다. 전환해도 수정 중인 항목/값/선택 위치를 유지한다.
3. 메인 워크플랜 아래 여러 워크플랜과 하위 워크플랜을 만들 수 있다. 워킹스텝은 워크플랜에 속한다. 실제 구현의 깊이/개수 한도는 준수한다.
4. 장비·재료는 XML이 있어야만 등록 가능한 구조가 아니다. 사람이 알고 있는 값을 직접 넣을 수 있어야 한다. 임의 PDF/Excel 자동 추출은 현재 범위가 아니다.
5. 선택 필드는 모달에서 고르고 본문에서 값을 추가/수정/삭제한다. 반복 필드와 enum 선택, 필수 하위 구조를 스키마에 맞게 보여준다.
6. 설정에서 글로벌 자산 ID 기본 URI를 관리한다. 기본값은 `https://digital-thread.re/kitech/`이며 기존 자산 ID를 설정 변경만으로 일괄 변경하지 않는다.
7. 원본에 없는 필수값은 사용자의 명시적 동의로 작성용 임시값을 넣을 수 있다. 출처·보완 이력·확인 필요 경고를 보여준다.
8. NC/CAM 기반 기존 흐름에서 공구 T 번호는 **NC 기준**이다. 동일 WP 내 같은 T를 같은 공구로 처리하되 제원 충돌은 사용자 확인 없이 덮지 않는다.
9. ELS의 원본 구성 충돌에는 더 엄격한 규칙을 적용한다. 같은 T라도 원본 공구 구성이 다르면 자동 통합하지 않는다.
10. 최종 목표는 프로젝트/장비/재료/공구/파일 관련 XML 생성·검증·개별 또는 ZIP 다운로드다. DB/플랫폼 연동은 후속 과제다.

## 3. ISO 14649와 DT 확장 구조

### 실제 스키마 기준

- 기준 모델은 `ISO_api/src/entities/model_v31.py`다. 다른 model 버전으로 잘못 바꾸지 않는다.
- 기본 ISO 객체: Project/Workplan/Workingstep, Workpiece/Feature, Operation, Technology, MachineFunctions, Tool 등.
- DT 확장: `DtAsset`, `DtProject`, `DtMachineTool`, `DtMaterial`, `DtCuttingTool13399`, `DtFile` 및 자산 간 참조.
- 프론트는 Python을 실행하지 않고 `/api/v3/creator/schema`의 카탈로그를 이용한다.
- `catalog.py`, `schema_provider.py`, `profiles/v31.json`이 모델 metadata/참조 정책을 제공한다. `v31_tools.json`은 지원 공구·제원·단위 대응을 관리한다.
- 새 모델/XSD 파일을 임의 업로드하면 즉시 교체되는 범용 런타임은 아니다. 새 스키마는 provider 등록·프로필·해시·카탈로그·검증/복구 호환성을 함께 검토해야 한다.

### 개념 구조

```text
DtAsset(project) → DtProject
  ├─ main_workplan → Workplan
  │    └─ its_elements → Workplan ... / MachiningWorkingstep ...
  │         └─ MachiningWorkingstep
  │              ├─ its_secplane
  │              ├─ its_feature → its_workpiece → Workpiece
  │              └─ its_operation
  │                   ├─ its_tool (내부 ISO 공구 객체, 필수 구조 유지)
  │                   ├─ its_technology / its_machine_functions / 전략 등
  │                   └─ ref_dt_cutting_tool → 독립 DtCuttingTool13399 자산
  └─ its_workpieces → Workpiece

Workpiece.ref_dt_material → 독립 DtMaterial 자산
Workplan.ref_dt_machine_tool → 독립 DtMachineTool 자산
DtFile 자산 ↔ 프로젝트/대상 워크플랜의 파일 연결 metadata
```

`ref_dt_cutting_tool`은 **operation의 참조**이며 `its_tool` 아래에 임의로 만들면 안 된다. 독립 13399 자산 참조가 있다고 내부 `its_tool`을 없애면 필수 구조가 깨진다. 두 공구 표현의 공통 제원을 동기화한다.

### 편집용 Draft와 XML의 차이

`CreatorDraft`는 `nodes[nodeId] = {nodeId,typeId,fields}`, `{$node: ...}` 객체 연결, `assets`, `projectAssetNodeId`, revision/해시와 링크 목록으로 구성된 편집 그래프다. XML 자체를 화면 상태로 저장하지 않는다.

- `referenceLinks`: 장비·재료 등 정책 기반 일반 자산 참조.
- `fileLinks`: 실제 브라우저 파일 Blob/fileId/해시와 DT 파일의 연결.
- `toolLinks`: 기존 NC/CAM 공구 연결.
- `manualTools`: 수동/ELS에서도 재사용하는 공구 정의 registry. 이름이 manual이라고 자동으로 수동 WP 소유가 되는 것은 아니다.
- `manualToolLinks`, `manualWorkplans`, `ncReviews`: NC 수동 작성 및 확인 정보.
- `completionEntries`: 생성/기본/임시/공통 입력값의 이력.

관리 참조는 resolver가 검증 후 XML 그래프에 주입한다. 프론트에서 임의 ref XML 객체를 만들어 검토를 우회하지 않는다. 이름과 ID를 구분하고 표시 이름 변경으로 node ID를 다시 만들지 않는다.

## 4. 기존 생성기에서 가능한 흐름

### CAM 경로

1. 프로젝트와 대상 워크플랜을 만든다. 장비·재료 자산을 입력하고 참조한다.
2. DT 파일 화면에서 NC를 등록하고 **대상 워크플랜을 선택해 배정**한다. 파일 추가만으로 배정 완료가 아니다.
3. 해당 WP의 CAM 가져오기에서 NX 또는 PowerMill을 선택한다.
4. NX는 한 JSON에 여러 워킹스텝, PowerMill은 보통 JSON 하나에 워킹스텝 하나다. 여러 PowerMill JSON을 선택하고 작업자가 순서를 맞춘다.
5. 파싱 후보를 검토·수정하고 선택 결과를 명시적으로 적용한다. 중복/지연 응답으로 기존 수정값을 덮지 않는다.
6. NC 구간·T 번호·13399 공구 연결을 검토한다. 구간 후보 분석은 최종 확인이 아니다.
7. 누락값 보완, 상세 편집, NC 재확인 후 전체 XML 검토/다운로드로 진행한다.

### NC만 있는 경로

1. 프로젝트/WP, 장비·재료와 NC 파일을 등록·배정한다.
2. `공구 · 13399`에서 사양을 직접 입력해 독립 공구 자산을 만든다. CAM JSON은 필요하지 않다.
3. WP의 `직접 작성`에서 이름, 지원 가공 타입, 사용 공구를 선택해 워킹스텝을 추가한다.
4. NC 구간 후보를 참고해 각 WS의 T 번호와 시작/끝 행을 확인한다.
5. 확인 근거·사유를 선택/입력하고 별도 최종 확인 체크 후 `NC 수동 확인 적용`을 누른다.
6. XML 생성·검증·다운로드를 진행한다. 그래프/공구/NC 관련 내용이 바뀌면 재확인이 필요하다.

### 수동 누락값 보완: 최근 개선

- 신규 WS는 `새 워킹스텝과 사용 공구의 누락 필수값을 임시 보완...` 체크를 명시적으로 켜면 준비+보완 성공 후 한 번에 적용한다.
- 기존 WS는 **직접 WS가 있는 대상 WP → 누락값 보완 → 형상·좌표·치수 임시값 포함 → 별도 검토 동의 → 누락값 일괄 보완** 순서다.
- 하위 WP까지 재귀 처리하지 않는다. 각 WP에 적용한다. 옵션을 끄면 기본 enum/boolean 등만 채워지고 평면/형상/치수 누락은 남을 수 있다.
- `POST /workplans/manual-complete`는 revision/profile/수동 공구 링크를 검증하며, 양쪽 공구의 빠진 제원도 맞춘다. 기존 0/false 및 실제 입력값을 보존한다.
- 서로 다른 기존 제원은 임시값으로 덮지 않는다. unsupported 필수 항목은 오류로 남긴다. 다른 WP와 공구를 공유해 안전한 범위를 판단할 수 없으면 거부한다.
- 데이터가 바뀐 WP의 NC 확인은 무효화한다. 멱등 재요청으로 변화가 없으면 확인을 불필요하게 없애지 않는다.
- `NC 수동 확인 적용`은 확인 사유/배정/공구/최종 확인이 필요하다. 이유 선택 버튼은 사유를 작성할 뿐 최종 동의를 자동 처리하지 않는다.
- XML 리뷰는 임시값을 강조하며 ZIP의 검증 보고서에도 남긴다. 임시 치수·평면을 실제 가공값으로 사용하면 안 된다.

### 기계연 시연 데이터 합의

Git에서 제외된 `data/xml/기계연/`의 CAM JSON, `merge.tap`, 기계연 장비/재료 XML을 사용했다. `1차` 작업순서 txt는 개발자가 순서를 이해하기 위한 참고이며 사용자 업로드 필수 파일이 아니다. `Toolpaths.json`, `Tools.json`, `Groups.json`, `Stocks.json`은 이 시연의 입력 대상이 아니다. NC에 맞는 순서를 작업자가 확인하며 T 번호도 NC를 따른다. 실제 폴더의 한글 조합 방식/경로는 새 맥북에서 확인한다.

## 5. ELS 개발 완료 범위

| 단계 | 현재 상태 | 사용자 사용 가능 여부 |
| --- | --- | --- |
| G0 | 읽기 전용 Access reader, 합성 MDB/ACCDB, 원본 catalog | 단독 테스트 가능 |
| G1 | DTO, 매핑 프로필, 소유권/후보 적용 preflight, NC 확인 호환 | 기반 구현 |
| G2a | 소유 세션 업로드·조회·만료·취소·원본 선택 | runtime/flag 필요 |
| G2b | 별도 DT 후보 → 보완/동기화 → ELS 확인 → XML 검토 | 서버 후보 테스트 가능 |
| G3a-1 | format-2 적용·이전 초안 복원·파일 보존 저장 함수 | 함수/테스트만, 화면 미연결 |
| 다음 | 활성 편집·자동저장 큐·UI·ZIP·E2E·배포 | 미구현 |

**G3 전체 완료가 아니다.** 현재 ELS 프론트 폴더에는 `contracts.ts`, `workspace.ts`, `recovery.ts`만 있다. 업로드/선택 React 화면이나 app 연결이 없다.

G2b의 확인된 대표 템플릿은 `FreeformOperation + ToolpathFeature + MillingCuttingTool`이다. 모든 feature는 프로젝트의 실제 Workpiece 하나를 공유하고, 기본 MachineTool/Material 및 13399 수치/단위를 표현한다.

상세 컨트롤러·축/주축·MachineToolSpecification, 다른 가공/공구 조합은 `els_milling_v1.json`의 coverage에서 deferred다. 기존 수동 지원이 존재한다는 이유로 ELS 지원도 완료라고 표시하지 않는다. 5축 데이터 구조를 입력할 수 있다는 것과 5축 기계 특성/가공을 자동 복원·검증한다는 것은 다르다.

## 6. ELS 데이터 해석: 다시 추측하면 안 되는 결정

아래는 사용자 합의/ELS 담당자 설명을 반영한 설계다. **의미가 합의됐다는 것과 해당 상세 매핑이 구현됐다는 것은 구분**한다. 실제 구현 coverage는 프로필과 테스트가 기준이다.

### 식별과 순서

- 프로젝트 범위는 **Part_No + Part_Rev + Op_No**다. 파트 전체의 밀링/터닝 OP를 묶지 않는다.
- 첫 버전은 한 OP에서 프로그램/개정 조합 하나를 명시 선택한다. REVNO 최댓값을 최신이라고 자동 선택하지 않는다.
- `010`과 `10`은 다른 문자열 키다. 정렬용 수치 변환과 원본 식별을 혼동하지 않는다.
- 상세 행 식별은 `Operation_Machining_SN`을 우선한다. OP/PGM/REV/SEQ 튜플을 PK로 단정하지 않는다.
- 동일 OP/PGM/REV/SEQ에 다른 공구가 있던 특정 사례는 담당자가 원본 오류라고 설명했다. 모든 중복행이 삭제 가능한 오류라는 뜻은 아니다.
- 원본 행 삭제/수정 없이 제외 행·순서 변경과 사유를 후보 metadata에 기록한다. 자동 최신 선택/중복 병합 금지.

### 속도/이송 및 공구 의미

| 소스 | 의미/구현 원칙 |
| --- | --- |
| SPINDLE_01/02 | 한 sequence의 가변 조건일 수 있음. 서로 다른 주축/WS로 분할하지 않음. 동일값 반복은 통합 가능, 다른 값은 대표값+사유 및 미표현 경고 |
| FEED_01~04 | 유효값 전체 검사. 밀링이 항상 FEED_01만 사용한다고 가정하지 않음. 원호 보정 이송을 복원했다고 주장하지 않음 |
| SPINDLE_MAX/MIN, FEEDRATE_MAX/MIN | 선택 운전값의 자동 대체값이 아님 |
| INSERT_01/02 | 한 cutter body에 서로 다른 인서트 종류가 장착될 수 있음. 컬럼 수를 날 수로 쓰지 않음 |
| HOLDER_01~05 | 복합 홀더 구성 정보. 체결 순서/위치/개수를 임의 생성하지 않음. 빈 값은 홀더 없음이라는 뜻이 아님 |
| Tool_Milling | 선택적 기준정보. TOOLNO로 MES PK를 직접 join하지 않음. 부분 일치 후보가 하나여도 대상이 인서트인지 조립체인지 확인 필요 |
| 실제 사용 공구 | Operation_Machining 제원 우선. Tool_Milling 매칭 없어도 생성 가능. fuzzy match 자동 확정은 현재 미구현 |
| DIAMETER_SETPOINT/VERICUT_DIAMETER | 유효 지름 후보. 명시적 선택 규칙 적용 |
| CORNER_NOSE_RADIUS/VERICUT_RADIUS | 코너/날끝 반경 후보. SETDIAMETER_OFFSET과 다름 |
| STICKOUT 등 | 돌출 길이. 전체 조립 길이로 자동 매핑하지 않음 |
| AXIAL_DEPTH_MAX | 공정 사용량일 수 있음. 공구 허용 maximum_depth_of_cut으로 자동 매핑하지 않음 |
| 전체 조립 길이/유효 날 수 | 직접 확정 정보가 없으면 사용자 입력 또는 지원 placeholder. 단품 전장을 조립 전장으로 추정하지 않음 |

ELS 주축 rpm → 1/s는 `/60`, 이송 mm/min → m/s는 `/60000`으로 한 번만 변환하고 원본/목표 단위를 보존한다. 공구 치수는 NumericalValue와 Unit을 함께 쓴다. `0`, `false`, NULL, 빈 문자열을 일괄 결측치로 바꾸지 않는다. mm/rev 등을 변환할 근거가 부족하면 임의 변환하지 않는다.

공구 동일성은 **placeholder 적용 전 원본 구성 fingerprint**로 결정한다. 서로 다른 행도 같은 실제 공구면 공유할 수 있지만, 같은 T에 다른 구성이면 충돌이다. 제원이 없으면 작업자의 configuration ID/사유가 필요하다. 같은 더미 치수로 채워졌다고 공구를 합치지 않는다.

### 장비·재료·파일

- Part_Info → Operation_Info: Part_No + Part_Rev. 가공 상세는 여기에 Op_No를 더한다.
- 장비는 설비코드+설비번호로 정확히 매칭하며 모호하면 중단한다. 5축이라는 이유로 A/B/C나 동시 제어축을 임의 생성하지 않는다.
- 재료는 `Spec_재질`, `Part_Material`에서 식별 가능한 값을 사용한다. 국제 규격 코드를 별도 필수 확인으로 강제하지 않는다.
- 설비코드+번호의 DeviceId 설계, 컨트롤러, 축 스트로크 및 절삭유 기본 가정은 후속 상세 매핑 대상이다. 원본 가공값이 있으면 그것이 우선이다.
- Machine_AvailableOP/Part_Spec 누락을 기본 생성 실패 조건으로 추가하지 않는다.
- File_Path는 원본 bytes가 아니다. 서버가 네트워크 경로를 자동 읽지 않는다.
- ELS metadata-only 파일은 `elsFileLinks`로 보존한다. 가짜 fileId/Blob/hash/OID를 만들지 않는다. 검증된 이 파일에만 검토 XML의 `DtFile.value` 생략을 허용하고 `sourceFileAvailable:false`/pendingStorage를 보고한다.
- 실제 Blob 연결 시 같은 파일 자산 ID를 유지하는 전환은 후속 UI/command 작업이다. 원본 해시가 없으면 이름 일치만으로 내용 진위를 인증하지 않는다.

## 7. ELS 서버 계약과 코드 지도

### 파일별 책임

| 위치 | 책임 |
| --- | --- |
| `ISO_api/src/entities/model_v31.py` | 스키마 기준 모델 |
| `ISO_api/src/services/creator/schema_provider.py`, `catalog.py` | 모델/프로필 등록과 프론트 카탈로그 |
| `ISO_api/src/services/creator/profiles/v31.json`, `v31_tools.json` | 기존 참조 정책·지원 공구 |
| `ISO_api/src/services/creator/profiles/els_milling_v1.json` | ELS 매핑/단위/기본값/coverage/limits, 별도 해시 |
| `ISO_api/src/schemas/creator.py` | 엄격한 기존 CreatorDraft DTO |
| `ISO_api/src/schemas/creator_els.py`, `creator_els_sessions.py` | 후보/출처/결정 및 업로드 세션 DTO |
| `ISO_api/src/apis/v3/creator.py`, `creator_els.py` | 생성기 및 ELS router |
| `ISO_api/src/apis/v3/creator_middleware.py` | 기존 요청 상한, 정확한 ELS 업로드 경로만 스트리밍 상한 |
| `ISO_api/src/services/creator/els/reader.py`, `source_catalog.py`, `selection.py` | Access 읽기, 목록/키/선택 범위 |
| `ISO_api/src/services/creator/els/sessions.py` | 임시 소유 세션/작업/정리/자원 한도 |
| `ISO_api/src/services/creator/els/profile.py`, `tool_identity.py` | 매핑값 선택과 원본 공구 identity |
| `ISO_api/src/services/creator/els/build.py`, `contracts.py` | 후보 그래프 생성 및 적용 preflight |
| `ISO_api/src/services/creator/els/complete.py`, `review.py` | 보완/공구 동기화, 확인 해시, ELS resolver/XML |
| `ISO_api/src/services/creator/manual_completion.py` | NC 수동용 missing-only 보완 |
| `ISO_api/src/services/creator/preview.py`, `references.py`, `asset_references.py` | 공통 XML 검토 및 기존 참조 |

### 실제 ELS API

공통 prefix: `/api/v3/creator/els`.

| Method/경로 | 역할 |
| --- | --- |
| GET `/capabilities` | 기능 상태. 현재 enabled=false |
| POST `/imports` | multipart file 한 개, X-ELS-Request-Id, 202 응답 |
| GET `/imports/{id}` | 상태/만료/진단 요약 |
| GET `/imports/{id}/operations` | PART/REV/OP 검색 및 페이지 |
| GET `/imports/{id}/operations/{key}` | 프로그램/개정 선택 |
| GET `/imports/{id}/operations/{key}/programs/{programKey}/rows` | 원본 가공 행 페이지 |
| GET `/imports/{id}/diagnostics` | 진단 페이지 |
| GET `/imports/{id}/operations/{key}/programs/{programKey}/source` | 후보 생성용 제한된 원본 범위 |
| DELETE `/imports/{id}` | 취소/임시 상태 정리. 초안 삭제 아님 |
| POST `/imports/{id}/prepare` | ElsBuildRequest → 별도 후보와 검토 결과 |
| POST `/complete` | ElsCompleteRequest, placeholder/synchronizeTools 명시 선택 |
| POST `/confirm` | ElsConfirmRequest, 필수/참조/동기화/XML 검증 후 WP 확인 |
| POST `/review` | ElsReviewRequest, 대상 자산 1~10개의 검토용 XML |

업로드 응답의 ownerToken은 이후 세션 API의 **X-ELS-Owner-Token 헤더**에 넣는다. URL, 로그, 초안, IndexedDB에 저장하지 않는다. 다른 소유자/미존재/만료/취소는 구분되지 않는 404로 처리한다. requestId는 추적용이며 서버 재시도 중복 제거 키가 아니다. 성공 응답은 no-store다.

상태는 uploading/queued/reading/ready/failed다. ready는 원본 조회 가능 상태일 뿐 DT 변환/확인 완료가 아니다. 원본 세션이 사라져도 이미 만들어진 후보의 complete/confirm/review는 stateless하게 처리한다. 제출된 원본 snapshot의 진위까지 인증하는 것은 아니다.

### 후보 계약

```text
ElsCandidate
  request: requestId/importId/baseDraftId/baseRevision/expectedSequence
           mode(replace-project | append-tools)/profileHash/selection/includePlaceholders
  draft: 기존 CreatorDraft
  metadata: elsImports / elsOrigins / elsWorkplans / elsToolLinks / elsReviews / elsFileLinks
  requiredCapabilities: ["els-import-v1"]
  recoveryFormatVersion: 2
  purpose: "authoring-review-only"
  machineReady: false, finalizable: false, persisted: false
```

- replace-project: 다른 draftId, 후보 revision=0. append-tools: 같은 draftId, baseRevision+1.
- prepare에는 OP/program 키, 프로젝트명, URI 기본값, 명시적 mapping/template/행/공구/파일 결정이 포함된다.
- 준비 응답에는 다운로드 XML을 직접 노출하지 않고 review에서 반환한다.
- 기존 `CreatorDraft`는 여전히 ELS 확장 필드를 받지 않는다. `candidate.draft`만 기존 `applyPrepared()`에 전달하면 출처를 버리므로 금지한다.
- 후보의 생성 시 revision 제약을 활성 편집 revision 규칙과 혼동하지 않는다. **활성 ELS 편집 DTO는 다음 단계에서 설계·구현**해야 한다.

## 8. 확인 해시와 기존 NC 호환

ELS 확인은 선택한 WP의 원본 선택, 도달 가능한 그래프, 사용 공구 정의, 참조 장비/재료, metadata 파일 및 규칙 해시에 대한 일관성 확인이다. 암호학적 전자서명/원본 인증이나 NC 확인이 아니다.

- 미사용 공구를 추가했다는 이유만으로 무관한 WP 확인을 무효화하지 않는다.
- 사용 공구/순서/원본 결정/관련 값 수정 시 해당 확인은 다시 받아야 한다.
- 모든 확인 검사는 **파생 XML 참조를 삽입하기 전** 원본 그래프에 수행한다.
- 동일 step/WP에 ELS와 기존 CAM/NC 관리자가 중복 소유하면 거부한다.
- 기존 NC WP는 계속 NC 확인이 필요하다. ELS라는 이유로 전체 NC 검증을 끄는 옵션을 만들지 않는다.
- 프론트 `ncSignature()`의 수동 공구 정의 범위를 해당 WP 사용 공구로 제한했다. 구 서명은 구 알고리즘으로 현재 데이터와 일치할 때만 새 알고리즘으로 이행한다. 이미 stale하거나 미확인인 세션을 완료로 바꾸지 않는다.
- 기존 CAM 서명과 서버 manual snapshot 알고리즘은 변경하지 않았다. 기존 schemaHash/referencePolicyHash/v31_tools 해시를 ELS 추가만을 위해 바꾸지 않는다.

현재 `features/export/model.ts`는 직접 WS가 있는 **모든 WP에 NC 확인을 요구**한다. 따라서 ELS 그래프만 화면에 넣으면 ZIP이 막힌다. ELS 소유권에 따른 검토 분기를 서버/프론트 양쪽에서 구현해야 한다.

## 9. ELS 로컬 저장·복원: 구현됐지만 미연결

주요 파일: `ISO_api/frontend/src/features/els/{contracts,workspace,recovery}.ts`.

| 함수/계약 | 동작 |
| --- | --- |
| `ElsWorkspaceData` | 기존 WorkspaceData + 별도 elsMetadata |
| `snapshotOf`, `validateWorkspaceSnapshot` | v1/v2 분리와 capability/profile/구조 검사 |
| `workspaceFromCandidate` | 요청/기준 draft/sequence 검증 및 교체·공구 추가 구성 |
| `applyElsRecovery` | 후보 적용, 교체 전 미저장 입력 포함 previous 보관 |
| `readElsRecovery` | 명시적 opt-in 읽기, 두 슬롯과 원본 해시 검증 |
| `restorePreviousRecovery` | active/previous 한 칸 교환, sequence 증가 |

세 버전은 다르다: API draftVersion=1, 기존 record formatVersion=1/ELS record formatVersion=2, IndexedDB database version=1. ELS record에는 requiredCapabilities=[els-import-v1]이 필요하다.

저장소 이름은 `dt-project-creator`, object stores는 `workspace`, `files`다. ELS 적용/복원은 다음을 하나의 readwrite transaction으로 처리한다.

1. expectedSequence 비교(CAS), 오래된 requestId/base revision/작업 epoch/취소 확인.
2. active와 previous metadata 기록. previous는 저장된 옛 초안이 아니라 **현재 메모리의 rawInputs/extraFields/CAM/NC/파일까지** 담는다.
3. 두 슬롯이 참조하는 Blob 합집합 보관. 동일 fileId에 다른 해시/내용이 있으면 거부한다.
4. 어느 슬롯에서도 쓰지 않는 파일만 정리. quota/트랜잭션 실패 시 이전 metadata/Blob 모두 보존한다.

append-tools는 기존 project/WS/배정/파일/NC 확인/출처를 변경하지 않는다. 서버가 생략된 기본값을 명시 직렬화해도 의미를 비교하고 기존 프론트 표현을 보존해 서명 변화를 막는다. 명시적 새 프로젝트 reset은 previous와 원본도 함께 정리하지만 URI 사용자 설정은 유지한다.

**아직 없는 것:** useRecovery 큐 checkpoint/flush/epoch 연결, 편집 잠금, 적용/복원 확인 UI, v2 편집 후 자동저장, ELS-aware 편집기. `isCurrent`와 AbortSignal을 전달하는 coordinator가 필요하다. 저장 함수를 app에 바로 호출해 기능 완료로 처리하지 않는다.

현재 app은 기존 v1 reader/writer를 사용한다. ELS metadata/v2는 거부하여 출처가 조용히 지워지지 않게 한다. 이는 현재 ELS 데이터가 실제 사용자 브라우저에 자동 저장되고 있다는 뜻이 아니다. 저장 테스트는 fake-indexeddb만 사용했다.

## 10. Reader/업로드 자원과 보안 경계

- Java 17 + Jackcess 4.0.8. 형식 allowlist는 합성 검증한 V2000 MDB와 V2010 ACCDB다. 확장자만으로 모든 Access를 지원한다고 표시하지 않는다.
- 허용 8테이블: Part_Info, Operation_Info, Operation_Machining, Machine_Milling, Tool_Milling, Part_File, Machine_File, Tool_File.
- 원본 Access 읽기 전용. SQL/저장 쿼리/VBA/매크로/외부 linked table 실행·접속 금지.
- Reader 한도: 입력 128 MiB, 출력 16 MiB, 한 프로토콜 행 256 KiB, 합계 100,000행, 복사 포함 60초, Java heap 128 MiB/metaspace 64 MiB.
- 세션: 실행 reader 1개, 세션 최대 4개, 고정 TTL 15분, 정리 5초 간격, 업로드 timeout 120초.
- 임시 디스크 예약은 파일 상한의 3배, 총 예산 768 MiB. 읽기 완료 후 원본 bytes 제거, 조회 index만 메모리에 둔다.
- `/els/imports` POST만 ASGI 스트리밍으로 128 MiB+64 KiB multipart 여유를 적용한다. 기존 CAM/NC 32 MiB/일반 2 MiB 분기는 유지한다.
- 후보 draft+metadata UTF-8 1.75 MiB, 전체 요청 2 MiB, node 10,000, asset 1,000, 보완 이력 20,000, 직접 WS 300, 깊이 64/확장 방문 10,000.
- `/tmp/dt-creator-els-imports` 기본 임시 루트는 소유권/배타 lease를 확인한다. 살아 있는 다른 서버의 파일이나 임의 디렉터리를 정리하지 않는다.
- 단일 API 프로세스 세션 소유를 지원한다. 다중 worker 분산 세션은 미구현이며 동일 루트 경쟁 시 ELS만 거부한다.
- `CREATOR_ELS_ENABLED=1`, `ELS_READER_JAR`, PATH의 java가 inspection 실행 조건이다. `ELS_IMPORT_TEMP_ROOT`로 테스트 임시 경로를 지정할 수 있다. 전체 enabled는 아직 false다.

## 11. 새 맥북에서 환경 재구성

### 파일 복사/Git과 브라우저 초안은 별개

- 프로젝트 폴더나 Git clone에는 브라우저 IndexedDB, Docker image/volume, 실행 중 container가 포함되지 않는다.
- 기존 브라우저의 임시저장 초안과 Blob은 **컴퓨터·브라우저 프로필·origin**에 묶인다. localhost:3011과 localhost:8080도 다르다.
- 현재 `초안 JSON` 내보내기는 객체 그래프 중심이며 원본 Blob/CAM 세션을 포함한 완전한 작업공간 백업이 아니다. ELS 이전 초안 복원 함수도 다른 기기로 이주시키는 기능이 아니다.
- 기존 초안까지 옮겨야 한다면 원본 파일을 따로 보관하고, 완전한 작업공간 export/import를 별도 작업으로 설계하거나 새 기기에서 재작성해야 한다. 브라우저 내부 DB 폴더를 임의 조작하지 않는다.

### Git 외에 필요한 자료

| 자료 | 취급 |
| --- | --- |
| 루트 및 ISO_api의 `.env` | 안전한 별도 경로로 전달. 자격증명은 Git/이 문서에 넣지 않음 |
| `data/xml/기계연/`, `data/json/boss/result/` | 실제 데이터/구조 참고, Git 제외. 시연/외부 데이터 테스트 시 별도 복사 |
| ISO PDF/요약 | 기존 머신의 Desktop/kitech/함범환/ISO Guide 아래. 새 경로 확인, 라이선스 문서는 공개 커밋하지 않음 |
| `docs/hanhwa_db자료/`, 로컬 매핑 XLSX | 실제 ELS 분석 참고. Git 제외, 필요 시 별도 전달 |
| `/plans/`, `/outputs/`, `/.codex-artifacts/` | 과거 계획·목업·PPT 산출물. 실행 의존성이 아니며 Git 제외 |
| ELS 합성 MDB/ACCDB | `ISO_api/test/creator/fixtures/els/`는 Git 포함. 실제 고객 DB가 아님 |
| JAR, node_modules, dist | Git 제외, 새 환경에서 재생성 |

이 문서에 과거 로컬 계획의 핵심 결정을 통합했으므로 `/plans/`가 없어도 개발 재개는 가능하다. 원본 계획은 `plans/dt-project-creator/els-import/implementation-plan.md` 18~23장이 가장 최근 상태였으며, 초기 장의 제안 API/구현 완료 표현보다 이 문서와 현재 코드를 우선한다.

### 기존 Compose로 실행하는 경우

저장소 루트에서 실행한다. Docker Desktop과 기존 backend 환경설정/데이터가 준비됐다는 전제다. external network `kitech_network`가 없으면 먼저 만든다.

```sh
docker network inspect kitech_network
# 위 명령에서 없다고 확인한 새 환경에서만:
docker network create kitech_network
docker compose up -d mongo iso-api
docker compose --profile creator build iso-creator-front
docker compose --profile creator up -d --no-deps iso-creator-front
```

생성기: `http://localhost:3011`, backend: `http://localhost:8000`.

`src.main:app`은 legacy 서비스를 포함하므로 Mongo 등의 기존 실행 의존성이 있다. 생성기에서 DB 저장을 구현한다는 뜻은 아니다. 이 문서의 명령을 기존 서버에 무심코 전체 적용하지 않는다. 프론트만 바꿀 때는 마지막 두 명령만 사용하며 `down -v`는 금지한다.

루트 `.env`에서 참조하는 변수 이름: MONGO_USERNAME/MONGO_PASSWORD/DATABASE_NAME/DLL_URI 등. `ISO_api/src/config.py`는 VM_API_URL/VM_USERNAME/VM_PASSWORD/DP_BASE_URL/DP_API_KEY도 읽는다. 값은 기존 환경을 안전하게 전달받는다. 새 인계 작업에서 값을 출력하거나 Git에 넣지 않았다.

### 생성기만 로컬 개발하는 경우

프론트는 Node 22 계열(프론트 Dockerfile은 22.22.1), React 19.2.5, TypeScript 5.9.3, Vite 6.4.2다. package-lock.json을 따르고 불필요하게 의존성을 업그레이드하지 않는다.

```sh
cd ISO_api/frontend
npm ci
ISO_API_PROXY_TARGET=http://127.0.0.1:8000 npm run dev
```

기본 개발 주소는 `http://localhost:8080`이다. 포트가 사용 중이면 `npm run dev -- --port 3012`처럼 다른 포트를 지정한다. `ISO_API_PROXY_TARGET`은 서버 전용 proxy 설정이며 DB/플랫폼 키를 VITE_*에 넣지 않는다.

backend 의존성이 준비된 Python 3.10 환경에서는 ISO_api 디렉터리에서 아래 앱을 사용하면 legacy lifespan/DB 초기화 없이 생성기를 개발할 수 있다.

```sh
python -m uvicorn src.creator_app:app --host 127.0.0.1 --port 8000
```

현재 backend Dockerfile은 conda myenv(Python 3.10), pythonocc 및 renderenv도 설치하므로 새 머신 build가 무겁다. `requirements.txt`는 완전 잠금 파일이 아니며 pydantic-settings도 명시 누락되어 있다. 새 환경 설치 시 이를 확인해야 한다. 이번 인계는 의존성 정리 작업까지 수행하지 않았다. 위 로컬 부팅 명령의 완전한 빈 머신 재현은 별도 검증 대상이다.

2026-11-08 실행 중 backend에서 확인한 주요 버전: FastAPI 0.141.1, Starlette 1.6.0, Pydantic 2.13.5, pydantic-settings 2.15.0, xsdata 26.2, python-multipart 0.0.32, pytest 9.1.1, httpx 0.28.1, fastapi-mcp 0.4.0. 이는 관측값이며 저장소에 전체 lock을 새로 만들었다는 뜻이 아니다.

## 12. 테스트 명령과 최신 결과

### 2026-11-08 실제 재실행

| 검증 | 결과 |
| --- | --- |
| 생성기 backend `test/creator` | **270 passed / 13 skipped** |
| frontend, backend 생성 fixture 지정 | **89 passed / 0 skipped** |
| TypeScript/Vite build | 통과 |
| 합성 Access 4개 SHA-256 | checksums.json과 모두 일치 |
| ELS capability 응답 | enabled=false, requested=false, readerPresent=false, inspectionEnabled=false |

backend의 13개 skip은 Java/JAR runtime이 필요한 테스트다. 현재 실행 중 shared server에는 reader가 없다. 이번 인계에서 Java reader/브라우저 E2E는 재실행하지 않았다. 과거 2026-10-30 Java+backend 일회성 이미지 검증은 276 passed/2 외부 기계연 mount skip이었다. 이 과거 수치를 최신 실행 결과로 말하지 않는다.

기존 57개 API path/component의 HEAD 호환성 비교를 이전 단계에서 수행했지만, 그 일회성 audit script는 Git 추적 대상이 아니다. 재검증 시 기존/신규 router의 OpenAPI를 DB/lifespan 없이 비교하고 필요하면 버전 관리되는 테스트로 만든다. 기존 외부 시스템의 저장/업로드 E2E를 수행한 것은 아니다.

### 일반 회귀 테스트

```sh
# 저장소 루트, 기존 iso_api 실행 환경 사용
docker exec -e PYTHONDONTWRITEBYTECODE=1 iso_api /opt/conda/envs/myenv/bin/python -m pytest -q -p no:cacheprovider test/creator

# ISO_api/frontend에서
npm test
npm run build
```

기본 npm test는 생성 fixture 경로가 없으면 교차 계약 테스트 1개만 skip한다. 전체 89개를 실행하려면:

```sh
# 저장소 루트. 기존 Compose의 /app source mount와 frontend/node_modules 존재 전제
docker exec -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/app:/app/test/creator iso_api /opt/conda/envs/myenv/bin/python test/creator/export_els_recovery_fixture.py /app/frontend/node_modules/els-recovery-fixture.json

# ISO_api/frontend에서
ELS_RECOVERY_FIXTURE=node_modules/els-recovery-fixture.json npm test
```

Docker가 아닌 backend 환경이면 ISO_api에서 `PYTHONPATH=.:test/creator python test/creator/export_els_recovery_fixture.py frontend/node_modules/els-recovery-fixture.json`을 실행한다. 이 파일은 실제 서버 prepare/confirm이 만든 합성 후보이며 실사용 초안이 아니다.

기계연 회귀는 기본 `/data/xml/기계연`을 찾는다. 다른 위치라면 `KIMM_DATA_DIR`를 지정한다. 자료가 없어 skip이면 실데이터 수용 검증을 통과했다고 보고하지 않는다. `test/test_main.py` 등 전체 legacy 저장 테스트를 임의로 운영 DB에 실행하지 않는다.

### Access runtime 일회성 테스트

ISO_api에서:

```sh
docker build -f deploy/creator/Dockerfile.els-reader-test -t dt-els-reader-test:local .
docker run --rm --network none --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m --memory 512m --cpus 1 --pids-limit 128 dt-els-reader-test:local
```

이 이미지는 Java/Maven/Python을 자체 구성하고 합성 Access를 생성한다. 빌드에는 패키지 다운로드가 필요하다. 검증된 샘플 형식만 지원으로 표시한다.

Java+backend 전체 통합 이미지는 `deploy/creator/Dockerfile.els-vertical-test`이며 로컬 `dt-els-reader-test:local`과 `digital-thread-iso-api:latest` 이미지를 전제로 한다. 새 맥북의 Compose 프로젝트 이름이 다르면 backend image tag를 확인하고 해당 FROM/tag를 의식적으로 맞춘다. 타 아키텍처의 옛 JRE/image cache를 그대로 복사하지 말고 새 환경에서 빌드한다.

```sh
docker build --network none -f deploy/creator/Dockerfile.els-vertical-test -t dt-els-vertical-test:local .
docker run --rm --network none --read-only --tmpfs /tmp:size=512m --cpus 1 --memory 768m -v "$PWD:/app:ro" dt-els-vertical-test:local /opt/conda/envs/myenv/bin/python -m pytest -q -p no:cacheprovider test/creator
```

이 컨테이너는 API 서버가 아니며 Mongo/플랫폼에 연결하지 않는다. 이미지 안의 테스트 의존성 준비는 별도 확인한다. Maven jar/target은 Git 제외이며 직접 reader를 빌드하려면 `deploy/creator/access-reader/README.md`를 따른다.

브라우저 acceptance 파일은 `ISO_api/frontend/test/operator-demo.mjs`, `manual-demo.mjs`다. repo README의 PLAYWRIGHT_RUNTIME/CREATOR_TEST_URL 등 실행 조건을 확인한다. 항상 격리된 브라우저 context로 실행하고 사용자 저장 데이터를 reset하지 않는다. 새 ELS UI E2E는 아직 없다.

## 13. 회귀 위험과 금지 사항

1. **출처 유실:** candidate.draft만 applyPrepared/saveRecovery에 전달하지 않는다. metadata를 같은 작업 단위로 보존한다.
2. **소유권 혼합:** ELS WP에 기존 manual-step/CAM append를 바로 호출하면 manualWorkplans에 편입되거나 링크가 중복될 수 있다. 별도 WP 사용 또는 명시적 정책 전환 command가 필요하다.
3. **공구 불일치:** standalone 13399 편집 후 내부 its_tool을 암묵적으로 덮지 않는다. 모든 사용처 조회와 충돌/덮어쓰기 동의를 구현한다.
4. **삭제 후 잔재:** 사용 중 공구 삭제 차단, WS/WP/operation 변경 시 ELS 링크·출처 정리와 확인 무효화가 필요하다.
5. **검증 우회:** ELS resolver는 검증된 슬롯에만 참조를 주입해야 한다. 기존 NC 요구조건을 전체적으로 생략하지 않는다.
6. **파일 위조:** metadata-only 파일에 가짜 Blob/OID를 만들지 않는다. 실제 파일의 임의 필수값 생략으로 예외를 확대하지 않는다.
7. **동시성:** revision만으로 다중 탭을 보호할 수 없다. draftId/requestId/epoch/IDB sequence/취소를 함께 검사하고 자동저장 큐를 직렬화한다.
8. **복구 손상:** 새 형식을 오래된 앱이 읽고 다시 v1로 쓰지 못하게 한다. 준비 실패/quota/취소 시 기존 active/previous/files 유지.
9. **과장된 지원:** 모델에 타입이 존재하는 것과 importer/보완/편집/내보내기 경로가 검증된 것은 다르다.
10. **범위 확대:** 기존 백엔드 저장 API, 모델 전체 재생성, DB migration, 플랫폼 업로드, 불필요한 다른 시스템 리팩터링은 이번 범위 밖이다.

## 14. 다음 개발 순서와 완료 기준

### A. 활성 ELS 편집 계약 및 보호 규칙

- 준비 후보와 적용 후 편집 상태를 분리한다. 현재 후보 DTO의 revision=0/base+1 제약을 임의 제거해 우회하지 않는다.
- draft+ELS metadata를 함께 처리하는 요청 계약과 서버 preflight/resolver를 설계한다. 기존 API 계약을 보존하는 전용 경로/엄격한 선택 확장을 검토한다.
- 프론트 `app.tsx`의 dispatch/applyPrepared, `shared/draft/model.ts`의 삭제/prune, `manual.py`의 공구/step 변경 경로를 대조한다.
- ELS WP 직접 WS 추가/삭제/배정/정렬은 ELS 정책을 유지한다. 수동 추가분에는 fake source SN 대신 manual 출처+사유를 남긴다.
- 공유 공구 편집/상세 편집, 장비·재료 참조 변경 후 영향 WP만 stale 처리한다. 무관한 WP/공구 확인은 유지한다.
- 반복 append-tools/기존 ELS 작업공간 재가져오기와 중복 원본 선택을 명시 처리한다. 자동 3-way merge는 하지 않는다.

완료 기준: 충돌 소유권/삭제/공구 동기화/출처 보존/확인 범위 테스트, 기존 manual/CAM API 회귀 통과.

### B. 자동저장와 적용·복원 연결

- `shared/draft/recovery.ts`의 useRecovery 큐에 checkpoint/flush와 작업 epoch를 연결한다.
- 후보 요청 전 base draft/revision/sequence를 확정하고 입력/선택/탭 이동/reset/unmount 시 작업을 취소한다.
- commit 중 편집을 잠그고 성공 후에만 React 상태를 새 snapshot으로 교체한다. 실패 후에도 현재 초안의 저장/편집을 이어갈 수 있어야 한다.
- format-2 편집 후 자동저장/재시작 읽기와 previous 교환을 연결한다. 기능 OFF/구버전에서 자동 downgrade하지 않는다.

완료 기준: fake-indexeddb뿐 아니라 격리 브라우저의 새로고침·다중 탭·입력 중 취소·저장 실패·이전 복원·새 프로젝트 테스트.

### C. ELS 가져오기 및 상세 편집 화면

- 기존 작업자/상세 화면을 유지한 채 ELS 진입점을 추가한다. 한 화면에 모든 정보를 펼치지 않는다.
- 업로드 → PART/REV/OP → 프로그램/개정 → 행/순서/공구/값 충돌 해결 → 후보/placeholder 검토 → 명시적 적용.
- 프로젝트 교체와 공구만 추가를 구분하고 이전 초안 보관/복원 상태를 보여준다.
- 실제 값/파생값/기본값/임시값/수동값을 구분한다. 세션 만료는 재조회에만 영향, 이미 적용한 초안 편집을 막지 않게 한다.
- 적용·복원 dialog, enum/단위/필수 하위 입력, 키보드/작은 화면과 글자 겹침을 확인한다.

### D. 검토·다운로드·배포

- 전체 XML 검토가 WP별 ELS/NC 정책을 구분하고, ELS review XML/출처/선택 사유/미표현 조건/placeholder/pendingStorage를 ZIP에 포함해야 한다.
- XML/보고서는 같은 revision snapshot에서 생성하고 편집 후에는 이전 결과를 내려받지 못하게 한다.
- 합성 MDB와 ACCDB로 파일 선택부터 ZIP 내용 확인까지 E2E를 만든다. 프로젝트 교체/공구만 추가/취소/복원 모두 검사한다.
- 회귀 통과 후 기존 iso_api에 reader/환경설정을 배포하고 capability를 활성화한다. 별도 상시 서버는 만들지 않는다.
- 실제 고객 Access가 제공되면 컬럼/PK/단위/행 수/암호화/linked table/성능 호환 검증을 별도 수행한다.

## 15. 아직 확인해야 하는 것

- 실제 고객 Access는 제공받지 못했다. 합성 fixture 통과가 고객 파일 호환 보장은 아니다.
- 실제 Tool_Milling PK, 부분 일치 기준, 복수 속도 조건 구간, 일부 공구 치수 의미와 단위는 소스/프로필/사용자 결정으로 확인해야 한다.
- 상세 장비/전략/5축 데이터 coverage는 추가 구현·roundtrip 테스트가 필요하다.
- 새 맥북의 backend 전체 환경 완전 재현, dependencies pinning, 공개 서비스 보안/다중 worker 운영은 별도 과제다.
- 현재 실행 중 프론트 이미지는 10월 30일 수동 보완 개선 배포본이다. Git의 G3a-1 소스가 Docker 프론트에 자동 반영되는 것은 아니다. 이번 커밋/인계에서는 이미지 교체·서버 재시작을 하지 않는다.
- `/plans`, 문서 산출물, 실제 데이터와 자격증명은 이번 커밋에 넣지 않는다. 필요한 자료는 별도로 이동해야 한다.

## 16. 새 Codex 세션에 전달할 요청문

> ISO_api/CREATOR_HANDOFF.md를 먼저 읽고 현재 Git 상태와 코드를 확인해줘. DT 생성기의 기존 CAM/NC 수동 작성과 사용자 초안을 유지하면서 ELS 개발을 이어가려 해. G2b 서버 후보 생성/검토와 G3a-1 저장 함수는 구현되어 있지만 활성 편집 계약, useRecovery 큐 연결, UI와 ZIP 연동은 남아 있어. 문서 14장의 A부터 진행하고 필요한 테스트를 추가해줘. candidate.draft만 기존 화면에 적용하거나 ELS flag만 켜지 말아줘. 실제 사용자 브라우저 데이터로 테스트하지 말고 DB 저장·플랫폼 업로드는 계속 제외해줘. 기존 iso_api는 외부 시스템도 사용하므로 기존 API 계약과 동작을 보존하고 변경 범위·검증 결과·남은 과제를 분명히 보고해줘.

이 문서를 읽은 다음에 과거 대화 전체나 로컬 계획서를 반드시 다시 읽어야 개발을 시작할 수 있는 구조로 만들지 않았다. 추가 의미 확인이 필요하면 코드/프로필/테스트를 먼저 보고, 확인되지 않은 사실을 사용자에게 묻는다.

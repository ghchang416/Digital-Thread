# 업체 Excel → DT XML 시험 변환기

업체의 실제 데이터를 외부로 보내지 않고, 로컬 Excel에서 현재 `src/entities/model_v31.py` 구조의 XML을 생성합니다. 서버 접속·파일 업로드·DB 저장은 하지 않습니다.

## 현재 양식: 업체 원본 컬럼명·순서 유지

**`outputs/els_dt_converter/업체DB_원본컬럼_빈양식.xlsx`를 사용하세요.** 제공된 업체 테이블 정의서의 대상 10개 테이블, 236개 컬럼을 원래 명칭·순서 그대로 옮겼습니다. 원본 정의서와 모든 헤더를 직접 대조하는 테스트를 포함합니다. 실제 DB에 접속하여 물리적 컬럼 순서를 확인한 것은 아닙니다.

- 원본 시트: **1행 컬럼명, 2행부터 데이터**. 아래로 행을 계속 추가합니다.
- 원본 테이블에 `Record_ID` 또는 DT용 컬럼을 추가하지 않았습니다.
- 비용·단가·작성자·작성일 등도 원본 순서를 유지합니다. 현재 DT 변환에 사용하지 않는 값은 보고서의 미사용 항목에 표시합니다.
- `Machine_File.번호`와 `Machine_Milling.설비번호`처럼 서로 다른 원본 명칭도 유지하며, 변환기에서 연결합니다.
- `Part_Spec`, `Machine_AvailableOP`는 참고용 원본 입력이며 현재 프로필이 자동으로 DT 속성으로 변환하지는 않습니다.

| 별도 보완 시트 | 원본 연결 키 | 내용 |
|---|---|---|
| DT_공정 | Part_No + Part_Rev + Op_No | 공정 실행 순서 |
| DT_가공 | Operation_Machining_SN | 공구 복합키, 가공 실행 순서, 단위·조건·피처·평면 |
| DT_장비 | 설비코드 + 설비번호 | 제어기 및 장비 필수 사양 |
| DT_파일 | source_table + File_SN | MIME 유형, 선택적 로컬 경로, 업로드 ID |
| DT_공구경로 | Operation_Machining_SN + 순서 | 선택적 경로점·공구축 |

`DT_` 시트는 업체 원본 테이블이 아닙니다. 값의 의미는 `DT_입력설명` 시트에 정리했습니다. 원본 `File_Type`은 확장자·업체 코드를 그대로 입력하고, MIME 유형은 `DT_파일.content_type`에 따로 넣습니다. `local_path`는 원본 경로를 로컬 파일 위치로 바꿔 읽을 때만 사용합니다. SN은 정수 또는 문자열로 입력할 수 있고 문자형 복합키는 앞자리 0을 보존합니다.

컬럼명·순서가 다르면 오류를 반환합니다. **원본 정의서와 같은 컬럼 순서로 내보낸 행**을 붙여넣으세요. 원본 시트에 전체 값을 붙여넣어도 변환기는 지원하는 DT 항목만 읽습니다. 필수 보완값이 없으면 해당 원본 키와 부족한 항목을 보고하고 XML 생성은 중단합니다.

```bash
.venv-els/bin/python ISO_api/tools/els_dt_converter/convert.py \
  outputs/els_dt_converter/업체DB_원본컬럼_빈양식.xlsx \
  --part 'PART-001' --rev '01' --out outputs/원본DB_변환_001
```

먼저 실제 값을 채운 뒤 실행하세요. 설치·파일 모드·결과 검증 방법은 아래와 같습니다. 이전 행 양식과 세로 양식도 계속 읽을 수 있습니다.

## 이전 양식: 선택 컬럼에 Record_ID를 추가한 행 입력

이전 `업체입력_빈양식_DB행입력.xlsx`의 사용법입니다. 새 원본 컬럼 양식은 위의 설명을 따르세요. 기존 파일은 보존했습니다.

```text
Part_Info (파트·개정 1행)
  └─ Operation_Info (공정 여러 행)
       └─ Operation_Machining (가공 순서 여러 행)
            └─ Tool_Milling (행마다 사용하는 공구 1개 참조)
```

공구 개수를 미리 정하지 않습니다. **공구가 바뀌거나 같은 공구를 다시 사용하면 상세 가공 행을 추가**합니다. 공구 마스터에는 같은 공구를 반복 등록하지 않습니다.

새 가상 예제는 파트 1개, 공정 2개, 상세 가공 6행, 공구 3개를 포함합니다.

| Op_No | 가공 순서 | 상세 가공 Record_ID | 사용 공구 |
|---|---:|---|---|
| 010 | 1 | WS1 | TOOL-001 |
| 010 | 2 | WS2 | TOOL-002 |
| 010 | 3 | WS3 | TOOL-003 |
| 010 | 4 | WS4 | TOOL-001 재사용 |
| 020 | 1 | WS5 | TOOL-002 재사용 |
| 020 | 2 | WS6 | TOOL-003 재사용 |

### 시트별 행의 의미

| 시트 | 한 행 | 연결 |
|---|---|---|
| Part_Info | 파트·개정 | Part_No + Part_Rev |
| Operation_Info | 공정 | 파트 키 + Op_No, 장비 복합키 |
| Operation_Machining | 가공 순서·사용 공구 | 공정 키, 공구번호 + 공구사양 |
| Tool_Milling | 공구 사양 | 공구번호 + 공구사양 |
| Machine_Milling | 장비 | 설비코드 + 설비번호 |
| Machining_Conditions | 가공별 조건·공구 조립값 | 상세 가공과 같은 Record_ID |
| Machining_Geometry | 가공별 피처·평면 | 상세 가공과 같은 Record_ID |
| Machine_Details | 장비별 제어기 등 추가 사양 | 장비와 같은 Record_ID |
| Files | 관련 파일 | source_table + target_record |
| 공구경로 | 경로점·공구축 | 가공레코드 = 상세 가공 Record_ID |

`Record_ID`는 **Excel 내 행 식별용 추가 키**이며 업체 원본 컬럼이 아닙니다. 예: WS7 행을 추가하면 Machining_Conditions와 Machining_Geometry에도 WS7 행을 추가합니다. 부족한 보완 행은 오류로 표시합니다. Part_No·Part_Rev·Op_No 및 공구·장비 복합키는 업체 값으로 입력합니다.

3행은 설명, 4행은 컬럼명, **5행부터 실제 데이터**입니다. 시트에서 아래로 계속 행을 추가할 수 있고 기존 표 범위 밖의 데이터도 읽습니다. 헤더는 유지하고, Record_ID는 같은 시트 안에서 중복되지 않게 입력하세요. 필요하지 않은 빈 행은 무시합니다. 보완 시트도 행 형식이며, 가로로 너무 긴 표를 피하기 위해 조건·형상을 나눴습니다.

가공 순서는 행의 물리적 위치가 아니라 `execution_order`로 결정합니다. NC `TOOLNO`와 공구 마스터 번호는 구분합니다. 공구 교환 자체가 독립적인 NC 기능인 경우 이를 별도 NC 명령으로 생성하는 기능은 현재 범위에 포함하지 않습니다.

## 먼저 실행하기

프로젝트 루트 `Digital-Thread`에서 실행합니다. **Python 3.11~3.13**을 사용하세요. 검증 환경은 Python 3.12이며, 고정한 xsdata 버전은 Python 3.14를 지원하지 않습니다.

```bash
python3.12 -m venv .venv-els
.venv-els/bin/python -m pip install -r ISO_api/tools/els_dt_converter/requirements.txt
.venv-els/bin/python ISO_api/tools/els_dt_converter/convert.py \
  outputs/els_dt_converter/가상예제_DB행입력.xlsx \
  --out outputs/els_dt_converter/내_첫_변환
```

패키지를 처음 설치할 때만 패키지 다운로드가 필요합니다. 설치 후 변환은 네트워크 없이 실행됩니다. Windows에서는 `.venv-els/bin/python` 대신 `.venv-els\Scripts\python.exe`를 사용합니다.

가상예제와 `demo.nc`는 같은 폴더에 두세요. 예제는 모두 새로 만든 시험값이며, NC 파일에도 실행 가능한 가공 명령은 없습니다.

## 이전 세로 양식 참고

아래 내용은 이전에 제공한 `업체입력_빈양식.xlsx`에 대한 설명입니다. 새 행 입력 양식은 위의 **현재 양식** 설명을 따르세요. 단위·업체 복합키·파일 모드 및 출력 검증 규칙은 두 양식에 공통으로 적용됩니다.

입력 파일은 `outputs/els_dt_converter/업체입력_빈양식.xlsx`입니다. 노란 셀에 값을 입력하고 별도 이름으로 저장하세요.

| 시트 | 입력 내용 |
|---|---|
| 사용안내 | 범위, 입력 순서, 단위와 연결 방법 |
| 업체입력 | 기본 테이블 5개의 선택 컬럼. D열에 업체 값 입력 |
| 필수보완 | 업체 컬럼으로 채울 수 없는 값과 변환 규칙. D열에 입력 |
| 파일입력 | Part_File / Tool_File / Machine_File의 파일과 대상 연결 |
| 공구경로 | 선택 입력. 가공 레코드별 X/Y/Z와 공구축 I/J/K |

세로 표의 **테이블 + 레코드 + 컬럼**이 하나의 입력 칸을 식별합니다. 레코드 `P1`, `OP1`, `WS1`, `T1`, `M1`은 Excel 안에서만 사용하는 구분명입니다. 실제 자산 ID는 업체 키에서 자동 생성합니다.

레코드를 추가하려면 해당 테이블의 행 묶음을 복사하고 레코드를 `WS2` 등으로 변경하세요. 필수보완에도 같은 테이블과 레코드명을 사용합니다. 행 순서는 바꿔도 됩니다. 시트명과 4행의 헤더는 유지하고, 데이터는 5행부터 입력하세요. 필수/설명 열을 바꿔도 프로그램의 검증 규칙은 바뀌지 않습니다.

파트 번호·개정·공정 번호·장비 번호는 **문자열**입니다. `01`, `010`, `001`의 앞자리 0을 보존하세요. 숫자로 붙여넣은 ID는 거부합니다. 수식도 거부하므로 값으로 붙여넣어야 합니다. `false`는 유효한 필수 입력이며 빈칸과 구분합니다.

### 연결 규칙

| 원본 | 연결 키 | 생성 결과 |
|---|---|---|
| Part_Info | Part_No + Part_Rev | dt_project + Workpiece + dt_material |
| Operation_Info | Part_No + Part_Rev + Op_No | 공정별 Workplan |
| Operation_Machining | 위 공정 키 + PGMNO + REVNO + SEQNO | MachiningWorkingstep + FreeformOperation |
| Tool_Milling | 공구번호 + 공구사양 | dt_cutting_tool_13399 |
| Machine_Milling | 설비코드 + 설비번호 | dt_machine_tool |
| 파일 3개 테이블 | 입력 레코드 대상 | dt_file + DtReference |

- `TOOLNO`는 NC T번호로만 사용합니다. 공구 마스터는 **필수보완의 공구번호+공구사양**으로 직접 연결합니다.
- `execution_order`는 공정·가공의 실행 순서입니다. Op_No나 PGMNO를 사전순으로 정렬해 실행 순서를 추정하지 않습니다.
- 주축은 `SPINDLE_01/02`, 이송은 `FEED_01~04` 중 **의미를 확인한 컬럼**을 필수보완에서 선택합니다. 01 컬럼을 자동으로 가정하지 않습니다.
- 길이·좌표는 mm, 방향은 무차원 단위벡터입니다. `rpm ÷ 60 → 1/s`, `mm/min ÷ 60000 → m/s`로 변환합니다. 회전 부호는 유지합니다.
- 조립 전체 길이와 최대 절삭 깊이는 별도로 입력합니다. 공구 전장·날장·STICKOUT을 대신 넣지 않습니다.
- 안전평면은 공작물 좌표계, 피처 배치는 공작물 좌표계, 깊이평면은 피처 좌표계로 입력합니다. 각 평면의 X축과 Z축은 직교해야 합니다.
- 5축 장비라는 조건에서 동시 제어축 수를 추정하지 않습니다. 장비 종류·제어기 사양을 명시합니다.

파일 시트는 편의를 위해 하나로 묶었습니다. `source_table`에 원본 테이블을 지정하고, `target_record`에 다음 대상을 넣습니다.

- Part_File: Part_Info의 레코드(프로젝트) 또는 Operation_Info의 레코드(공정).
- Tool_File: Tool_Milling의 레코드.
- Machine_File: Machine_Milling의 레코드.

`File_Type`은 이 시험 양식에서 MIME 유형으로 정규화해 입력합니다(예: `text/plain`, `application/pdf`, `application/octet-stream`). 업체 원본이 확장자라면 그대로 복사하지 마세요. `File_Path`의 상대경로는 **Excel 파일이 있는 폴더**를 기준으로 합니다. 로컬에서 읽을 수 있는 실제 파일이 필요합니다. 관련 파일이 없다면 파일입력의 F1 행을 모두 삭제할 수 있으며, 이 경우 dt_file은 생성하지 않습니다.

### 파트·리비전 선택

여러 파트가 있으면 반드시 선택합니다.

```bash
.venv-els/bin/python ISO_api/tools/els_dt_converter/convert.py \
  /로컬/입력.xlsx --part 'PART-001' --rev '01' \
  --namespace 'urn:my-company:els-test' --out outputs/내_변환_001
```

입력 전체의 형식·필수값·키를 먼저 검증하고, 선택한 파트와 실제 사용하는 장비·공구·파일을 출력합니다. 업체/시험 환경마다 namespace를 구분하세요. 같은 업체 키와 namespace는 반복 실행에서 같은 자산 ID가 됩니다. 파일 ID는 대상·이름·개정·파일 내용 해시를 포함합니다.

## 결과와 오류 확인

- `project-….xml`, `machine-….xml`, `tool-….xml`, `material-….xml`, `file-….xml`: 자산별 XML.
- `report.json`: 성공 여부, 오류 셀, 입력 검증 목록, 지원하지 않는 컬럼, 사용 여부, 생성 자산 목록과 한계.
- `file_manifest.json`: 파일 해시, 복사 위치, 연결 자산, 업로드 필요 여부.
- `files/`: Excel에 지정한 관련 파일의 복사본.

필수값·연결·중복·단위·좌표 오류가 있으면 **report.json만 저장하고 XML은 생성하지 않습니다.** 종료 코드는 정상 `0`, 입력 오류 `2`입니다. 기존 출력 폴더는 덮어쓰지 않으므로 수정 후 새 출력 폴더를 지정하세요.

보고서에서 `input_checks`는 입력 형식·필수값 확인이고 `output_use`는 선택 여부 안내입니다. `unmapped_columns`는 사용자가 추가했지만 이 시험 프로필이 지원하지 않는 컬럼입니다. 원본 업체 DB 전체를 입력받지 않으므로 원본 전체 컬럼의 대조 결과를 뜻하지는 않습니다. XML에는 선택한 자산만 포함됩니다.

`model_required_fields_verified=true`는 **생성한 객체에 한해 현재 dataclass 모델의 required 메타데이터가 채워졌고 XML 왕복 검증을 통과했다**는 의미입니다. 이 양식의 필수 입력에는 변환기의 연결·선택 규칙도 포함되어 있으므로 모두 ISO 자체의 필수 속성인 것은 아닙니다.

## 파일의 로컬 모드와 서버 등록

기본 `--file-mode local`에서는 dt_file.value를 `pending-upload:<sha256>`로 기록합니다. **이 값은 실제 GridFS ID가 아니며 현행 서버 API에 그대로 등록할 수 없습니다.** 가짜 ObjectId를 만들지 않습니다.

이미 별도로 업로드한 파일이 있다면 파일입력의 `gridfs_id`에 실제 결과 ID를 넣고 다음처럼 실행합니다.

```bash
.venv-els/bin/python ISO_api/tools/els_dt_converter/convert.py \
  /로컬/입력.xlsx --file-mode gridfs --out outputs/내_변환_002
```

이 모드는 24자리 ObjectId **형식만** 검사합니다. 서버의 파일 존재 여부, 해시 일치, API 등록 성공 여부는 확인하지 않습니다. 업로드·DB 등록·참조 해석의 통합 검증은 별도 단계입니다.

## 현재 지원 범위

**5축 밀링의 공정 등록 구조를 시험하는 첫 번째 프로필**입니다. FreeformOperation + ToolpathFeature를 명시적으로 선택한 레코드만 처리합니다. 드릴링, 포켓·평면 등의 다른 밀링 작업 유형과 터닝은 아직 변환하지 않습니다. 모든 밀링을 이 프로필로 강제 변환하면 안 됩니다.

공구경로가 있으면 입력한 점열과 공구축 점열을 Polyline으로 저장합니다. 경로가 없어도 등록 초안 XML을 만들지만 보고서에 미완성을 표시합니다. 표면 형상 복원, CAD/NC 파일 해석, 공구축 보간, 셋업·고정구, 공차·전략, 충돌·역기구학·기계축 제한은 검증하지 않습니다. `machine_ready`는 항상 `false`입니다. 예제의 경로도 가상 좌표입니다.

공구 수치 속성명은 현재 DT 구현의 로컬 명칭을 사용합니다. 정식 ISO 13399 사전 코드·전체 공구 조립 모델의 인증을 의미하지 않습니다. BOM·견적·비용·실적은 입력 대상에서 제외했습니다. 실제 업체 레코드, 서버 업로드, 생산 장비로는 시험하지 않았습니다.

## 테스트

이 테스트는 로컬 Excel 자료를 사용하는 통합 테스트입니다. GitHub에는 도구 소스와 테스트 코드만 포함되며, `.gitignore`로 제외된 아래 자료는 별도로 준비해야 합니다. 저장소를 새로 복제한 상태에서는 테스트가 바로 실행되지 않습니다.

- `outputs/els_dt_converter/`: `가상예제.xlsx`, `업체입력_빈양식.xlsx`, `가상예제_DB행입력.xlsx`, `업체입력_빈양식_DB행입력.xlsx`, `업체DB_원본컬럼_빈양식.xlsx` 및 예제에서 참조하는 `demo.nc`
- `docs/`: `original_columns.json`의 `source`에 지정된 원본 테이블 정의서. 원본 컬럼 대조 테스트에 필요합니다.

실제 업체 자료나 생성된 XML 결과를 테스트 실행을 위해 Git에 추가하지 마세요. Python 3.11~3.13과 이 폴더의 `requirements.txt`에 명시된 패키지가 필요합니다.

```bash
.venv-els/bin/python -m unittest discover \
  -s ISO_api/tools/els_dt_converter -p 'test_*.py' -v
```

프로그램은 같은 저장소의 model_v31.py를 직접 사용합니다. 도구 폴더만 다른 PC로 복사하면 모델을 가져올 수 없으므로, 저장소와 입력 Excel을 함께 준비하세요. 모델 변경 시 테스트를 다시 실행해야 합니다.

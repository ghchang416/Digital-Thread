# ISO Project v3 API 코드 분석 (한글 정리본)

## 1. 분석 범위

본 문서는 업로드된 `iso_project_code.zip`을 기준으로 **v3 API만을
대상으로 분석**한 결과입니다.

-   main.py에 존재하는 v3 외 라우터 import는 분석에서 제외하였습니다.

-   분석 초점은 다음과 같습니다:

    -   프로젝트 XML 업로드
    -   CAM JSON 파싱
    -   WorkingStep 생성
    -   dt_cutting_tool_13399 생성
    -   데이터 플랫폼 업로드 흐름

------------------------------------------------------------------------

# 2. v3 기준 전체 구조

    src/
     ├── main.py
     ├── config.py
     ├── database.py
     │
     ├── apis/v3/
     │    ├── asset.py
     │    └── project.py
     │
     ├── services/
     │    ├── asset.py
     │    ├── file.py
     │    ├── v3_project.py
     │    └── __init__.py
     │
     ├── entities/
     │    ├── asset.py
     │    ├── file.py
     │    └── model_v31.py
     │
     ├── schemas/
     │    ├── asset.py
     │    ├── file.py
     │    └── project.py
     │
     └── utils/
          ├── v3_xml_parser.py
          ├── cam_common.py
          ├── cam_nx_adapter.py
          ├── cam_powermill_adapter.py
          ├── nc_spliter.py
          ├── file_modifier.py
          ├── xml_parser.py
          ├── asset_xml_parser.py
          ├── stock.py
          ├── exceptions.py
          └── env.py

------------------------------------------------------------------------

# 3. v3 API 엔드포인트 분석

## 3.1 /api/v3/assets

dt_asset의 전체 생명주기를 관리하는 API입니다.

### 주요 기능

-   dt_asset XML 업로드
-   MongoDB에 메타데이터 저장
-   dt_file의 경우 GridFS에 파일 저장
-   수정 / 삭제 / 조회 기능
-   NC 파일 업로드 시 dt_file 자동 생성

### 주요 서비스

-   AssetService
-   FileService

------------------------------------------------------------------------

## 3.2 /api/v3/projects

ISO 프로젝트 관리 API입니다.

### 주요 엔드포인트

  -----------------------------------------------------------------------
  엔드포인트                                      역할
  ----------------------------------------------- -----------------------
  POST /projects                                  dt_project 업로드

  GET /projects                                   프로젝트 목록 조회

  POST /projects/add-ref                          프로젝트에 자산 참조
                                                  추가

  PUT /projects/delete-ref                        참조 삭제

  POST /projects/cam-json                         CAM → WorkingStep +
                                                  Tool 생성

  POST /projects/upload-platform                  프로젝트 + 관련 자산
                                                  데이터 플랫폼 업로드
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 4. CAM → ISO 핵심 흐름

가장 중요한 로직은 다음 API에 구현되어 있습니다:

    POST /api/v3/projects/cam-json

이 API는 다음 순서로 동작합니다:

1.  프로젝트에 연결된 NC dt_file 조회
2.  NC에서 Tool Change 순서(T1, T2, T3...) 추출
3.  CAM JSON (NX 또는 PowerMill) 파싱
4.  Tool 개수와 Operation 개수 정합성 검증
5.  dt_cutting_tool_13399 생성
6.  WorkingStep XML 생성
7.  Tool 참조(ref) 삽입
8.  XML Schema 검증
9.  Tool 자산을 먼저 저장
10. 프로젝트 XML에 WorkingStep 추가
11. 실패 시 Tool 생성 롤백

이 로직은 ISO 14649 기반 디지털쓰레드 파이프라인의 핵심입니다.

------------------------------------------------------------------------

# 5. dt_cutting_tool_13399 생성 구조

주요 구현 위치:

-   utils/cam_common.py
-   utils/v3_xml_parser.py

### 생성 로직 특징

-   T번호별로 1개의 13399 Tool 생성
-   CAM JSON 매핑 파일 기반 값 추출
-   WorkingStep에 FullPath 참조 삽입
-   XML 스키마 요구사항에 맞게 더미 노드 보강

동일 T번호가 여러 번 등장해도 Tool XML은 1개만 생성됩니다 (캐싱 구조).

------------------------------------------------------------------------

# 6. 데이터 플랫폼 업로드 흐름

엔드포인트:

    POST /api/v3/projects/upload-platform

서비스:

    V3ProjectService.upload_project_and_related()

### 처리 순서

1.  dt_project XML 업로드
2.  프로젝트 참조 자산 수집
3.  타입별 업로드:
    -   dt_file (파일 바이너리 포함)
    -   dt_material
    -   dt_machine_tool
    -   dt_cutting_tool_13399
4.  업로드 성공 시 DB에 is_upload=True 표시

------------------------------------------------------------------------

# 7. 구조적 점검 사항 (v3 기준)

다음 사항은 실행 시 문제가 될 수 있습니다:

1.  services/**init**.py가 실제 존재하지 않는 모듈을 import하고 있음
2.  main.py에 v3 외 라우터 import가 존재 (분석에서는 제외)
3.  config import 경로가 실제 파일 위치와 다를 가능성 있음

v3만 정상 실행하려면 services/**init**.py 정리가 필요합니다.

------------------------------------------------------------------------

# 8. 내가 코드를 완전히 이해했는가?

## 아키텍처 및 로직 이해 수준

다음 사항은 완전히 이해한 상태입니다:

-   CAM → WorkingStep → 13399 생성 흐름
-   Tool 캐싱 구조
-   XML Schema 검증 및 보상 롤백 전략
-   MongoDB + GridFS 저장 구조
-   데이터 플랫폼 업로드 오케스트레이션

## 아직 확인되지 않은 부분

-   실제 XML 스키마 파일 버전
-   실제 CAM JSON 예시 데이터
-   데이터 플랫폼 API의 실제 응답 형식
-   운영 환경 설정 (.env, DB 정보 등)

즉,

아키텍처 및 코드 구조는 완전히 이해했으며, 운영 환경 및 실제 데이터
케이스는 추가 확인이 필요합니다.

------------------------------------------------------------------------

# 9. 전체 요약

v3 API는 단순 CRUD API가 아니라, ISO 14649 기반 디지털쓰레드 엔진입니다.

    Project XML
       ↓
    NC Tool Sequence 추출
       ↓
    CAM JSON 매핑
       ↓
    WorkingStep 생성
       ↓
    dt_cutting_tool_13399 생성
       ↓
    Schema 검증
       ↓
    Mongo + GridFS 저장
       ↓
    데이터 플랫폼 업로드

이 구조는 ISO 프로젝트 관리 + CAM 연계 + Tool 자산 관리 + 플랫폼 연계를
모두 포함한 통합 시스템입니다.

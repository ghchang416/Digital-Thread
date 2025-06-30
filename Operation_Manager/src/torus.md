### 1. 개요

TORUS 플랫폼의 Machine Data Model은 이종 CNC 벤더들의 데이터를 공통 포맷으로 정리해 장비 상태, 프로그램 실행, 가공 정보 등을 일관되게 모니터링하고 제어할 수 있도록 구성된 데이터 구조입니다. 이 모델은 공작기계의 상태를 디지털 트윈으로 표현하거나, 장비 간 통합 연계, 표준화된 가공 이력 저장 등 다양한 기능을 위한 기반 데이터로 활용됩니다.

---

### 2. 최상위 구조: `machine`

하나의 공작기계를 대표하는 최상위 객체입니다. 이 객체는 장비의 기본 정보와 함께 채널(channel), PLC, 공구영역(toolArea), 메모리(ncMemory) 등을 포함합니다.

### 주요 속성:

- `cncModel` (STRING): 해당 장비에 탑재된 NC의 모델명 (예: FANUC 0i, SIEMENS 840D)
- `numberOfChannels` (INTEGER): 하나의 장비에 존재하는 제어 채널 수 (ex. 2개일 경우 이중 스핀들 가공 가능)
- `cncVendor` (INTEGER): 제조사 구분 코드
    - 1: FANUC, 2: SIEMENS, 3: CSCAM, 4: MITSUBISHI, 5: KCNC
- `ncLinkState` (BOOLEAN): NC와의 연결 상태 (true: 연결됨, false: 연결 안 됨)
- `currentAccessLevel` (INTEGER): NC 접근 권한 등급 (1~7, SIEMENS 전용)
- `basicLengthUnit` (INTEGER): 단위 (0: metric, 1: inch 등)
- `machinePowerOnTime` (REAL): 장비 전원이 켜져 있던 시간 (단위: 분)
- `currentCncTime` (STRING): 장비 내부 시계 시간 (형식: yyyy-MM-ddTHH:mm:ss)
- `machineType` (INTEGER): 장비의 타입 (1: milling, 2: lathe 등)
- `ncMemory`: NC 프로그램 저장 메모리 정보를 포함하는 구조체 (자세한 구조는 아래에 설명)
- `channel[]`: 각 채널에 대한 제어 및 상태 정보를 나타내는 리스트 구조
- `toolArea[]`: 장비에 설치된 공구 그룹 및 공구 정보
- `buffer[]`: 센서 스트림 수집 구성 정보 (일부 벤더 한정)

---

### 3. `ncMemory` (NC 메모리 정보)

NC 장비의 프로그램 저장 공간 관련 정보를 나타냅니다.

- `totalCapacity` (REAL): 전체 메모리 용량 (Byte 단위)
- `usedCapacity` (REAL): 현재 사용 중인 용량
- `freeCapacity` (REAL): 남은 용량
- `rootPath` (STRING): NC 프로그램의 기본 디렉토리 경로 (ex. /cnc/prog/main)

---

### 4. `channel[]` (계통 정보)

하나의 장비에 포함된 채널별 제어/측정 상태 정보입니다. 각 채널은 별도의 축/스핀들/공구 제어가 가능하며, 독립적인 프로그램 실행도 가능합니다.

- `channelEnabled` (BOOLEAN): 해당 채널 활성화 여부
- `toolAreaNumber` (INTEGER): 연동된 공구 영역 번호
- `numberOfAxes`, `numberOfSpindles`: 축과 스핀들의 개수
- `alarmStatus`, `operateMode`, `ncState`, `motionStatus`, `emergencyStatus`: 장비 상태 코드
- `axis[]`: 제어 가능한 축 리스트 (아래 axis 구조 참조)
- `spindle[]`: 연결된 스핀들 리스트 (아래 spindle 구조 참조)
- `feed`: 축 이송 속도 정보 (feedRate 포함)
- `workStatus[]`: 현재 가공 수량 및 가공 시간 정보
- `activeTool`: 현재 활성화된 공구 정보
- `currentProgram`: 실행 중인 NC 프로그램 정보
- `workOffset[]`: 공작물 좌표계 설정 정보
- `alarm[]`: 발생한 알람 정보 리스트
- `variable[]`: 사용자 정의 변수

---

### 5. `axis[]` (축 정보)

각 축에 대한 위치, 부하, 제어 가능 여부, 제한 설정 등이 포함됩니다.

- `machinePosition`, `workPosition`, `relativePosition`: 머신/워크/상대 좌표 위치
- `axisLoad`: 축에 걸리는 부하 (단위 없음, 퍼센트 개념)
- `axisFeed`: 축 이송 속도 (mm/min 또는 inch/min)
- `axisEnabled`: 축 사용 여부
- `axisLimitPlus/Minus`, `workAreaLimitPlus/Minus`: 기계 및 가공영역 한계값
- `interlockEnabled`: 인터락 활성화 여부
- `axisCurrent`, `axisTemperature`: 전류, 온도 상태
- `axisPower`: 축별 전력 소비 정보 (자세한 구성은 아래 axisPower 참조)

### 6. `spindle[]` (스핀들 정보)

회전축(스핀들)의 부하, 온도, 속도, 전력 정보를 포함합니다.

- `spindleLoad`, `spindleOverride`: 부하 및 속도 오버라이드 비율
- `spindleLimit`: 회전 속도 한계값
- `spindleEnabled`, `spindleCurrent`, `spindleTemperature`
- `rpm`: 스핀들 회전 속도 정보 (`commandedSpeed`, `actualSpeed`, `speedUnit`)
- `spindlePower`: 전력 정보 (`actualPowerConsumption`, `powerConsumption`, `regeneratedPower`)

---

### 7. `feed` (이송 속도 정보)

가공 중 사용되는 이송 속도에 대한 제어 및 측정 정보입니다.

- `feedOverride`: 현재 오버라이드 비율 (예: 150%)
- `rapidOverride`: 급속이송 오버라이드 비율
- `feedRate`: 실제 이송 속도 (`commandedSpeed`, `actualSpeed`, `speedUnit`)

---

### 8. `workStatus[]` (가공 상태 정보)

장비에서 진행 중인 작업의 수량 및 가공 시간 정보입니다.

- `workCounter`: 가공 수량
    - `currentWorkCounter`: 현재까지 완료한 수량
    - `targetWorkCounter`: 목표 수량
    - `totalWorkCounter`: 누적 수량
- `machiningTime`: 가공 시간
    - `processingMachiningTime`: 현재까지 진행된 시간
    - `estimatedMachiningTime`: 남은 예상 시간
    - `actualCuttingTime`: 절삭 시간
    - `machineOperationTime`: 장비 전체 운전 시간

---

### 9. `currentProgram` (현재 실행 중인 프로그램)

NC 프로그램의 진행 상태와 블록 정보, 좌표계 상태 등을 나타냅니다.

- `sequenceNumber`, `currentBlock`, `lastBlock`, `nextBlock`: 실행 블록
- `activePartProgram`: 현재 실행 중인 프로그램명
- `programMode`: 현재 프로그램 실행 모드 (RUN, STOP 등)
- `modal[]`: 현재 사용 중인 G/M 코드 리스트
- `overallBlock[]`, `interruptBlock[]`: 프로그램 흐름 제어 관련 블록
- `currentWorkOffsetIndex`, `currentWorkOffsetCode`: 현재 G 코드 좌표계
- `currentTotalWorkOffset`: 총 오프셋 값
- `currentFile`, `mainFile`: 프로그램 파일 경로 및 정보
- `controlOption`: single block, dry run, block skip 등 실행 옵션

---

**10. 공통 경로 접근 형식**

```jsx
# 장비 모델명 조회
data://machine/cncModel?machine=1

# 첫 번째 장비의 첫 번째 채널, 두 번째 축의 부하 조회
data://machine/channel/axis/axisLoad?machine=1&channel=1&axis=2

# 첫 번째 장비의 첫 번째 채널, 첫 번째 스핀들의 소비 전력 조회
data://machine/channel/spindle/spindlePower/powerConsumption?machine=1&channel=1&spindle=1
```
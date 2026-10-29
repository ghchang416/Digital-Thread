"""Small, explicit ELS input profile. No production data or inferred defaults."""

# (column, type, required, mapping/help, synthetic example)
SOURCE = {
    'Part_Info': [
        ('Part_No', 'text', True, '파트 선택 키', 'DEMO-P001'),
        ('Part_Rev', 'text', True, '파트 개정 선택 키', '01'),
        ('Part_Name', 'text', True, 'DtProject.display_name', '가상 밀링 시험품'),
        ('Part_Material', 'text', True, 'DtMaterial.material_identifier', 'DEMO-ALLOY'),
        ('Spec_재질', 'text', True, 'DtMaterial.standard_identifier: 실제 규격을 입력', 'DEMO-SPEC'),
    ],
    'Operation_Info': [
        ('Part_No', 'text', True, 'Part_Info 연결', 'DEMO-P001'),
        ('Part_Rev', 'text', True, 'Part_Info 연결', '01'),
        ('Op_No', 'text', True, '공정 키. 실행 순서는 보완 시트에서 지정', '010'),
        ('공정명', 'text', True, '공정 식별명 → Workplan.its_id에 포함', '가상 자유곡면 밀링'),
        ('설비코드', 'text', True, 'Machine_Milling 연결', 'MC'),
        ('설비번호', 'text', True, 'Machine_Milling 연결', '001'),
    ],
    'Operation_Machining': [
        ('Part_No', 'text', True, '공정 연결', 'DEMO-P001'),
        ('Part_Rev', 'text', True, '공정 연결', '01'),
        ('Op_No', 'text', True, '공정 연결', '010'),
        ('PGMNO', 'text', True, '프로그램 식별', 'O1000'),
        ('REVNO', 'text', True, '프로그램 개정', '01'),
        ('SEQNO', 'integer', True, '프로그램 내 순서. 전체 실행 순서는 보완 시트', 10),
        ('TOOLNO', 'text', True, 'NC T번호. 공구 마스터 키와 별개', 'T01'),
        ('SPINDLE_01', 'number', False, '선택 후보: 보완 시트의 spindle_source로 선택', 6000),
        ('SPINDLE_02', 'number', False, '선택 후보: 단위와 회전 부호 확인', None),
        ('FEED_01', 'number', False, '선택 후보: 보완 시트의 feed_source로 선택', 600),
        ('FEED_02', 'number', False, '선택 후보', None),
        ('FEED_03', 'number', False, '선택 후보', None),
        ('FEED_04', 'number', False, '선택 후보', None),
    ],
    'Tool_Milling': [
        ('공구번호', 'text', True, '공구 복합키', 'TOOL-001'),
        ('공구사양', 'text', True, '공구 복합키', 'DEMO-D10'),
        ('날경 (mm)', 'positive', True, 'effective_cutting_diameter (mm)', 10),
        ('날수 (ea)', 'integer', True, 'number_of_effective_teeth', 4),
        ('코너R', 'nonnegative', False, 'corner_radius (mm)', 1),
        ('Maker', 'text', False, '공구 string_value: manufacturer', 'DEMO-TOOL-MAKER'),
    ],
    'Machine_Milling': [
        ('설비코드', 'text', True, '장비 복합키', 'MC'),
        ('설비번호', 'text', True, '장비 복합키', '001'),
        ('설비명 (모델)', 'text', True, 'DeviceId.model_name', 'DEMO-5AX'),
        ('메이커', 'text', True, 'DeviceId.manufacturer', 'DEMO-MACHINE-MAKER'),
        ('컨트롤러', 'text', True, 'NcController.controller_model', 'DEMO-CNC'),
        ('축수', 'integer', True, '이 변환기는 5축 장비만 지원. 동시 제어축과 별개', 5),
    ],
}
SUPPLEMENT = {
    'Operation_Info': [('execution_order', 'integer', True, '공정 실행 순서 (파트 내 중복 금지)', 1)],
    'Operation_Machining': [
        ('execution_order', 'integer', True, 'Workingstep 실행 순서 (공정 내 중복 금지)', 1),
        ('공구번호', 'text', True, 'Tool_Milling에 명시적으로 연결', 'TOOL-001'),
        ('공구사양', 'text', True, 'Tool_Milling에 명시적으로 연결', 'DEMO-D10'),
        ('operation_profile', 'freeform_toolpath', True, '현재 지원: freeform_toolpath. 다른 작업 유형은 별도 구현 필요', 'freeform_toolpath'),
        ('spindle_source', 'SPINDLE_01|SPINDLE_02', True, '주축 지령값으로 확인한 업체 컬럼', 'SPINDLE_01'),
        ('spindle_unit', 'rpm|1/s', True, '입력 단위. rpm → 1/s 변환; 부호 유지', 'rpm'),
        ('feed_source', 'FEED_01|FEED_02|FEED_03|FEED_04', True, '절삭 이송으로 확인한 업체 컬럼', 'FEED_01'),
        ('feed_unit', 'mm/min|m/s', True, '입력 단위. mm/min → m/s 변환', 'mm/min'),
        ('feedrate_reference', 'tcp|ccp', True, '이송 기준점', 'tcp'),
        ('synchronize_spindle_with_feed', 'bool', True, '주축·이송 동기화. true/false 명시', False),
        ('inhibit_feedrate_override', 'bool', True, '이송 오버라이드 금지', False),
        ('inhibit_spindle_override', 'bool', True, '주축 오버라이드 금지', False),
        ('coolant', 'bool', True, '공정 절삭유 ON/OFF', True),
        ('through_spindle_coolant', 'bool', True, '공정 주축 관통 절삭유 ON/OFF', False),
        ('chip_removal', 'bool', True, '공정 칩 제거 ON/OFF', True),
        ('overall_assembly_length', 'positive', True, '실제 사용 공구 조립 전체 길이 (mm). 단품 전장과 구분', 120),
        ('maximum_depth_of_cut', 'positive', True, '사용 공구 최대 절삭 깊이 (mm). 날장과 구분', 20),
        ('feature_origin', 'vector', True, '피처 원점 x,y,z (mm), 공작물 좌표계', '0,0,0'),
        ('feature_axis', 'unitvector', True, '피처 Z축 단위벡터 i,j,k', '0,0,1'),
        ('feature_ref_direction', 'unitvector', True, '피처 X축 단위벡터. Z축과 직교', '1,0,0'),
        ('security_origin', 'vector', True, '안전평면 원점 x,y,z (mm), 공작물 좌표계', '0,0,50'),
        ('security_axis', 'unitvector', True, '안전평면 법선 단위벡터', '0,0,1'),
        ('security_ref_direction', 'unitvector', True, '안전평면 X축 단위벡터', '1,0,0'),
        ('depth_origin', 'vector', True, '깊이평면 원점 (mm), 피처 좌표계', '0,0,-2'),
        ('depth_axis', 'unitvector', True, '깊이평면 법선 단위벡터', '0,0,1'),
        ('depth_ref_direction', 'unitvector', True, '깊이평면 X축 단위벡터', '1,0,0'),
    ],
    'Machine_Milling': [
        ('machine_class', 'MACHINING_CENTRE|MILLING_MACHINE', True, '장비 종류를 확인하여 선택', 'MACHINING_CENTRE'),
        ('serial_number', 'text', True, '제조 일련번호. 사내 설비번호와 구분', 'DEMO-SERIAL-001'),
        ('controller_manufacturer', 'text', True, '제어기 제조사', 'DEMO-CONTROL-MAKER'),
        ('units', 'METRIC', True, '이 시험 프로필은 METRIC만 지원', 'METRIC'),
        ('maximum_number_of_simultaneous_control_axes', 'integer', True, '동시 제어축 수. 5축 장비라도 별도 확인', 5),
        ('maximum_total_number_of_control_feed_axes', 'integer', True, '제어 이송축 수', 5),
        ('maximum_total_number_of_control_spindles', 'integer', True, '제어 주축 수', 1),
        ('minimum_linear_increment', 'positive', True, '최소 직선 지령 증분 (mm)', 0.001),
        ('minimum_angle_increment', 'positive', True, '최소 각도 지령 증분 (degree)', 0.001),
        ('maximum_number_of_multi_channel_control', 'integer', True, '제어 채널 수', 1),
    ],
}
FILES = [
    ('source_table', 'Part_File|Tool_File|Machine_File', True, '파일 원본 테이블', 'Part_File'),
    ('target_record', 'text', True, '업체입력의 P1/OP1/T1/M1 등 레코드명. 실제 DB 키 대신 입력 연결용', 'P1'),
    ('File_Name', 'text', True, '파일명', 'demo.nc'),
    ('File_Path', 'text', True, '로컬 파일 위치. 상대경로는 Excel 폴더 기준', 'demo.nc'),
    ('File_Type', 'text', True, 'MIME 유형으로 정규화한 값', 'text/plain'),
    ('Doc_Type', 'text', True, 'dt_file.category', 'NC'),
    ('Doc_Rev', 'text', False, '파일 개정', '01'),
    ('gridfs_id', 'text', False, '서버 등록 모드에서만 필수. 실제 업로드 결과 ObjectId', None),
]
RECORDS = {'Part_Info': 'P1', 'Operation_Info': 'OP1', 'Operation_Machining': 'WS1', 'Tool_Milling': 'T1', 'Machine_Milling': 'M1'}

# A worksheet row is a database record. Record_ID is a local workbook key,
# not an ELS business key or an output asset ID.
WS_LINK_COLUMNS = {'execution_order', '공구번호', '공구사양', 'operation_profile'}
ROW_LAYOUT = {
    name: (name, definitions + (SUPPLEMENT['Operation_Info'] if name == 'Operation_Info' else
        [f for f in SUPPLEMENT[name] if f[0] in WS_LINK_COLUMNS] if name == 'Operation_Machining' else []), False)
    for name, definitions in SOURCE.items()
}
ROW_LAYOUT.update({
    'Machining_Conditions': ('Operation_Machining', [f for f in SUPPLEMENT['Operation_Machining'] if f[0] not in WS_LINK_COLUMNS and f[1] not in ('vector', 'unitvector')], True),
    'Machining_Geometry': ('Operation_Machining', [f for f in SUPPLEMENT['Operation_Machining'] if f[1] in ('vector', 'unitvector')], True),
    'Machine_Details': ('Machine_Milling', SUPPLEMENT['Machine_Milling'], True),
    'Files': ('Files', FILES, False),
})

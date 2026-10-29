// Presentation only. Types, cardinalities, enum options and references come from the catalog.
export const operatorLabels: Record<string, string> = {
  display_name: '이름', element_description: '설명', its_id: '식별자', machine_tool: '설비 사양',
  description: '설비 설명', automatically_pallet_changeable: '자동 팔레트 교환',
  number_of_tools_in_tool_magazine: '공구 매거진 수용 개수', spindles: '주축', spindle_name: '주축 이름',
  spindle_power: '주축 출력', maximum_drive_speed: '최대 회전수', axis: '축 구성',
  number_of_axes: '전체 축 수', number_of_simultanious_axes: '동시 제어 축 수',
  positioning: '이동 범위·정밀도', maximum_range_of_motion: '축별 이동 범위', axis_name: '축 이름', motion_range: '이동 범위',
  standard_identifier: '재료 규격', material_identifier: '재질명', material_property: '재료 특성', parameter_name: '특성 이름·설명',
};

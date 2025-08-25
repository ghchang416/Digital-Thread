import os
import re
from typing import List, Dict


def detect_n_format(n_lines: List[str]):
    """기존 N번호 포맷 감지 (패딩 여부 + 자리수)"""
    n_values = []
    for line in n_lines:
        match = re.match(r"^N(\d+)", line.strip())
        if match:
            n_values.append(match.group(1))
    if not n_values:
        return {"padding": True, "width": 4}
    widths = [len(n) for n in n_values]
    avg_width = round(sum(widths) / len(widths))
    padding = all(n.startswith("0") and len(n) >= 3 for n in n_values)
    return {"padding": padding, "width": avg_width}


def renumber_lines(
    lines: List[str], start: int = 10, step: int = 10, n_format: Dict = None
):
    """리넘버링 수행: 기존 N넘버가 코드에 붙어 있으면 새로운 N도 붙여서 출력"""
    if n_format is None:
        n_format = {"padding": True, "width": 4}

    renumbered = []
    n = start

    prev_attached = False

    for line in lines:
        original_line = line.strip()
        if not original_line:
            continue

        attached = False  # N번호와 코드가 붙어 있는지 여부

        # 기존 N 제거 + 붙어 있는지 판별
        if original_line.startswith("N"):
            match = re.match(r"^N(\d+)(.*)", original_line)
            if match:
                n_val, rest = match.groups()
                attached = not rest.startswith(" ")
                prev_attached = attached
                content = rest.lstrip()
            else:
                content = original_line[1:]
        # N 번호 없는 것(추가한 종료코드에 대해서)도 붙여줘야 한다.
        else:
            content = original_line.lstrip()
            attached = prev_attached

        # 새로운 N 생성
        if n_format["padding"]:
            n_str = f"N{n:0{n_format['width']}d}"
        else:
            n_str = f"N{n}"

        # 붙여서 출력 여부
        if attached:
            renumbered.append(f"{n_str}{content}\n")
        else:
            renumbered.append(f"{n_str} {content}\n")

        n += step

    return renumbered


def split_by_tool_change_with_preamble(lines: List[str]):
    """툴 교체 기준으로 NC 세그먼트 분할 + 초기 셋팅 블럭 반환"""
    segments = []
    current = []
    preamble = []
    tool_pattern = re.compile(r"(T0*\d{1,3}\s*M0?6)|(M0?6\s*T0*\d{1,3})", re.IGNORECASE)
    # 기존 패턴 tool_pattern = re.compile(r"T0*\d{1,3}\s*M0?6", re.IGNORECASE)
    tool_found = False

    for line in lines:
        # 라인에 %가 있으면 바로 패스한다.
        if "%" in line:
            continue

        if tool_pattern.search(line):
            tool_found = True
            if current:
                segments.append(current)
            current = [line]
        else:
            if tool_found:
                current.append(line)
            else:
                preamble.append(line)

    if current:
        segments.append(current)

    # 마지막 segment의 %는 제거해야한다.

    return preamble, segments


def extract_onumber_from_preamble(preamble_lines: List[str]):
    """
    preamble에서 O넘버 또는 :넘버 추출 및 제거, %도 제거

    Returns:
        clean_lines: '%' 및 O넘버 라인 제거된 리스트
        onumber: 감지된 넘버 문자열 (예: 'O1234' or ':1234')
    """
    clean_lines = []
    onumber = None
    for line in preamble_lines:
        stripped = line.strip()
        if stripped == "%":
            continue  # % 제거

        # O1234 또는 :1234 둘 다 허용
        if onumber is None and re.match(r"^(O|:)\d+", stripped, re.IGNORECASE):
            onumber = stripped
            continue  # 감지 후 제거
        clean_lines.append(line)
    return clean_lines, onumber


def generate_segment_onumber(
    base_onumber: str, segment_index: int, full_segment: List[str]
):
    """
    원래 O넘버 (O0001 또는 :0001)를 기반으로 세그먼트별 새로운 O넘버를 생성
    segment_index 0부터 시작, 1000 더해서 생성
    """
    if base_onumber is None:
        return full_segment

    match = re.match(r"^(O|:)(\d+)", base_onumber.strip(), re.IGNORECASE)
    if not match:
        return full_segment

    prefix = match.group(1)  # 'O' 또는 ':'
    base_num = int(match.group(2))
    new_num = 1000 + base_num + segment_index  # 예: 1000 + 1 + 0 = 1001

    new_onum = prefix + str(new_num) + "\n"

    full_segment.insert(0, new_onum)
    return full_segment


def find_terminated_code(full_segment: List[str]):
    """
    라인의 마지막 줄에 M30 혹은 M02이 없다면 추가로 붙여주는 함수
    """
    last_line = full_segment[-1]

    pattern = re.compile(r"M(?:30|02|2)(?!\d)")
    if not pattern.search(last_line):
        full_segment.append("M30")

    return full_segment


def process_nc_file(input_path: str, output_dir: str):
    """전체 처리 함수"""
    os.makedirs(output_dir, exist_ok=True)
    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # N 포맷 감지
    # n_lines = [l for l in lines if re.match(r"^N\d+", l.strip())]
    # n_format = detect_n_format(n_lines)

    n_lines = [l for l in lines if re.match(r"^N\d+", l.strip())]
    n_format = detect_n_format(n_lines)
    has_n_number = bool(n_lines)

    # 초기 블럭 + 세그먼트 분할
    preamble, segments = split_by_tool_change_with_preamble(lines)

    # %와 O넘버 제거
    clear_preamble, onumber = extract_onumber_from_preamble(preamble)

    saved_paths = []
    for i, segment in enumerate(segments):
        full_segment = clear_preamble + segment  # 초기 설정 포함

        # full_seg에 M30이나 M02가 없다면 M30을 추가
        full_segment = find_terminated_code(full_segment)

        # 넘버링이 있으면 리넘버링 아니면 안함.
        if has_n_number:
            renumbered = renumber_lines(full_segment, n_format=n_format)
        else:
            renumbered = full_segment  # N 넘버 추가 안 함

        # 기존에 onumber가 있다면 full segment 마다 onumber를 다시 붙여준다.
        add_onumbered = generate_segment_onumber(onumber, i, renumbered)

        # 맨 앞과 뒤에 %를 붙여준다.
        add_onumbered.insert(0, "%\n")
        add_onumbered.append("%\n")

        base_filename = os.path.splitext(os.path.basename(input_path))[0]
        filename = f"{base_filename}_{i + 1}"

        # 🔽 폴더 이름은 파일 이름에서 확장자를 뺀 것
        folder_name = filename

        # 🔽 하위 디렉토리 생성: output_dir / folder_name
        segment_output_dir = os.path.join(output_dir, folder_name)
        os.makedirs(segment_output_dir, exist_ok=True)

        # 🔽 해당 폴더 아래에 파일 저장
        filepath = os.path.join(segment_output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(add_onumbered)

        saved_paths.append(filepath)

    return saved_paths


def extract_tool_numbers_from_paths(file_paths: List[str]) -> List[int]:
    """
    주어진 NC 파일 목록에서 툴 번호(T코드)를 순서대로 추출하여 정수 리스트로 반환.
    """
    tool_pattern = re.compile(r"(T0*\d{1,3})\s*M0?6|M0?6\s*(T0*\d{1,3})", re.IGNORECASE)
    tool_numbers = []

    for path in file_paths:
        with open(path, "r") as f:
            text = f.read()

        match = tool_pattern.search(text)
        if match:
            tool_str = match.group(1) or match.group(2)
            number = int(re.sub(r"[^\d]", "", tool_str))  # T코드에서 숫자만 추출
            tool_numbers.append(number)
        else:
            tool_numbers.append(None)

    return tool_numbers


# 예시 사용
if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # "../../../data/nc" 상대경로를 base_dir 기준 절대경로로 변환
    nc_dir = os.path.normpath(os.path.join(base_dir, "../../../data/nc"))
    input_nc_path = nc_dir + "/merge.tap"  # 원본 파일
    input_splited = input_nc_path.split(".")
    output_path = nc_dir + "/result_" + input_splited[0]
    output_folder = output_path  # 저장 폴더
    process_nc_file(input_nc_path, output_folder)

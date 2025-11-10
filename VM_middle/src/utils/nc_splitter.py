# src/utils/nc_splitter.py
import os
import re
from typing import List, Dict, Any, Optional


_TERM_LINE_RE = re.compile(r"^\s*M(?:30|0?2)\s*$", re.IGNORECASE)


def detect_n_format(n_lines: List[str]):
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
    if n_format is None:
        n_format = {"padding": True, "width": 4}
    renumbered = []
    n = start
    prev_attached = False
    for line in lines:
        original_line = line.strip()
        if not original_line:
            continue
        attached = False
        if original_line.startswith("N"):
            match = re.match(r"^N(\d+)(.*)", original_line)
            if match:
                n_val, rest = match.groups()
                attached = not rest.startswith(" ")
                prev_attached = attached
                content = rest.lstrip()
            else:
                content = original_line[1:]
        else:
            content = original_line.lstrip()
            attached = prev_attached
        if n_format["padding"]:
            n_str = f"N{n:0{n_format['width']}d}"
        else:
            n_str = f"N{n}"
        renumbered.append(f"{n_str}{content}\n" if attached else f"{n_str} {content}\n")
        n += step
    return renumbered


def split_by_tool_change_with_preamble(lines: List[str]):
    segments = []
    current = []
    preamble = []
    tool_pattern = re.compile(r"(T0*\d{1,3}\s*M0?6)|(M0?6\s*T0*\d{1,3})", re.IGNORECASE)
    tool_found = False
    for line in lines:
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
    return preamble, segments


def extract_onumber_from_preamble(preamble_lines: List[str]):
    clean_lines = []
    onumber = None
    for line in preamble_lines:
        stripped = line.strip()
        if stripped == "%":
            continue
        if onumber is None and re.match(r"^(O|:)\d+", stripped, re.IGNORECASE):
            onumber = stripped
            continue
        clean_lines.append(line)
    return clean_lines, onumber


def generate_segment_onumber(
    base_onumber: str, segment_index: int, full_segment: List[str]
):
    if base_onumber is None:
        return full_segment
    match = re.match(r"^(O|:)(\d+)", base_onumber.strip(), re.IGNORECASE)
    if not match:
        return full_segment
    prefix = match.group(1)
    base_num = int(match.group(2))
    new_num = 1000 + base_num + segment_index
    new_onum = prefix + str(new_num) + "\n"
    full_segment.insert(0, new_onum)
    return full_segment


def normalize_termination(full_segment: list[str], *, is_last: bool) -> list[str]:
    """
    - 모든 '%'는 본문에서 제거(파일 끝의 '%'는 별도로 추가 예정)
    - 중간 세그먼트: 마지막 줄이 M30/M02가 아니면 'M30'을 단독 라인으로 추가
    - 마지막 세그먼트: 원본 그대로(추가로 M30 붙이지 않음)
    - 'M30%' 같이 붙은 경우도 '%'를 분리해 'M30' 단독 라인 + (끝에 '%')가 되도록 정리
    """
    cleaned: list[str] = []
    for line in full_segment:
        # 본문 중 '%' 제거(마지막에 우리가 따로 '%\\n' 붙일 거라 지금은 제거)
        if "%" in line:
            line = line.replace("%", "")
        # 개행 보정
        if not line.endswith("\n"):
            line += "\n"
        cleaned.append(line)

    # 뒤쪽 공백 라인 정리
    while cleaned and cleaned[-1].strip() == "":
        cleaned.pop()

    if not is_last:
        # 마지막 줄이 종료 코드(M30/M02) 단독 라인이 아니면 추가
        if not cleaned or not _TERM_LINE_RE.match(cleaned[-1].strip()):
            cleaned.append("M30\n")

    # 마지막 세그먼트는 종료 코드 추가 안 함(원본 유지)
    return cleaned


def process_nc_text(
    nc_text: str,
    output_dir: str,
    base_filename_with_ext: str = "program.nc",
) -> List[str]:
    """
    원본 NC 텍스트를 규칙대로 분할/리넘버/종료코드 보정하고 디스크에 저장한다.
    저장 구조:
      tmp/<proj>/ncdata/<stem>_1/<stem>_1.<ext>
      tmp/<proj>/ncdata/<stem>_2/<stem>_2.<ext>
      ...
    반환: 저장된 '파일 경로'(확장자 포함) 리스트
    """
    os.makedirs(output_dir, exist_ok=True)

    stem, ext = os.path.splitext(os.path.basename(base_filename_with_ext))
    ext = ext or ".nc"  # 확장자 없으면 .nc 기본

    lines = nc_text.splitlines(True)  # keepends=True

    # N 포맷 감지
    n_lines = [l for l in lines if re.match(r"^N\d+", l.strip())]
    n_format = detect_n_format(n_lines)
    has_n_number = bool(n_lines)

    # 프리앰블/세그먼트
    preamble, segments = split_by_tool_change_with_preamble(lines)
    clear_preamble, onumber = extract_onumber_from_preamble(preamble)

    saved_paths: List[str] = []
    total = len(segments)

    for i, segment in enumerate(segments):
        is_last = i == total - 1

        full_segment = clear_preamble + segment
        # 🔽 종료 처리: 중간 세그먼트엔 M30을 단독 라인으로 보장,
        #               마지막 세그먼트엔 새로 붙이지 않음
        full_segment = normalize_termination(full_segment, is_last=is_last)

        if has_n_number:
            renumbered = renumber_lines(full_segment, n_format=n_format)
        else:
            renumbered = full_segment

        add_onumbered = generate_segment_onumber(onumber, i, renumbered)
        # 맨 앞/뒤에 %는 항상 별도 라인으로 부여
        add_onumbered.insert(0, "%\n")
        add_onumbered.append("%\n")

        numbered_stem = f"{stem}_{i + 1}"
        seg_dir = os.path.join(output_dir, numbered_stem)
        os.makedirs(seg_dir, exist_ok=True)

        file_path = os.path.join(seg_dir, f"{numbered_stem}{ext}")
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(add_onumbered)

        saved_paths.append(file_path)

    return saved_paths


def extract_tool_numbers_from_paths(file_paths: List[str]) -> List[Optional[int]]:
    tool_pattern = re.compile(r"(T0*\d{1,3})\s*M0?6|M0?6\s*(T0*\d{1,3})", re.IGNORECASE)
    tool_numbers = []
    for path in file_paths:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        match = tool_pattern.search(text)
        if match:
            tool_str = match.group(1) or match.group(2)
            number = int(re.sub(r"[^\d]", "", tool_str))
            tool_numbers.append(number)
        else:
            tool_numbers.append(None)
    return tool_numbers

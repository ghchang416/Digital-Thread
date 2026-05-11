from __future__ import annotations

from collections import Counter
from io import BytesIO
from pathlib import Path
import tempfile
import zipfile
from typing import Any, Iterable, Optional

from src.utils.nc_parser import NCParser


Point3 = tuple[float, float, float]


def parse_stock_box(stock_size: Optional[str]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    if not stock_size:
        return None, "stock_size is empty"

    parts = [part.strip() for part in stock_size.split(",")]
    if len(parts) != 6:
        return None, "stock_size must contain 6 comma-separated numbers"

    try:
        x_min, x_max, y_min, y_max, z_min, z_max = [float(part) for part in parts]
    except ValueError:
        return None, "stock_size contains non-numeric values"

    return {
        "min": [x_min, y_min, z_min],
        "max": [x_max, y_max, z_max],
        "source": "project_file_draft.stock_size",
    }, None


def build_toolpath_preview_from_zip(
    *,
    zip_bytes: bytes,
    processes: Iterable[Any],
    max_segments: int,
    include_rapid: bool,
    process_index: Optional[int] = None,
) -> dict[str, Any]:
    max_segments = max(1, int(max_segments))
    parser = NCParser()
    all_segments: list[dict[str, Any]] = []
    file_summaries: list[dict[str, Any]] = []

    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        zip_entries = [name for name in archive.namelist() if not name.endswith("/")]

        with tempfile.TemporaryDirectory(prefix="vm-toolpath-preview-") as tmp_dir:
            for index, process in enumerate(processes):
                if process_index is not None and index != process_index:
                    continue

                file_path = _get_process_value(process, "file_path")
                if not file_path:
                    file_summaries.append(
                        {
                            "process_index": index,
                            "file_path": None,
                            "segment_count": 0,
                            "type_counts": {},
                            "error": "process file_path is empty",
                        }
                    )
                    continue

                entry_name = match_zip_entry(file_path, zip_entries)
                if not entry_name:
                    file_summaries.append(
                        {
                            "process_index": index,
                            "file_path": file_path,
                            "segment_count": 0,
                            "type_counts": {},
                            "error": "NC file not found in ncdata.zip",
                        }
                    )
                    continue

                suffix = Path(entry_name).suffix or ".nc"
                tmp_path = Path(tmp_dir) / f"process_{index}{suffix}"
                tmp_path.write_bytes(archive.read(entry_name))

                parsed_segments = parser.parse_as_segments(str(tmp_path))
                normalized_segments = [
                    _normalize_segment(
                        segment,
                        process_index=index,
                        file_path=file_path,
                    )
                    for segment in parsed_segments
                    if include_rapid or segment.get("type") != "RAPID"
                ]

                type_counts = Counter(segment["type"] for segment in normalized_segments)
                file_summaries.append(
                    {
                        "process_index": index,
                        "file_path": file_path,
                        "zip_entry": entry_name,
                        "segment_count": len(normalized_segments),
                        "type_counts": dict(type_counts),
                    }
                )
                all_segments.extend(normalized_segments)

    returned_segments = _sample_segments(all_segments, max_segments)
    return {
        "toolpath_bounds": _compute_bounds(all_segments),
        "segments": returned_segments,
        "files": file_summaries,
        "summary": {
            "segment_count": len(all_segments),
            "returned_segment_count": len(returned_segments),
            "truncated": len(returned_segments) < len(all_segments),
            "sampling": "uniform" if len(returned_segments) < len(all_segments) else "none",
            "max_segments": max_segments,
            "process_count": len(file_summaries),
            "type_counts": dict(Counter(segment["type"] for segment in all_segments)),
        },
    }


def match_zip_entry(process_file_path: str, zip_entries: Iterable[str]) -> Optional[str]:
    normalized = _normalize_path(process_file_path)
    without_ncdata = _strip_ncdata_prefix(normalized)
    candidates = {normalized, without_ncdata}

    entries = list(zip_entries)
    normalized_entries = {_normalize_path(entry): entry for entry in entries}

    for candidate in candidates:
        if candidate in normalized_entries:
            return normalized_entries[candidate]

    for candidate in candidates:
        for normalized_entry, original_entry in normalized_entries.items():
            if normalized_entry.endswith("/" + candidate) or candidate.endswith("/" + normalized_entry):
                return original_entry

    basename = Path(normalized).name
    basename_matches = [
        original_entry
        for normalized_entry, original_entry in normalized_entries.items()
        if Path(normalized_entry).name == basename
    ]
    if len(basename_matches) == 1:
        return basename_matches[0]

    return None


def _normalize_path(value: str) -> str:
    return value.replace("\\", "/").strip().lstrip("./")


def _strip_ncdata_prefix(value: str) -> str:
    return value[len("ncdata/") :] if value.startswith("ncdata/") else value


def _get_process_value(process: Any, key: str) -> Any:
    if isinstance(process, dict):
        return process.get(key)
    return getattr(process, key, None)


def _normalize_segment(
    segment: dict[str, Any],
    *,
    process_index: int,
    file_path: str,
) -> dict[str, Any]:
    normalized = {
        "process_index": process_index,
        "file_path": file_path,
        "type": str(segment.get("type") or "FEED"),
        "mode": str(segment.get("mode") or ""),
        "start": _point_to_list(segment.get("start")),
        "end": _point_to_list(segment.get("end")),
        "feedrate": segment.get("feedrate"),
    }

    for key in ("arc_i", "arc_j", "arc_k"):
        if key in segment:
            normalized[key] = segment[key]

    return normalized


def _point_to_list(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return [0.0, 0.0, 0.0]
    return [float(value[0]), float(value[1]), float(value[2])]


def _sample_segments(segments: list[dict[str, Any]], max_segments: int) -> list[dict[str, Any]]:
    if len(segments) <= max_segments:
        return segments
    if max_segments <= 1:
        return [segments[0]]

    last_index = len(segments) - 1
    return [segments[round(i * last_index / (max_segments - 1))] for i in range(max_segments)]


def _compute_bounds(segments: list[dict[str, Any]]) -> Optional[dict[str, list[float]]]:
    points = [point for segment in segments for point in (segment["start"], segment["end"])]
    if not points:
        return None

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    zs = [point[2] for point in points]
    return {
        "min": [min(xs), min(ys), min(zs)],
        "max": [max(xs), max(ys), max(zs)],
    }

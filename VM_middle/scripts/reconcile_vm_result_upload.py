from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from datetime import datetime

from bson import ObjectId

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core import db as core_db
from src.core.config import settings
from src.core.db import get_db
from src.dao.files import GridFSFileStore
from src.dao.vm_file import VmFileDAO
from src.dao.vm_project import VmProjectDAO
from src.services.vm_file import VmFileService
from src.services.vm_project import VmProjectService


def _project_process_count(doc: dict[str, Any]) -> int:
    project_file = doc.get("project_file_draft") or {}
    processes = project_file.get("process") or []
    return len(processes) if isinstance(processes, list) else 0


def _build_upload_info(
    *,
    mode: str,
    seq_id: int,
    results: list[dict[str, Any]],
    process_count: int,
) -> dict[str, Any]:
    uploaded = sorted(
        {
            item["process_index"]
            for item in results
            if isinstance(item.get("process_index"), int)
        }
    )
    by_index = {
        item["process_index"]: item
        for item in results
        if isinstance(item.get("process_index"), int)
    }
    element_ids = [
        str(by_index[index].get("element_id") or "")
        for index in uploaded
        if by_index.get(index)
    ]
    return {
        "mode": mode,
        "seq_id": seq_id,
        "total_count": process_count,
        "uploaded_indices": uploaded,
        "uploaded_element_ids": [eid for eid in element_ids if eid],
        "last_uploaded_index": uploaded[-1] if uploaded else None,
        "last_uploaded_element_id": element_ids[-1] if element_ids else None,
        "failed_index": None,
        "error_message": None,
        "updated_at": datetime.now().isoformat(),
    }


async def reconcile(project_id: str, *, apply: bool) -> dict[str, Any]:
    await core_db.connect(settings.MONGO_URI, settings.MONGO_DB)
    try:
        database = get_db()
        project_dao = VmProjectDAO(database["vm_project"])
        file_dao = VmFileDAO(database["vm_file"])
        file_svc = VmFileService(file_dao, GridFSFileStore())
        svc = VmProjectService(project_dao, file_svc)

        oid = ObjectId(project_id)
        doc = await project_dao.get(oid)
        if not doc:
            raise SystemExit(f"vm_project not found: {project_id}")

        source = str(doc.get("source") or "iso").strip().lower()
        upload_mode = svc._resolve_upload_mode_from_doc(doc)
        if source != "dp" or upload_mode != "json":
            return {
                "project_id": project_id,
                "can_complete": False,
                "reason": "현재 스크립트는 DP source + json upload_mode만 복구합니다.",
                "source": source,
                "upload_mode": upload_mode,
            }

        gid = str(doc.get("gid") or "").strip()
        eid = str(doc.get("eid") or "").strip()
        wpid = doc.get("wpid")
        process_count = _project_process_count(doc)
        if not gid or not eid or process_count <= 0:
            return {
                "project_id": project_id,
                "can_complete": False,
                "reason": "gid/eid/process_count가 부족합니다.",
                "gid": gid,
                "eid": eid,
                "process_count": process_count,
            }

        existing = await svc._list_existing_dp_vm_results(gid=gid, eid=eid, wpid=wpid)
        seq_id = svc._select_json_upload_seq(doc, existing, process_count=process_count)
        selected = [item for item in existing if item.get("seq_id") == seq_id]
        usable = [
            item
            for item in selected
            if svc._dp_existing_result_is_usable(item)
            and isinstance(item.get("process_index"), int)
        ]
        uploaded_indices = sorted({item["process_index"] for item in usable})
        expected_indices = list(range(1, process_count + 1))
        missing_indices = [
            index for index in expected_indices if index not in uploaded_indices
        ]
        can_complete = not missing_indices
        upload_info = _build_upload_info(
            mode="json",
            seq_id=seq_id,
            results=usable,
            process_count=process_count,
        )

        if apply and can_complete:
            await project_dao.set_vm_result_upload(
                oid,
                upload_info=upload_info,
                project_status="completed",
                vm_raw_status=doc.get("vm_raw_status") or "COMPLETE",
                vm_error_message=None,
            )
            await project_dao.set_vm_poll_result(
                oid,
                status="completed",
                vm_state=doc.get("vm_raw_status") or "COMPLETE",
                vm_error_message=None,
            )

        return {
            "project_id": project_id,
            "display_name": doc.get("display_name"),
            "status": doc.get("status"),
            "vm_job_id": doc.get("vm_job_id"),
            "seq_id": seq_id,
            "process_count": process_count,
            "uploaded_indices": uploaded_indices,
            "missing_indices": missing_indices,
            "can_complete": can_complete,
            "applied": bool(apply and can_complete),
        }
    finally:
        await core_db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconcile VM JSON result upload status from existing DP results."
    )
    parser.add_argument("--project-id", required=True, help="vm_project ObjectId")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply DB updates. Defaults to dry-run.",
    )
    args = parser.parse_args()
    result = asyncio.run(reconcile(args.project_id, apply=args.apply))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

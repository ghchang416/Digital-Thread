from __future__ import annotations

import argparse
import asyncio
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from src.clients import dp as dp_client
from src.core.config import settings
from src.utils.xml_parser import extract_project_summary


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _candidate_aids(gid: str, aid: str) -> list[str]:
    candidates = [aid]
    if gid and aid and not aid.startswith(gid):
        candidates.append(f"{gid.rstrip('/')}/{aid.lstrip('/')}")
    return list(dict.fromkeys(candidates))


async def _load_dp_display_name(*, gid: str, aid: str, eid: str) -> str | None:
    last_error: Exception | None = None

    for candidate_aid in _candidate_aids(gid, aid):
        try:
            xml = await dp_client.get_element_xml(aid=candidate_aid, eid=eid)
        except Exception as exc:
            last_error = exc
            continue

        if not xml:
            continue

        summary = extract_project_summary(xml)
        display_name = summary.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()

    if last_error is not None:
        raise last_error
    return None


async def run(*, dry_run: bool, limit: int | None) -> int:
    client = AsyncIOMotorClient(settings.MONGO_URI)
    collection = client[settings.MONGO_DB]["vm_project"]

    query = {
        "source": "dp",
        "$or": [
            {"display_name": {"$exists": False}},
            {"display_name": None},
            {"display_name": ""},
        ],
    }

    cursor = collection.find(query).sort("created_at", 1)
    if limit is not None:
        cursor = cursor.limit(limit)

    matched = 0
    updated = 0
    skipped = 0
    failed = 0

    async for doc in cursor:
        matched += 1
        doc_id = doc.get("_id")
        gid = str(doc.get("gid") or "")
        aid = str(doc.get("aid") or "")
        eid = str(doc.get("eid") or "")

        if not (gid and aid and eid):
            skipped += 1
            print(f"SKIP missing keys id={doc_id} gid={gid!r} aid={aid!r} eid={eid!r}")
            continue

        try:
            display_name = await _load_dp_display_name(gid=gid, aid=aid, eid=eid)
        except Exception as exc:
            failed += 1
            print(f"FAIL id={doc_id} eid={eid} error={exc}")
            continue

        if _is_blank(display_name):
            skipped += 1
            print(f"SKIP no display_name id={doc_id} eid={eid}")
            continue

        print(
            f"{'DRY' if dry_run else 'SET'} id={doc_id} eid={eid} "
            f"display_name={display_name!r}"
        )

        if not dry_run:
            result = await collection.update_one(
                {
                    "_id": doc_id,
                    "$or": [
                        {"display_name": {"$exists": False}},
                        {"display_name": None},
                        {"display_name": ""},
                    ],
                },
                {
                    "$set": {"display_name": display_name}
                },
            )
            updated += result.modified_count

    print(
        f"SUMMARY matched={matched} updated={updated} skipped={skipped} "
        f"failed={failed} dry_run={dry_run}"
    )
    client.close()
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill missing display_name on DP VM projects."
    )
    parser.add_argument("--apply", action="store_true", help="write updates to MongoDB")
    parser.add_argument("--limit", type=int, default=None, help="max documents to scan")
    args = parser.parse_args()

    raise SystemExit(asyncio.run(run(dry_run=not args.apply, limit=args.limit)))


if __name__ == "__main__":
    main()

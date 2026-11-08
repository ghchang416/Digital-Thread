"""Generate synthetic backend candidates for the opt-in frontend storage contract test.

Run from ISO_api with the backend test environment. No DB, user files or browser
storage are accessed; the output path is an explicitly supplied test artifact.
"""
import argparse
import json
from pathlib import Path

from src.services.creator.catalog import get_catalog
from src.services.creator.els.build import prepare
from src.services.creator.els.profile import load_profile
from test_els_vertical import context_and_request, confirmed
from test_nc import NC


def export_fixture():
    context, request = context_and_request()
    request.request.expectedSequence = 1
    candidate = confirmed(prepare(context, request))
    context2, request2 = context_and_request(mode="append-tools")
    request2.baseDraft = request.baseDraft
    request2.request.baseDraftId = request.baseDraft.draftId
    request2.request.baseRevision = request.baseDraft.revision
    request2.request.expectedSequence = 1
    appended = prepare(context2, request2)
    catalog = dict(get_catalog())
    used = {node.typeId for draft in [request.baseDraft, candidate.draft, appended.draft] for node in draft.nodes.values()}
    catalog["types"] = {key: value for key, value in catalog["types"].items() if key in used}
    return dict(catalog=catalog, profileHash=load_profile()[1], nc=NC.decode(),
                base=request.baseDraft.model_dump(by_alias=True),
                replacement=candidate.model_dump(by_alias=True), append=appended.model_dump(by_alias=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(export_fixture(), ensure_ascii=False), encoding="utf-8")

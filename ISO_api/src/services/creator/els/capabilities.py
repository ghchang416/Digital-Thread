"""Fail-closed feature discovery; a present reader never enables unfinished import APIs."""
import os

from .profile import load_profile
from .reader import AccessReader, ReaderLimits, VERIFIED_FORMATS


def capabilities():
    requested = os.environ.get("CREATOR_ELS_ENABLED") == "1"
    present = AccessReader().available()
    reasons = ["IMPLEMENTATION_PENDING"]
    if not requested:
        reasons.append("DISABLED_BY_CONFIGURATION")
    if not present:
        reasons.append("READER_UNAVAILABLE")
    profile_hash = None
    try:
        profile_hash = load_profile()[1]
    except (ValueError, OSError):
        reasons.append("PROFILE_INVALID")
    return {"capability": "els-import-v1", "contractVersion": 1, "stage": "staged-vertical",
            "enabled": False, "requested": requested, "readerPresent": present, "readerReady": False,
            "inspectionEnabled": requested and present, "inspectionStage": "upload-and-source-catalog",
            "profileHash": profile_hash, "verifiedFixtureFormats": sorted(VERIFIED_FORMATS),
            "maxFileBytes": ReaderLimits().file_bytes, "reasons": reasons,
            "finalizable": False, "persisted": False}

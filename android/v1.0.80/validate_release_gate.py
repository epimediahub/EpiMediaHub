#!/usr/bin/env python3
"""Fail-closed release gate for public EpiMediaHub Android v1.0.80 updater."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
APPROVAL = ROOT / "RELEASE_GATE.json"
VIDEO = ROOT / "epimedia_intro_v10.mp4"
REQUIRED = (
    "approved_intro_34s_reviewed",
    "original_logo_verified_in_final_frames",
    "heartbeat_audible_and_in_sync",
    "episcene_explanation_verified",
    "smarttube_quality_on_real_stream_verified",
    "smarttube_creator_channel_navigation_verified",
    "galabox_player_and_red_status_verified",
    "fire_tv_playback_frequency_and_av_sync_verified",
    "galabox_intro_playback_and_av_sync_verified",
    "in_app_updater_signed_upgrade_verified",
    "iptv_vpn_episcene_and_licensing_regression_passed",
)
def validate():
    if os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        raise ValueError("STOP_PUBLIC_RELEASE_REQUIRES_MANUAL_DISPATCH")
    if os.environ.get("INPUT_RELEASE_TO_CUSTOMERS", "").lower() != "true":
        raise ValueError("STOP_PUBLIC_RELEASE_REQUIRES_EXPLICIT_RELEASE_FLAG")
    if not APPROVAL.is_file() or not VIDEO.is_file():
        raise ValueError("STOP_RELEASE_GATE_OR_APPROVED_INTRO_MISSING")
    gate = json.loads(APPROVAL.read_text(encoding="utf-8"))
    if gate.get("release_approved") is not True:
        raise ValueError("STOP_RELEASE_NOT_APPROVED")
    if gate.get("version") != "1.0.80" or type(gate.get("versionCode")) is not int or gate["versionCode"] != 1080:
        raise ValueError("STOP_RELEASE_VERSION_MISMATCH")
    for key in REQUIRED:
        if gate.get(key) is not True:
            raise ValueError("STOP_UNVERIFIED_RELEASE_REQUIREMENT: " + key)
    digest = hashlib.sha256(VIDEO.read_bytes()).hexdigest()
    if gate.get("approved_intro_sha256") != digest:
        raise ValueError("STOP_APPROVED_VIDEO_HASH_NOT_MATCHED")
    logo_ref = gate.get("official_logo_reference_sha256", "")
    if not isinstance(logo_ref, str) or not re.fullmatch(r"[0-9a-f]{64}", logo_ref):
        raise ValueError("STOP_ORIGINAL_LOGO_PROVENANCE_MISSING")
    evidence = gate.get("qa_evidence_url")
    if not isinstance(evidence, str) or not evidence.startswith("https://github.com/epimediahub/EpiMediaHub/actions/runs/"):
        raise ValueError("STOP_DEVICE_QA_EVIDENCE_MISSING")
    print("EPIMEDIAHUB_V180_EXPLICIT_RELEASE_GATE_PASSED", digest)

if __name__ == "__main__":
    try:
        validate()
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        sys.exit(str(error))

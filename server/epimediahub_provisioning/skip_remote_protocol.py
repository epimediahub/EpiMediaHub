"""Private, versioned computation protocol; the database stays on the Raspberry."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

PROTOCOL = 1
SERVER_IP = '10.87.26.1'
CLIENT_IP = '10.87.26.2'
PORT = 8790
INTERFACE = 'wg-epi-analysis'
LEASE_SECONDS = 12
TASK_SECONDS = 230
MAX_BODY = 2_000_000
COMPONENTS = ('skip_analysis.py', 'skip_automation.py', 'skip_detector_v2.py',
              'skip_detector_v3.py', 'skip_remote_client.py', 'skip_remote_protocol.py')


def versions():
    root = Path(__file__).resolve().parent
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in COMPONENTS}


def number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('invalid_request')
    return value


def words(value):
    if (not isinstance(value, list) or not 1 <= len(value) <= 10_000
            or any(type(word) is not int or not 0 <= word < 1 << 32 for word in value)):
        raise ValueError('invalid_request')
    return value


def window_payload(window):
    return dict(fp=[int(word) for word in window.fp], start_sec=window.start_sec,
                item_sec=window.item_sec, delay_sec=window.delay_sec,
                time_offset_sec=window.time_offset_sec, episode_id=window.episode_id,
                duration_sec=window.duration_sec, trusted=window.trusted)

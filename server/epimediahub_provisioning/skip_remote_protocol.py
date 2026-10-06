"""Private, versioned computation protocol; the database stays on the Raspberry."""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

PROTOCOL = 1
SERVER_IP = '10.87.26.1'
CLIENT_IP = '10.87.26.2'
PORT = 8790
PROVIDER_RELAY_PORT = 8791
INTERFACE = 'wg-epi-analysis'
LEASE_SECONDS = 12
TASK_SECONDS = 230
MAX_BODY = 2_000_000
COMPONENTS = ('skip_analysis.py', 'skip_automation.py', 'skip_detector_v2.py',
              'skip_detector_v3.py', 'skip_remote_client.py', 'skip_remote_protocol.py',
              'skip_visual.py', 'skip_scene.py', 'skip_release.py')


def relay_url(value):
    return isinstance(value, str) and re.fullmatch(
        r'http://' + re.escape(CLIENT_IP) + ':' + str(PROVIDER_RELAY_PORT)
        + r'/[A-Za-z0-9_-]{32}', value) is not None


class RelayInput(str):
    """An authenticated peer's fixed private endpoint, never a general HTTP URL."""
    def __new__(cls, value):
        if not relay_url(value):
            raise ValueError('unsafe_source')
        return super().__new__(cls, value)


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
                duration_sec=window.duration_sec, trusted=window.trusted,
                trusted_ranges=[list(value) for value in window.trusted_ranges])

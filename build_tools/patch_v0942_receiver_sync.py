#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_v0942_receiver_sync.py /path/to/plugin.py")
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
if 'PLUGIN_VERSION = "0.9.41"' not in text:
    raise SystemExit("expected v0.9.41 source")
text = text.replace('PLUGIN_VERSION = "0.9.41"', 'PLUGIN_VERSION = "0.9.42"', 1)
anchor = 'def session_start(reason, **kwargs):\n'
if anchor not in text:
    raise SystemExit("session_start anchor missing")
text = text.replace(anchor, '''def _start_receiver_config_sync():
    try:
        from . import receiver_sync_client
    except Exception:
        try:
            import receiver_sync_client
        except Exception:
            return
    try:
        receiver_sync_client.start(sys.modules[__name__])
    except Exception:
        pass


def session_start(reason, **kwargs):
''', 1)
needle = '    _install_standby_hook(session)\n\n    try:\n        if not load_global_settings().get("autostart_app", False):\n'
if needle not in text:
    raise SystemExit("session hook anchor missing")
text = text.replace(needle, '    _install_standby_hook(session)\n    _start_receiver_config_sync()\n\n    try:\n        if not load_global_settings().get("autostart_app", False):\n', 1)
path.write_text(text, encoding="utf-8")
print("patched", path)

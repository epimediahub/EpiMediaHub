#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
manager = root / "app/src/main/java/de/epimediahub/app/data/UpdateManager.kt"
text = manager.read_text()
anchor = '''    fun pending(context: Context): AppUpdateInfo? {
'''
if text.count(anchor) != 1:
    raise SystemExit(f"updater pending anchor mismatch: {text.count(anchor)}")
insert = '''    fun cancelScheduled(context: Context) {
        WorkManager.getInstance(context.applicationContext).cancelUniqueWork(WORK_NAME)
    }

'''
text = text.replace(anchor, insert + anchor, 1)
manager.write_text(text)

if 'fun cancelScheduled(context: Context)' not in manager.read_text():
    raise SystemExit('cancelScheduled compatibility method missing')

print("Android v0.6.4.11 updater cancelScheduled compatibility fix applied")

#!/usr/bin/env python3
"""Keep Kids navigation open when no parental PIN has been configured."""
import os
import shutil
from pathlib import Path

root = Path(os.environ['PROJECT_ROOT'])
java = root / 'app/src/main/java/de/epimediahub/app'
here = Path(__file__).resolve().parent
build = root / 'app/build.gradle.kts'
text = build.read_text()
assert 'versionCode = 1029' in text and 'versionName = "1.0.29"' in text
build.write_text(text.replace('versionCode = 1029', 'versionCode = 1030').replace('versionName = "1.0.29"', 'versionName = "1.0.30"'))
for path in java.rglob('*.kt'):
    text = path.read_text()
    if '1.0.29' in text:
        path.write_text(text.replace('1.0.29', '1.0.30'))

gate = java / 'ui/V129SmartTubeGate.kt'
text = gate.read_text()
start = text.index('@Composable\ninternal fun V129SmartTubeGate(')
end = text.index('@Composable\ninternal fun V129ModeChooser(', start)
text = text[:start] + text[end:]
old = '    load: suspend () -> Result<List<V100SmartTubeRow>>\n)'
assert text.count(old) == 1
text = text.replace(old, '    load: suspend () -> Result<List<V100SmartTubeRow>>, exitRequiresPin: Boolean = false\n)')
old = '{ Text("Eltern · PIN", color = Color.White) }'
assert text.count(old) == 1
text = text.replace(old, '{ Text(if (exitRequiresPin) "Eltern · PIN" else "Zurück", color = Color.White) }')
gate.write_text(text)
shutil.copyfile(here / 'V130SmartTubeGate.kt', java / 'ui/V130SmartTubeGate.kt')
tests = root / 'app/src/test/java/de/epimediahub/app/ui'
tests.mkdir(parents=True, exist_ok=True)
for path in here.glob('*Test.kt'):
    shutil.copyfile(path, tests / path.name)
print('Android 1.0.30: optional Kids exit PIN installed')

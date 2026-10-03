"""Exercise the new installer's preflight, preserved data and code rollback."""
import json
import os
from pathlib import Path
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProgressInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base, self.data, self.units, self.bin = [self.root / name for name in ('app', 'data', 'units', 'bin')]
        for path in (self.base / '.venv/bin', self.data, self.units, self.bin):
            path.mkdir(parents=True, exist_ok=True)
        for source in ROOT.glob('*.py'):
            shutil.copyfile(source, self.base / source.name)
        shutil.copytree(ROOT / 'templates', self.base / 'templates')
        self.files = ['skip_analysis_worker.py', 'skip_automation.py', 'skip_markers.py', 'skip_release.py', 'skip_detector_v3.py']
        self.originals = {}
        for name in self.files:
            path = self.base / name
            path.write_text(path.read_text() + '\n# Previous installed code\n')
            self.originals[name] = path.read_bytes()
        with sqlite3.connect(self.data / 'provisioning.db') as con:
            con.executescript("CREATE TABLE preserved_data(value TEXT); INSERT INTO preserved_data VALUES('manual-marker');")
        self.envfile = self.root / 'server.env'
        self.envfile.write_text(f'EPIMEDIAHUB_DATA_DIR="{self.data}"\nEPIMEDIAHUB_ADMIN_TOKEN="fixture-token"\nEPIMEDIAHUB_ADMIN_PASSWORD="fixture-password"\nEPIMEDIAHUB_SECRET_KEY="fixture-secret"\n')
        python = self.base / '.venv/bin/python'
        python.write_text('#!/usr/bin/env bash\nexec ' + shlex.quote(sys.executable) + ' "$@"\n')
        python.chmod(0o755)
        self.state = self.root / 'services.json'
        self.state.write_text(json.dumps({'active': True, 'events': []}))
        self.script('id', "print('0')")
        self.script('install', "import shutil\nshutil.copyfile(sys.argv[-2],sys.argv[-1])")
        self.script('systemctl', '''
import json
from pathlib import Path
p=Path(os.environ['FIXTURE_STATE']); data=json.loads(p.read_text()); args=sys.argv[1:]
if args[0]=='is-active': raise SystemExit(0 if data['active'] else 3)
data['events'].append(args)
if args[0]=='stop': data['active']=False
if args[0]=='start' and 'epimediahub-skip-analysis.timer' in args: data['active']=True
p.write_text(json.dumps(data))
''')
        self.script('curl', '''
import json,shutil
from pathlib import Path
args=sys.argv[1:]; out=Path(args[args.index('-o')+1]); url=next(x for x in args if x.startswith('http'))
mode=os.environ['FIXTURE_MODE']
if '127.0.0.1' in url:
    out.write_text(json.dumps({'status':'broken' if mode=='bad-health' else 'ok'}))
else:
    name=url.rsplit('/',1)[-1]
    shutil.copyfile(Path(os.environ['FIXTURE_SOURCE'],name),out)
    if mode=='corrupt' and name=='skip_analysis_worker.py': out.write_text('syntax error @')
''')
        self.env = os.environ | dict(EPIMEDIAHUB_APP_DIR=str(self.base), EPIMEDIAHUB_ENV_FILE=str(self.envfile),
            EPIMEDIAHUB_SYSTEMD_DIR=str(self.units), FIXTURE_STATE=str(self.state), FIXTURE_SOURCE=str(ROOT),
            PATH=str(self.bin) + os.pathsep + os.environ['PATH'])

    def script(self, name, text):
        path = self.bin / name
        path.write_text('#!' + sys.executable + '\nimport os,sys\n' + text)
        path.chmod(0o755)

    def run_update(self, mode='success'):
        return subprocess.run(['bash', str(ROOT / 'deploy/install_skip_progress.sh')],
            env=self.env | dict(FIXTURE_MODE=mode), text=True, capture_output=True, timeout=45)

    def test_success_preserves_data_and_resource_limits_and_starts_sequential_worker(self):
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        service = (self.units / 'epimediahub-skip-analysis.service.d/progress.conf').read_text()
        self.assertIn('--batch --max-jobs 4 --max-seconds 600', service)
        self.assertNotIn('CPUQuota', service)
        self.assertNotIn('MemoryMax', service)
        with sqlite3.connect(self.data / 'provisioning.db') as con:
            self.assertEqual(con.execute('SELECT value FROM preserved_data').fetchone()[0], 'manual-marker')
            self.assertTrue(con.execute("SELECT 1 FROM sqlite_master WHERE name='skip_presence_sessions'").fetchone())
        backups = list((self.base / 'backups').glob('*/provisioning.db'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].stat().st_mode & 0o077, 0)
        state = json.loads(self.state.read_text())
        self.assertTrue(state['active'])
        self.assertIn(['start', '--no-block', 'epimediahub-skip-analysis.service'], state['events'])
        self.assertFalse(any('epimediahub-skip-analysis.service' in event and event[0]=='stop' for event in state['events']))

    def test_corrupt_download_leaves_installed_code_and_active_timer_untouched(self):
        result = self.run_update('corrupt')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(self.state.read_text())['events'], [])
        for name, data in self.originals.items():
            self.assertEqual((self.base / name).read_bytes(), data)

    def test_failed_health_restores_code_units_and_timer_without_replacing_user_data(self):
        result = self.run_update('bad-health')
        self.assertNotEqual(result.returncode, 0)
        for name, data in self.originals.items():
            self.assertEqual((self.base / name).read_bytes(), data)
        self.assertTrue(json.loads(self.state.read_text())['active'])
        self.assertFalse((self.units / 'epimediahub-skip-analysis.service.d/progress.conf').exists())
        with sqlite3.connect(self.data / 'provisioning.db') as con:
            self.assertEqual(con.execute('SELECT value FROM preserved_data').fetchone()[0], 'manual-marker')

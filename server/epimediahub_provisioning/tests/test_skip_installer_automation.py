"""Run the shipped Bash installer only against isolated paths and fake services."""
from __future__ import annotations

import fcntl
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from test_skip_analysis_references import ReferenceFixture, REAL_FLASK

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(REAL_FLASK, "Full backend dependencies required for installer preconditions")
class InstallerTests(ReferenceFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.workspace = Path(self.temp.name)
        self.appdir = self.workspace / 'app'
        self.datadir = self.workspace / 'data'
        self.bindir = self.workspace / 'bin'
        self.backups = self.workspace / 'backups'
        for directory in (self.appdir / '.venv/bin', self.appdir / 'templates', self.datadir, self.bindir, self.backups):
            directory.mkdir(parents=True, exist_ok=True)
        shutil.move(self.db_path, self.datadir / 'provisioning.db')
        self.db_path = self.datadir / 'provisioning.db'
        self.originals = {'skip_analysis.py': 'OLD_ANALYSIS = True\n', 'skip_analysis_worker.py': 'OLD_WORKER = True\n',
                          'skip_markers.py': 'OLD_MARKERS = True\n', 'templates/skip_markers.html': '<p>previous dashboard</p>\n'}
        for name, content in self.originals.items():
            (self.appdir / name).write_text(content)
        self.state = self.workspace / 'services.json'
        self.state.write_text(json.dumps({'timer': True, 'events': []}))
        self.envfile = self.workspace / 'server.env'
        self.envfile.write_text('EPIMEDIAHUB_DATA_DIR="'+str(self.datadir)+'"\nUNRELATED_SECRET="not-read-or-executed"\n')
        self.marker(self.seed)
        self.waiting()
        with self.db() as con:
            con.execute("INSERT INTO skip_auto_settings VALUES(1,0,0,'previous-choice')")
        source = (ROOT / 'deploy/install_skip_automation.sh').read_text()
        source_ref = re.search(r'^source_ref=([a-f0-9]{40})$',source,re.M).group(1)
        source = source.replace('app_dir=/opt/epimediahub/provisioning', 'app_dir='+str(self.appdir))
        source = source.replace('env_file=/etc/epimediahub/provisioning.env', 'env_file='+str(self.envfile))
        source = source.replace('-p /var/tmp', '-p '+str(self.workspace))
        source = source.replace('/var/backups/epimediahub/skip-automation-', str(self.backups / 'skip-automation-'))
        self.installer = self.workspace / 'installer.sh'
        self.installer.write_text(source)
        self.script('id', "print('0')")
        self.script('chown', 'pass')
        self.script('install', "import shutil\nshutil.copyfile(sys.argv[-2],sys.argv[-1])")
        self.script('curl', """
import json, shutil
from pathlib import Path
args=sys.argv[1:]; output=Path(args[args.index('-o')+1]); url=next(x for x in args if x.startswith('http'))
mode=os.environ.get('FIXTURE_MODE','success')
if '127.0.0.1' in url:
    new='skip_season_automation' in Path(os.environ['FIXTURE_APP'],'skip_markers.py').read_text()
    body={'api_version':'0.8.0' if mode=='old-api' else '0.8.2','status':'ok','features':{'skip_season_automation':new and mode!='bad-health'}}
    output.write_text(json.dumps(body))
else:
    assert '/'+os.environ['FIXTURE_REF']+'/' in url
    relative=url.split('/server/epimediahub_provisioning/')[1]
    shutil.copyfile(Path(os.environ['FIXTURE_BUNDLE'],relative),output)
    if mode=='corrupt' and relative=='skip_automation.py': output.write_text('corrupted download')
""")
        self.script('systemctl', """
import json
from pathlib import Path
p=Path(os.environ['FIXTURE_STATE']); state=json.loads(p.read_text()); args=sys.argv[1:]
if args[0]=='is-active': raise SystemExit(0 if state['timer'] else 3)
state['events'].append(args)
if args[0]=='stop' and 'epimediahub-skip-analysis.timer' in args: state['timer']=False
if args[0]=='start' and 'epimediahub-skip-analysis.timer' in args: state['timer']=True
p.write_text(json.dumps(state))
""")
        # The actual policy/audio suite is a separate CI step. Here inject its
        # exit code to exercise both preflight outcomes without repeating it.
        wrapper = """
import os, subprocess, sys
if sys.argv[1:3]==['-m','unittest']:
    raise SystemExit(1 if os.environ.get('FIXTURE_MODE')=='preflight' else 0)
os.execv(os.environ['FIXTURE_PYTHON'],[os.environ['FIXTURE_PYTHON'],*sys.argv[1:]])
"""
        python_path = self.appdir / '.venv/bin/python'
        python_path.write_text('#!'+sys.executable+'\n'+wrapper); python_path.chmod(0o755)
        self.env = os.environ | dict(PATH=str(self.bindir)+os.pathsep+os.environ['PATH'], FIXTURE_BUNDLE=str(ROOT),
                                     FIXTURE_APP=str(self.appdir),FIXTURE_STATE=str(self.state),FIXTURE_PYTHON=sys.executable,FIXTURE_REF=source_ref)

    def script(self, name, code):
        p = self.bindir / name
        p.write_text('#!'+sys.executable+'\nimport os,sys\n'+code+'\n'); p.chmod(0o755)

    def launch(self, mode='success', enable=True):
        result = subprocess.run(['bash', str(self.installer)] + (['--enable-automatic'] if enable else []),
                                env=self.env | dict(FIXTURE_MODE=mode), text=True, capture_output=True, timeout=45)
        self.assertNotIn('not-read-or-executed', result.stdout + result.stderr)
        return result

    def unchanged(self):
        for name, content in self.originals.items():
            self.assertEqual((self.appdir / name).read_text(), content)
        self.assertFalse((self.appdir / 'skip_automation.py').exists())
        with self.db() as con:
            marker = con.execute('SELECT * FROM skip_records').fetchone()
            self.assertEqual((marker['status'],marker['start_ms'],marker['end_ms']), ('approved',283043,309573))

    def test_success_enables_only_existing_audio_opt_ins_and_preserves_marker_backup(self):
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        with self.db() as con:
            states = dict((r['playlist_id'],r['enabled']) for r in con.execute('SELECT * FROM skip_auto_settings'))
            self.assertEqual(states, {1:1,2:1})
            self.assertEqual(con.execute('SELECT status,start_ms,end_ms FROM skip_records').fetchone()[:], ('approved',283043,309573))
        self.assertEqual(len(list(self.backups.glob('*/provisioning.db'))), 1)
        self.assertTrue(json.loads(self.state.read_text())['timer'])

    def test_no_activation_preserves_inactive_timer_and_previous_settings(self):
        self.state.write_text(json.dumps({'timer':False,'events':[]}))
        result=self.launch(enable=False)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(json.loads(self.state.read_text())['timer'])
        with self.db() as con:
            self.assertEqual(con.execute('SELECT enabled,online_enabled,updated_at FROM skip_auto_settings WHERE playlist_id=1').fetchone()[:], (0,0,'previous-choice'))

    def test_explicit_activation_starts_previously_inactive_timer(self):
        self.state.write_text(json.dumps({'timer':False,'events':[]}))
        result=self.launch()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(self.state.read_text())['timer'])

    def test_bad_health_restores_code_settings_and_original_timer_without_losing_markers(self):
        result=self.launch('bad-health')
        self.assertNotEqual(result.returncode,0)
        self.unchanged()
        with self.db() as con:
            self.assertEqual(con.execute('SELECT enabled,online_enabled,updated_at FROM skip_auto_settings WHERE playlist_id=1').fetchone()[:], (0,0,'previous-choice'))
            self.assertIsNone(con.execute('SELECT * FROM skip_auto_settings WHERE playlist_id=2').fetchone())
            self.assertEqual(con.execute('SELECT status,attempts,detail FROM skip_jobs').fetchone()[:], ('no_reference',2,'previous'))
        self.assertTrue(json.loads(self.state.read_text())['timer'])

    def test_corrupt_download_never_stops_services_or_changes_code(self):
        result=self.launch('corrupt')
        self.assertNotEqual(result.returncode,0)
        self.unchanged()
        self.assertEqual(json.loads(self.state.read_text())['events'],[])

    def test_failed_preflight_never_stops_services(self):
        result=self.launch('preflight')
        self.assertNotEqual(result.returncode,0)
        self.unchanged()
        self.assertEqual(json.loads(self.state.read_text())['events'],[])

    def test_busy_worker_keeps_service_and_lock_inode_intact(self):
        lockpath=self.datadir/'skip-analysis.lock'
        with lockpath.open('w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            inode=lockpath.stat().st_ino
            result=self.launch()
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(lockpath.stat().st_ino,inode)
        self.unchanged()
        self.assertEqual(json.loads(self.state.read_text())['events'],[])

    def test_old_api_rejects_before_any_service_change(self):
        result=self.launch('old-api')
        self.assertNotEqual(result.returncode,0)
        self.unchanged()
        self.assertEqual(json.loads(self.state.read_text())['events'],[])


if __name__=='__main__':
    unittest.main()

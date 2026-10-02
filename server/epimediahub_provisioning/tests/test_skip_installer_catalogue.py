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
import time
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
        self.originals = {'app.py': 'OLD_APP = True\n', 'skip_analysis.py': 'OLD_ANALYSIS = True\n', 'skip_analysis_worker.py': 'OLD_WORKER = True\n',
                          'skip_markers.py': 'OLD_MARKERS = True\nAPI_VERSION = "0.8.2"\ndef v082_skip_dashboard(): pass\ndef v082_skip_presence(): pass\n', 'templates/skip_markers.html': '<p>previous dashboard</p>\n'}
        for name, content in self.originals.items():
            (self.appdir / name).write_text(content)
        self.state = self.workspace / 'services.json'
        self.state.write_text(json.dumps({'timer': True, 'events': []}))
        self.envfile = self.workspace / 'server.env'
        self.envfile.write_text('EPIMEDIAHUB_DATA_DIR="'+str(self.datadir)+'"\nUNRELATED_SECRET="not-read-or-executed"\n')
        self.marker(self.seed)
        self.waiting()
        with self.db() as con:
            con.execute("ALTER TABLE customers ADD COLUMN name TEXT NOT NULL DEFAULT 'Fixture customer'")
            con.execute("INSERT INTO skip_auto_settings VALUES(1,1,1,'previous-choice')")
            con.execute("INSERT INTO skip_catalogue_settings VALUES(1,0,'previous-choice')")
            con.execute("INSERT INTO skip_auto_metadata_config VALUES('tmdb_api_key',?,'previous-choice')",("a"*32,))
        source = (ROOT / 'deploy/install_skip_catalogue.sh').read_text()
        source_ref = re.search(r'^source_ref=([a-f0-9]{40})$',source,re.M).group(1)
        source = source.replace('app_dir=/opt/epimediahub/provisioning', 'app_dir='+str(self.appdir))
        source = source.replace('env_file=/etc/epimediahub/provisioning.env', 'env_file='+str(self.envfile))
        source = source.replace('-p /var/tmp', '-p '+str(self.workspace))
        source = source.replace('/var/backups/epimediahub/skip-catalogue-', str(self.backups / 'skip-catalogue-'))
        self.installer = self.workspace / 'installer.sh'
        self.installer.write_text(source)
        self.script('id', "print('0')")
        self.script('chown', 'pass')
        self.script('install', """
import shutil
from pathlib import Path
shutil.copyfile(sys.argv[-2],sys.argv[-1])
if os.environ.get('FIXTURE_MODE')=='bad-dashboard' and sys.argv[-1].endswith('check_skip_dashboard.py'):
    Path(os.environ['FIXTURE_APP'],'templates/skip_progress.html').unlink()
""")
        self.script('curl', """
import json, shutil
from pathlib import Path
args=sys.argv[1:]; output=Path(args[args.index('-o')+1]); url=next(x for x in args if x.startswith('http'))
mode=os.environ.get('FIXTURE_MODE','success')
if '127.0.0.1' in url:
    new='skip_nightly_catalogue' in Path(os.environ['FIXTURE_APP'],'skip_markers.py').read_text()
    if mode=='unavailable-health' and not new: raise SystemExit(22)
    healthy=new and mode!='bad-health'
    body={'api_version':'0.8.0' if mode=='old-api' else '0.8.2','status':'ok','features':{'skip_nightly_catalogue':healthy,'skip_high_audio_approval':healthy,'skip_proposal_dedup':healthy,'skip_online_error_details':healthy,'skip_language_priority':healthy,'skip_bulk_review':healthy and mode!='missing-bulk-review','skip_network_address_fallback':healthy and mode!='missing-network-fallback','skip_automatic_acceptance':healthy and mode!='missing-automatic-acceptance','skip_series_progress':healthy and mode!='missing-series-progress','skip_database_concurrency':healthy and mode!='missing-database-concurrency'}}
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
if args[0]=='stop' and 'epimediahub-skip-analysis.service' in args and state.get('worker_pid'):
    import signal
    try: os.kill(state['worker_pid'],signal.SIGTERM)
    except ProcessLookupError: pass
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

    def launch(self, mode='success', enable=True, wait_worker=False, repair=False):
        args = ['bash', str(self.installer)]
        if enable:
            args.append('--start-catalogue')
        if wait_worker:
            args.append('--wait-worker')
        if repair:
            args.append('--repair-database')
        result = subprocess.run(args, env=self.env | dict(FIXTURE_MODE=mode), text=True, capture_output=True, timeout=45)
        self.assertNotIn('not-read-or-executed', result.stdout + result.stderr)
        return result

    def test_optional_worker_wait_finishes_after_lock_release_and_restores_timer(self):
        logfile = self.workspace / 'waiting.log'
        with (self.datadir / 'skip-analysis.lock').open('a') as worker_lock:
            fcntl.flock(worker_lock, fcntl.LOCK_EX)
            with logfile.open('w') as log:
                process = subprocess.Popen(['bash', str(self.installer), '--wait-worker'], env=self.env,
                                           text=True, stdout=log, stderr=subprocess.STDOUT)
                try:
                    deadline = time.monotonic() + 15
                    while 'Analysedurchlauf warten' not in logfile.read_text() and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(.02)
                    self.assertIn('Analysedurchlauf warten', logfile.read_text())
                    self.assertIsNone(process.poll())
                    self.assertEqual(json.loads(self.state.read_text())['events'], [])
                    fcntl.flock(worker_lock, fcntl.LOCK_UN)
                    self.assertEqual(process.wait(timeout=30), 0, logfile.read_text())
                finally:
                    if process.poll() is None:
                        process.kill(); process.wait()
        self.assertTrue(json.loads(self.state.read_text())['timer'])

    def test_optional_worker_wait_timeout_preserves_code_timer_and_database(self):
        self.installer.write_text(self.installer.read_text().replace('lock_options=(-w 900)', 'lock_options=(-w 1)'))
        with (self.datadir / 'skip-analysis.lock').open('a') as worker_lock:
            fcntl.flock(worker_lock, fcntl.LOCK_EX)
            result = self.launch(wait_worker=True)
        self.assertNotEqual(result.returncode, 0)
        self.unchanged()
        self.assertTrue(json.loads(self.state.read_text())['timer'])
        self.assertEqual(json.loads(self.state.read_text())['events'], [])

    def test_success_prioritizes_existing_tagged_queue_and_schedules_category_refresh(self):
        from skip_catalogue import LANGUAGE_POLICY
        with self.db() as con:
            con.execute('INSERT INTO skip_catalogue_series VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (1, '501', json.dumps({'series_id': '501', 'name': '[IT] Lie to Me', 'year': '2009', 'release': ''}), 'signature', 0, 1, 1, 0, '', ''))
            con.execute('INSERT INTO skip_catalogue_episodes VALUES(?,?,?,?,?)', (1, '501', self.target['asset_key'], 'version', 1))
            con.execute('DELETE FROM skip_auto_maintenance WHERE name=?', (LANGUAGE_POLICY,))
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        with self.db() as con:
            self.assertEqual(con.execute('SELECT priority FROM skip_language_priority WHERE asset_key=?', (self.target['asset_key'],)).fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT checked_at FROM skip_catalogue_language_refresh WHERE playlist_id=1').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT status,attempts,detail FROM skip_jobs').fetchone()[:], ('no_reference', 2, 'previous'))

    def unchanged(self):
        for name, content in self.originals.items():
            self.assertEqual((self.appdir / name).read_text(), content)
        self.assertFalse((self.appdir / 'skip_automation.py').exists())
        self.assertFalse((self.appdir / 'skip_catalogue.py').exists())
        self.assertFalse((self.appdir / 'skip_release.py').exists())
        self.assertFalse((self.appdir / 'skip_progress.py').exists())
        self.assertFalse((self.appdir / 'skip_database.py').exists())
        self.assertFalse((self.appdir / 'deploy/check_skip_dashboard.py').exists())
        self.assertFalse((self.appdir / 'templates/skip_progress.html').exists())
        with self.db() as con:
            marker = con.execute('SELECT * FROM skip_records').fetchone()
            self.assertEqual((marker['status'],marker['start_ms'],marker['end_ms']), ('approved',283043,309573))

    def test_success_starts_only_enabled_automatic_sources_and_preserves_marker_and_key(self):
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        with self.db() as con:
            states = dict((r['playlist_id'],r['enabled']) for r in con.execute('SELECT * FROM skip_catalogue_settings'))
            self.assertEqual(states, {1:1})
            self.assertEqual(con.execute("SELECT value FROM skip_auto_metadata_config WHERE name='tmdb_api_key'").fetchone()[0], 'a'*32)
            self.assertEqual(con.execute("SELECT value FROM skip_catalogue_config WHERE name='daily_limit'").fetchone()[0],96)
            self.assertEqual(con.execute("SELECT phase,next_due FROM skip_catalogue_runs WHERE playlist_id=1").fetchone()[:],('idle',0))
            self.assertEqual(con.execute('SELECT status,start_ms,end_ms FROM skip_records').fetchone()[:], ('approved',283043,309573))
        self.assertEqual(len(list(self.backups.glob('*/provisioning.db'))), 1)
        self.assertTrue(json.loads(self.state.read_text())['timer'])

    def test_no_activation_preserves_inactive_timer_and_previous_settings(self):
        self.state.write_text(json.dumps({'timer':False,'events':[]}))
        result=self.launch(enable=False)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(json.loads(self.state.read_text())['timer'])
        with self.db() as con:
            self.assertEqual(con.execute('SELECT enabled,updated_at FROM skip_catalogue_settings WHERE playlist_id=1').fetchone()[:], (0,'previous-choice'))

    def test_success_consolidates_old_duplicates_and_requeues_high_scores_without_approving_them(self):
        from skip_markers import add_record
        from skip_automation import POLICY_VERSION
        with self.db() as con:
            for shift in (0,125,250,375):
                add_record(con,self.target,'intro',48000+shift,74530+shift,False,source='audio',confidence=.937)
            con.execute('DELETE FROM skip_auto_maintenance WHERE name=?',(POLICY_VERSION,))
            con.execute("UPDATE skip_jobs SET status='review'")
        result=self.launch()
        self.assertEqual(result.returncode,0,result.stderr)
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_records WHERE asset_key=? AND status='pending'",(self.target['asset_key'],)).fetchone()[0],1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_records WHERE asset_key=? AND status='superseded'",(self.target['asset_key'],)).fetchone()[0],3)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_records WHERE asset_key=? AND status='approved'",(self.target['asset_key'],)).fetchone()[0],0)
            self.assertEqual(con.execute('SELECT status FROM skip_jobs').fetchone()[0],'queued')

    def test_update_accepts_old_pending_markers_by_default_and_keeps_human_markers_and_budget(self):
        from skip_markers import add_record
        from skip_release import POLICY
        with self.db() as con:
            record=add_record(con,self.target,'intro',48000,74530,False,source='audio',confidence=.81)
            record_id=record['id']
            con.execute('DELETE FROM skip_release_settings')
            con.execute('DELETE FROM skip_auto_maintenance WHERE name=?',(POLICY,))
            con.execute('INSERT INTO skip_analysis_budget VALUES(?,50)',(__import__('skip_markers').now()[:10],))
        result=self.launch()
        self.assertEqual(result.returncode,0,result.stderr)
        with self.db() as con:
            self.assertEqual(con.execute('SELECT status FROM skip_records WHERE id=?',(record_id,)).fetchone()[0],'approved')
            self.assertEqual(con.execute("SELECT status,start_ms,end_ms FROM skip_records WHERE source='device'").fetchone()[:],('approved',283043,309573))
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0],50)

    def test_explicit_activation_starts_previously_inactive_timer(self):
        self.state.write_text(json.dumps({'timer':False,'events':[]}))
        result=self.launch()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(self.state.read_text())['timer'])

    def test_legacy_online_error_is_scheduled_without_resetting_audio_job(self):
        from skip_automation import LEGACY_ONLINE_ERROR
        with self.db() as con:
            con.execute('INSERT INTO skip_auto_online VALUES(?,?,?,?,?)',
                        (self.target['asset_key'],self.target['duration_ms'],'[]',LEGACY_ONLINE_ERROR,123))
        result=self.launch()
        self.assertEqual(result.returncode,0,result.stderr)
        with self.db() as con:
            self.assertEqual(con.execute('SELECT status,attempts,detail FROM skip_jobs').fetchone()[:],('no_reference',2,'previous'))
            self.assertEqual(con.execute('SELECT error_code,retry_at FROM skip_auto_online_retry').fetchone()[:],('legacy_error',0))
            self.assertIn('erneut geprüft',con.execute('SELECT detail FROM skip_auto_online').fetchone()[0])

    def test_bad_health_restores_code_settings_and_original_timer_without_losing_markers(self):
        result=self.launch('bad-health')
        self.assertNotEqual(result.returncode,0)
        self.unchanged()
        with self.db() as con:
            self.assertEqual(con.execute('SELECT enabled,updated_at FROM skip_catalogue_settings WHERE playlist_id=1').fetchone()[:], (0,'previous-choice'))
            self.assertIsNone(con.execute('SELECT * FROM skip_catalogue_settings WHERE playlist_id=2').fetchone())
            self.assertEqual(con.execute('SELECT status,attempts,detail FROM skip_jobs').fetchone()[:], ('no_reference',2,'previous'))
            self.assertFalse(con.execute('SELECT 1 FROM skip_catalogue_runs').fetchone())
            self.assertFalse(con.execute('SELECT 1 FROM skip_catalogue_config').fetchone())
            self.assertEqual(con.execute("SELECT value FROM skip_auto_metadata_config WHERE name='tmdb_api_key'").fetchone()[0],'a'*32)
        self.assertTrue(json.loads(self.state.read_text())['timer'])

    def test_missing_network_fallback_restores_code_and_preserves_markers(self):
        result = self.launch('missing-network-fallback', enable=False)
        self.assertNotEqual(result.returncode, 0)
        self.unchanged()
        self.assertTrue(json.loads(self.state.read_text())['timer'])

    def test_missing_automatic_acceptance_or_progress_rolls_back_all_new_files(self):
        for mode in ('missing-automatic-acceptance','missing-series-progress'):
            with self.subTest(mode=mode):
                result=self.launch(mode,enable=False)
                self.assertNotEqual(result.returncode,0)
                self.unchanged()
                self.assertTrue(json.loads(self.state.read_text())['timer'])

    def test_bad_health_preserves_previous_run_schedule_and_budget(self):
        with self.db() as con:
            con.execute("INSERT INTO skip_catalogue_config VALUES('daily_limit',24,'previous-choice')")
            con.execute("INSERT INTO skip_catalogue_runs(playlist_id,full_done,generation,next_due,retry_at) VALUES(1,1,7,999999,444444)")
        result=self.launch('bad-health')
        self.assertNotEqual(result.returncode,0)
        with self.db() as con:
            self.assertEqual(con.execute('SELECT generation,next_due,retry_at FROM skip_catalogue_runs').fetchone()[:],(7,999999,444444))
            self.assertEqual(con.execute('SELECT value,updated_at FROM skip_catalogue_config').fetchone()[:],(24,'previous-choice'))

    def test_missing_bulk_review_feature_rolls_back_and_preserves_markers(self):
        result = self.launch('missing-bulk-review', enable=False)
        self.assertNotEqual(result.returncode, 0)
        self.unchanged()
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

    def test_repair_works_when_health_is_blocked_and_preserves_existing_data(self):
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='running'")
            con.execute("INSERT INTO skip_analysis_budget VALUES(?,37)", (__import__('skip_markers').now()[:10],))
            con.execute("DROP INDEX idx_skip_catalogue_episode_asset")
        result = self.launch('unavailable-health', repair=True, enable=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('vorhandenem Datenbestand erfolgreich geladen', result.stdout)
        with self.db() as con:
            self.assertEqual(con.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            self.assertIsNotNone(con.execute("SELECT 1 FROM sqlite_master WHERE name='idx_skip_catalogue_episode_asset'").fetchone())
            self.assertEqual(con.execute('SELECT status,attempts FROM skip_jobs').fetchone()[:], ('queued',2))
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0], 37)
            self.assertEqual(con.execute('SELECT status,start_ms,end_ms FROM skip_records').fetchone()[:], ('approved',283043,309573))
            self.assertEqual(con.execute("SELECT value FROM skip_auto_metadata_config WHERE name='tmdb_api_key'").fetchone()[0], 'a'*32)
        self.assertTrue(json.loads(self.state.read_text())['timer'])

    def test_repair_stops_active_writer_before_taking_worker_lock(self):
        ready = self.workspace / 'worker-ready'
        code = """
import fcntl,sqlite3,sys,time
from pathlib import Path
with Path(sys.argv[1]).open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    con=sqlite3.connect(sys.argv[2]); con.execute('BEGIN EXCLUSIVE')
    Path(sys.argv[3]).write_text('ready')
    time.sleep(30)
"""
        worker = subprocess.Popen([sys.executable,'-c',code,str(self.datadir/'skip-analysis.lock'),str(self.db_path),str(ready)])
        try:
            deadline = time.monotonic()+5
            while not ready.exists() and time.monotonic()<deadline:
                time.sleep(.01)
            self.assertTrue(ready.exists())
            state=json.loads(self.state.read_text()); state['worker_pid']=worker.pid; self.state.write_text(json.dumps(state))
            result=self.launch('unavailable-health',repair=True,enable=False)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(worker.wait(timeout=3),-15)
            self.assertTrue(json.loads(self.state.read_text())['timer'])
        finally:
            if worker.poll() is None:
                worker.terminate(); worker.wait(timeout=3)

    def test_real_dashboard_failure_restores_code_even_if_health_would_pass(self):
        result=self.launch('bad-dashboard',repair=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Intro-Dashboard konnte',result.stderr)
        self.unchanged()
        self.assertTrue(json.loads(self.state.read_text())['timer'])

    def test_missing_database_feature_rolls_back_code_and_preserves_data(self):
        result=self.launch('missing-database-concurrency',repair=True)
        self.assertNotEqual(result.returncode,0)
        self.unchanged()
        self.assertTrue(json.loads(self.state.read_text())['timer'])

    def test_corrupt_repair_download_preserves_active_services(self):
        result=self.launch('corrupt',repair=True)
        self.assertNotEqual(result.returncode,0)
        self.unchanged()
        self.assertEqual(json.loads(self.state.read_text())['events'],[])

    def test_repair_restarts_services_when_worker_lock_cannot_be_released(self):
        with (self.datadir/'skip-analysis.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            result=self.launch(repair=True)
        self.assertNotEqual(result.returncode,0)
        self.unchanged()
        state=json.loads(self.state.read_text())
        self.assertTrue(state['timer'])
        self.assertIn(['restart','epimediahub-provisioning.service'],state['events'])


if __name__=='__main__':
    unittest.main()

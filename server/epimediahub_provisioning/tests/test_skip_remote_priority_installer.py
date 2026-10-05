"""Execute the Pi update with isolated services, real SQLite migration and rollback."""
import json
import sqlite3
import unittest

import test_skip_remote_installer as installer_fixtures
from test_skip_analysis_references import ReferenceFixture
from skip_analysis import register_asset
from skip_catalogue import set_asset_language
from skip_markers import now
ROOT=installer_fixtures.ROOT


class PriorityInstallerTests(unittest.TestCase):
    def setUp(self):
        self.fixture=installer_fixtures.InstallerTests('test_server_installs_private_api_unprivileged_service_and_protected_keys')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.references=ReferenceFixture()
        self.references.setUp()
        self.addCleanup(self.references.tearDown)
        self.greek=self.references.descriptor('81',12,title='[GR] Paused series')
        with self.references.db() as con:
            register_asset(con,self.greek,self.greek,self.references.device)
            set_asset_language(con,self.greek['asset_key'],2)
            con.execute("UPDATE skip_jobs SET status='running',attempts=2")
            con.execute('INSERT INTO skip_analysis_budget VALUES(?,50)',(now()[:10],))
        self.marker=self.references.marker(self.greek)
        with self.references.db() as source, sqlite3.connect(self.fixture.data/'provisioning.db') as target:
            source.backup(target)
        self.old_code=(self.fixture.base/'skip_analysis_worker.py').read_bytes()+b'\n# previous installation\n'
        (self.fixture.base/'skip_analysis_worker.py').write_bytes(self.old_code)
        (self.fixture.base/'templates').mkdir()
        (self.fixture.base/'templates/skip_schedule.html').write_text('previous template')
        # Private RPC is isolated here; unchanged protocol has actual HTTP/audio tests.
        (self.fixture.base/'skip_remote_client.py').write_text("def configured(): return True\ndef health(): return {'status':'ok','active':False}\n")
        self.fixture.script('curl','''
args=sys.argv[1:]; out=Path(args[args.index('-o')+1]); url=next(x for x in args if x.startswith('http'))
mode=os.environ.get('FIXTURE_MODE','success')
if '127.0.0.1:8787' in url:
    out.write_text(json.dumps({'status':'broken' if mode=='dashboard-failure' else 'ok',
                              'features':{'skip_interactive_priority':True}}))
else:
    name=url.rsplit('/',1)[-1]
    source=Path(os.environ['FIXTURE_ROOT'],'templates',name) if name.endswith('.html') else Path(os.environ['FIXTURE_SOURCE'],name)
    shutil.copyfile(source,out)
    if mode=='corrupt' and name=='skip_analysis_worker.py': out.write_text('invalid python @')
''')
        self.components={name:(self.fixture.base/name).read_bytes() for name in
          ('skip_analysis.py','skip_automation.py','skip_detector_v2.py','skip_detector_v3.py',
           'skip_remote_client.py','skip_remote_protocol.py')}

    def run_update(self,mode='success',ref='a'*40):
        return self.fixture.run_script('install_skip_interactive_priority.sh',ref,mode=mode)

    def assert_data_preserved(self):
        with sqlite3.connect(self.fixture.data/'provisioning.db') as con:
            self.assertEqual(con.execute('SELECT status,start_ms,end_ms FROM skip_records WHERE id=?',(self.marker,)).fetchone(),
                             ('approved',283043,309573))
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0],50)
            self.assertEqual(con.execute('SELECT attempts FROM skip_jobs').fetchone()[0],2)
        for name,data in self.components.items():
            self.assertEqual((self.fixture.base/name).read_bytes(),data,name)

    def test_update_pauses_old_job_and_keeps_markers_budget_protocol_and_service_state(self):
        result=self.run_update()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assert_data_preserved()
        with sqlite3.connect(self.fixture.data/'provisioning.db') as con:
            self.assertEqual(con.execute('SELECT status FROM skip_jobs').fetchone()[0],'queued')
        self.assertEqual((self.fixture.base/'skip_analysis_worker.py').read_bytes(),(ROOT/'skip_analysis_worker.py').read_bytes())
        self.assertTrue(list((self.fixture.base/'backups').glob('*/provisioning.db')))
        self.assertTrue(json.loads(self.fixture.state.read_text())['active'])

    def test_post_install_health_failure_restores_previous_code_and_resumes_timer(self):
        result=self.run_update('dashboard-failure')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((self.fixture.base/'skip_analysis_worker.py').read_bytes(),self.old_code)
        self.assertEqual((self.fixture.base/'templates/skip_schedule.html').read_text(),'previous template')
        self.assert_data_preserved()
        self.assertTrue(json.loads(self.fixture.state.read_text())['active'])

    def test_corrupt_download_is_rejected_before_stopping_services(self):
        result=self.run_update('corrupt')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(json.loads(self.fixture.state.read_text())['events'],[])
        self.assertEqual((self.fixture.base/'skip_analysis_worker.py').read_bytes(),self.old_code)
        self.assert_data_preserved()

    def test_unpinned_source_is_rejected_before_any_service_action(self):
        result=self.run_update(ref='raspberry-hetzner-analysis')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(json.loads(self.fixture.state.read_text())['events'],[])

    def test_previously_disabled_timer_is_not_activated_by_update(self):
        self.fixture.state.write_text(json.dumps({'active':False,'events':[]}))
        result=self.run_update()
        self.assertEqual(result.returncode,0,result.stderr)
        state=json.loads(self.fixture.state.read_text())
        self.assertFalse(state['active'])
        self.assertFalse(any(event[0]=='start' for event in state['events']))

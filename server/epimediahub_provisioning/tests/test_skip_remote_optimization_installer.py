"""Paired update ordering, failure recovery and preservation of live state."""
import json
import shutil
import sqlite3
import sys
import unittest
from pathlib import Path

import test_skip_remote_installer as installer_fixtures
from test_skip_analysis_references import ReferenceFixture

ROOT=installer_fixtures.ROOT
COMMIT='a'*40


class PairedInstallerTests(unittest.TestCase):
    script=installer_fixtures.InstallerTests.script
    run_script=installer_fixtures.InstallerTests.run_script

    def setUp(self):
        installer_fixtures.InstallerTests.setUp(self)
        fixture=ReferenceFixture()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        fixture.marker()
        with sqlite3.connect(fixture.db_path) as source,sqlite3.connect(self.data/'provisioning.db') as target:
            source.backup(target)
        with sqlite3.connect(self.data/'provisioning.db') as con:
            con.execute("ALTER TABLE customers ADD COLUMN name TEXT DEFAULT 'Customer'")
            con.execute("INSERT INTO skip_catalogue_config VALUES('daily_limit',500,'preserved')")
            con.execute("INSERT INTO skip_analysis_budget VALUES('2026-10-06',73)")
        for directory in ('templates','static','deploy'):
            for base in (self.source,self.base):
                (base/directory).mkdir()
            for file in (ROOT/directory).glob('*'):
                if file.is_file():
                    shutil.copyfile(file,self.source/directory/file.name)
                    shutil.copyfile(file,self.base/directory/file.name)
        # Real protocol/FFT/RPC coverage is separate. Isolate the two machines'
        # installation from actual network and systemd in this fixture.
        client='''import os
from contextlib import contextmanager
def configured():return True
def health():
    if os.environ.get('FIXTURE_MODE')=='unreachable':raise ValueError('analysis_deferred')
    return {'status':'ok','active':False}
def match(*_):return (2500,1.0)
@contextmanager
def local_execution():yield
'''
        for base in (self.source,self.base):
            (base/'skip_remote_client.py').write_text(client)
        (self.base/'skip_remote_role.json').write_text(json.dumps(dict(protocol=1,url='http://10.87.26.1:8790',provider_path='raspberry')))
        self.state.write_text(json.dumps(dict(active=True,progress=False,events=[])))
        self.script('systemctl','''
p=Path(os.environ['FIXTURE_STATE']);data=json.loads(p.read_text());args=sys.argv[1:]
unit=args[-1]
if args[0]=='is-active':
    raise SystemExit(0 if data['progress' if 'progress' in unit else 'active'] else 3)
data['events'].append(args)
key='progress' if 'progress' in unit else 'active'
if unit.endswith('.timer') and args[0] in ('stop','start','enable'):
    data[key]=args[0]!='stop'
p.write_text(json.dumps(data))
''')
        self.script('curl','''
args=sys.argv[1:];out=Path(args[args.index('-o')+1]);url=next(x for x in args if x.startswith('http'))
mode=os.environ.get('FIXTURE_MODE','success')
if '127.0.0.1:8787' in url:
    broken=mode=='dashboard-failure'
    out.write_text(json.dumps(dict(status='broken' if broken else 'ok',features={
        k:True for k in ('skip_dashboard_async','skip_progress_readonly','skip_detection_precision','skip_language_stages')})))
elif '10.87.26.1' in url:
    sys.path.insert(0,os.environ['EPIMEDIAHUB_WORKER_DIR'])
    from skip_remote_protocol import versions
    value=versions()
    if mode=='bad-health':value['skip_analysis.py']='bad'
    out.write_text(json.dumps(dict(status='ok',versions=value,detection_cache={})))
else:
    name=url.split('/server/epimediahub_provisioning/',1)[1]
    shutil.copyfile(Path(os.environ['FIXTURE_SOURCE'],name),out)
    if mode=='corrupt' and name=='skip_analysis.py':out.write_text('invalid python @')
''')

    def invoke(self,mode,fixture_mode='success'):
        return self.run_script('install_skip_optimization.sh',mode,COMMIT,mode=fixture_mode)

    def prepare(self):
        result=self.invoke('prepare')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return result

    def preserved(self):
        with sqlite3.connect(self.data/'provisioning.db') as con:
            self.assertEqual(con.execute('SELECT status,start_ms,end_ms FROM skip_records').fetchone(),('approved',283043,309573))
            self.assertEqual(con.execute("SELECT value FROM skip_catalogue_config WHERE name='daily_limit'").fetchone()[0],500)
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0],73)
        self.assertEqual(json.loads((self.base/'skip_remote_role.json').read_text())['provider_path'],'raspberry')

    def test_prepare_is_idempotent_and_does_not_replace_live_code_or_web_service(self):
        before=(self.base/'skip_analysis.py').read_bytes()
        self.prepare();self.prepare()
        self.assertEqual((self.base/'skip_analysis.py').read_bytes(),before)
        state=json.loads((self.base/f'optimization-stage-{COMMIT}/state.json').read_text())
        self.assertEqual(state['timer_active'],1)
        self.assertFalse(json.loads(self.state.read_text())['active'])
        self.assertFalse(any('epimediahub-provisioning.service' in x for x in json.loads(self.state.read_text())['events']))
        self.preserved()

    def test_control_preflight_failure_keeps_old_code_and_analysis_paused(self):
        self.prepare()
        file=self.base/'skip_analysis.py';original=file.read_bytes()+b'\n# previous version\n';file.write_bytes(original)
        result=self.invoke('control','unreachable')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(file.read_bytes(),original)
        self.assertFalse(json.loads(self.state.read_text())['active'])
        self.assertTrue((self.base/f'optimization-stage-{COMMIT}/state.json').exists())
        self.preserved()

    def test_control_installs_assets_measures_reads_and_resumes_the_existing_timer(self):
        self.prepare()
        result=self.invoke('control')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('network_time_included',result.stdout)
        self.assertTrue(json.loads(self.state.read_text())['active'])
        self.assertTrue(json.loads(self.state.read_text())['progress'])
        self.assertTrue((self.base/'static/skip_dashboard.js').is_file())
        self.assertIn(str(self.base),(self.units/'epimediahub-skip-progress.service').read_text())
        self.assertFalse((self.base/f'optimization-stage-{COMMIT}/state.json').exists())
        self.preserved()

    def test_control_preserves_a_previously_paused_analysis_timer(self):
        value=json.loads(self.state.read_text());value['active']=False;self.state.write_text(json.dumps(value))
        self.prepare()
        result=self.invoke('control')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertFalse(json.loads(self.state.read_text())['active'])
        self.preserved()

    def test_control_modified_stage_is_rejected_before_installing(self):
        self.prepare()
        before=(self.base/'skip_analysis.py').read_bytes()
        (self.base/f'optimization-stage-{COMMIT}/skip_analysis.py').write_text('# modified\n')
        result=self.invoke('control')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((self.base/'skip_analysis.py').read_bytes(),before)
        self.preserved()

    def test_control_failed_dashboard_restores_code_and_units_without_replacing_database(self):
        self.prepare()
        file=self.base/'skip_analysis.py';original=file.read_bytes()+b'\n# original\n';file.write_bytes(original)
        unit=self.units/'epimediahub-skip-progress.service';unit.write_text('original unit\n')
        result=self.invoke('control','dashboard-failure')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(file.read_bytes(),original)
        self.assertEqual(unit.read_text(),'original unit\n')
        self.assertFalse(json.loads(self.state.read_text())['active'])
        self.preserved()

    def test_compute_rejects_the_control_device(self):
        result=self.invoke('compute')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(json.loads(self.state.read_text())['events'],[])

    def test_compute_corrupt_download_does_not_stop_running_worker(self):
        (self.base/'skip_remote_role.json').unlink()
        file=self.base/'skip_analysis.py';original=file.read_bytes()
        result=self.invoke('compute','corrupt')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(file.read_bytes(),original)
        self.assertEqual(json.loads(self.state.read_text())['events'],[])

    def test_compute_health_version_mismatch_restores_previous_code(self):
        (self.base/'skip_remote_role.json').unlink()
        file=self.base/'skip_analysis.py';original=file.read_bytes()+b'\n# original\n';file.write_bytes(original)
        result=self.invoke('compute','bad-health')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(file.read_bytes(),original)
        self.assertIn(['restart','epimediahub-analysis-worker.service'],json.loads(self.state.read_text())['events'])

    def test_compute_verifies_updated_private_worker_versions(self):
        (self.base/'skip_remote_role.json').unlink()
        result=self.invoke('compute')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Jetzt auf dem Raspberry',result.stdout)


if __name__=='__main__':unittest.main()

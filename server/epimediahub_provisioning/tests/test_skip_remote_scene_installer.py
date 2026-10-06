"""EpiScene paired install and rollback without changing budgets, keys or units."""
import json
import sqlite3
import unittest
from pathlib import Path

import test_skip_remote_optimization_installer as fixtures

COMMIT=fixtures.COMMIT


class SceneInstallerTests(unittest.TestCase):
    script=fixtures.PairedInstallerTests.script
    run_script=fixtures.PairedInstallerTests.run_script
    preserved=fixtures.PairedInstallerTests.preserved

    def setUp(self):
        fixtures.PairedInstallerTests.setUp(self)
        for root in (self.base,self.source):
            path=root/'skip_remote_client.py'
            path.write_text(path.read_text()+'''\ndef visual_detect(target,partners,kind,busy=lambda:False):
    if os.environ.get('FIXTURE_MODE')=='visual-failure':raise ValueError('analysis_deferred')
    from skip_visual import detect
    return detect(target,partners,kind,busy)
''')
        self.script('curl','''
args=sys.argv[1:];out=Path(args[args.index('-o')+1]);url=next(x for x in args if x.startswith('http'))
mode=os.environ.get('FIXTURE_MODE','success')
if '127.0.0.1:8787' in url:
    broken=mode=='dashboard-failure'
    out.write_text(json.dumps(dict(status='broken' if broken else 'ok',features={
        k:True for k in ('skip_episcene','skip_dashboard_cached_statistics','skip_language_stages')})))
elif '10.87.26.1' in url:
    sys.path.insert(0,os.environ['EPIMEDIAHUB_WORKER_DIR'])
    from skip_remote_protocol import versions
    from skip_visual import POLICY
    value=versions()
    if mode=='bad-health':value['skip_visual.py']='bad'
    out.write_text(json.dumps(dict(status='ok',versions=value,episcene=dict(policy=POLICY))))
else:
    name=url.split('/server/epimediahub_provisioning/',1)[1]
    shutil.copyfile(Path(os.environ['FIXTURE_SOURCE'],name),out)
    if mode=='corrupt' and name=='skip_visual.py':out.write_text('invalid python @')
''')
        self.resource_unit='[Service]\nCPUQuota=37%\nMemoryMax=192M\nTimeoutStartSec=120\n'
        (self.units/'epimediahub-skip-progress.service').write_text(self.resource_unit)
        with sqlite3.connect(self.data/'provisioning.db') as con:
            con.execute("INSERT INTO skip_auto_settings VALUES(1,1,0,'kept')")

    def invoke(self,mode,fixture_mode='success'):
        return self.run_script('install_skip_scene.sh',mode,COMMIT,mode=fixture_mode)

    def prepare(self):
        result=self.invoke('prepare')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return result

    def test_prepare_is_idempotent_preserves_installed_code_and_keeps_dashboard_running(self):
        before=(self.base/'skip_visual.py').read_bytes()
        self.prepare();self.prepare()
        self.assertEqual((self.base/'skip_visual.py').read_bytes(),before)
        state=json.loads((self.base/f'episcene-stage-{COMMIT}/state.json').read_text())
        self.assertEqual(state['timer_active'],1)
        self.assertFalse(json.loads(self.state.read_text())['active'])
        self.assertFalse(any('epimediahub-provisioning.service' in x for x in json.loads(self.state.read_text())['events']))
        self.preserved()

    def test_corrupt_download_is_rejected_before_any_service_is_stopped(self):
        result=self.invoke('prepare','corrupt')
        self.assertNotEqual(result.returncode,0)
        self.assertTrue(json.loads(self.state.read_text())['active'])
        self.assertEqual(json.loads(self.state.read_text())['events'],[])
        self.preserved()

    def test_real_visual_preflight_is_required_before_changing_pi_code(self):
        self.prepare()
        path=self.base/'skip_visual.py';before=path.read_bytes()+b'\n# previous installed version\n';path.write_bytes(before)
        result=self.invoke('control','visual-failure')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(path.read_bytes(),before)
        self.assertTrue((self.base/f'episcene-stage-{COMMIT}/state.json').exists())
        self.assertFalse(json.loads(self.state.read_text())['active'])
        self.preserved()

    def test_success_enables_episcene_and_preserves_budget_markers_role_and_resource_units(self):
        self.prepare()
        result=self.invoke('control')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('EpiScene aktiv',result.stdout)
        with sqlite3.connect(self.data/'provisioning.db') as con:
            self.assertEqual(con.execute("SELECT value FROM skip_auto_metadata_config WHERE name='episcene_enabled'").fetchone()[0],'1')
        self.assertTrue(json.loads(self.state.read_text())['active'])
        self.assertFalse(json.loads(self.state.read_text())['progress'])
        self.assertEqual((self.units/'epimediahub-skip-progress.service').read_text(),self.resource_unit)
        self.assertFalse((self.base/f'episcene-stage-{COMMIT}/state.json').exists())
        self.preserved()

    def test_previously_paused_analysis_and_running_progress_timer_keep_their_states(self):
        state=json.loads(self.state.read_text());state.update(active=False,progress=True);self.state.write_text(json.dumps(state))
        self.prepare()
        result=self.invoke('control')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        state=json.loads(self.state.read_text())
        self.assertFalse(state['active']);self.assertTrue(state['progress'])
        self.preserved()

    def test_modified_stage_fails_without_installing(self):
        self.prepare()
        (self.base/f'episcene-stage-{COMMIT}'/'skip_visual.py').write_text('# changed')
        result=self.invoke('control')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((self.base/'skip_visual.py').read_bytes(),(self.source/'skip_visual.py').read_bytes())
        self.preserved()

    def test_failed_dashboard_health_restores_code_feature_switch_and_requeued_jobs(self):
        with sqlite3.connect(self.data/'provisioning.db') as con:
            con.execute("INSERT INTO skip_assets VALUES(?, ?,1,'91','mkv','episode',180000,1,1,'Serie','','previous')",('d'*64,'e'*64))
            con.execute("INSERT INTO skip_jobs(asset_key,status,attempts,detail,created_at,updated_at) VALUES(?,'no_match',7,'previous','previous','previous')",('d'*64,))
        self.prepare()
        path=self.base/'skip_visual.py';before=path.read_bytes()+b'\n# previous\n';path.write_bytes(before)
        result=self.invoke('control','dashboard-failure')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(path.read_bytes(),before)
        self.assertFalse(json.loads(self.state.read_text())['active'])
        with sqlite3.connect(self.data/'provisioning.db') as con:
            self.assertIsNone(con.execute("SELECT value FROM skip_auto_metadata_config WHERE name='episcene_enabled'").fetchone())
            self.assertEqual(con.execute("SELECT status,attempts,detail,updated_at FROM skip_jobs WHERE asset_key=?",('d'*64,)).fetchone(),('no_match',7,'previous','previous'))
        self.assertEqual((self.units/'epimediahub-skip-progress.service').read_text(),self.resource_unit)
        self.preserved()

    def test_compute_includes_all_shared_components_and_rolls_back_failed_health(self):
        (self.base/'skip_remote_role.json').unlink()
        file=self.base/'skip_visual.py';before=file.read_bytes()+b'\n# old compute\n';file.write_bytes(before)
        result=self.invoke('compute','bad-health')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(file.read_bytes(),before)
        result=self.invoke('compute')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(file.read_bytes(),(self.source/'skip_visual.py').read_bytes())
        self.assertTrue((self.base/'skip_release.py').exists())


if __name__=='__main__':unittest.main()

"""Pi-only dashboard update preserves the paired worker, quotas and live data."""
import json
import sqlite3
import unittest

import test_skip_remote_optimization_installer as fixtures


class DashboardInstallerTests(unittest.TestCase):
    script=fixtures.PairedInstallerTests.script
    run_script=fixtures.PairedInstallerTests.run_script
    preserved=fixtures.PairedInstallerTests.preserved

    def setUp(self):
        fixtures.PairedInstallerTests.setUp(self)
        self.unit=self.units/'epimediahub-skip-progress.service'
        self.unit.write_text('[Service]\nUser=epimediahub\nCPUQuota=35%\nMemoryMax=192M\nTimeoutStartSec=10\n')
        value=json.loads(self.state.read_text());value['progress']=True;self.state.write_text(json.dumps(value))
        self.script('curl','''
args=sys.argv[1:];out=Path(args[args.index('-o')+1]);url=next(x for x in args if x.startswith('http'))
mode=os.environ.get('FIXTURE_MODE','success')
if '127.0.0.1:8787' in url:
    out.write_text(json.dumps(dict(status='ok' if mode!='dashboard-failure' else 'broken',
        features={'skip_dashboard_cached_statistics':True})))
else:
    name=url.split('/server/epimediahub_provisioning/',1)[1]
    shutil.copyfile(Path(os.environ['FIXTURE_SOURCE'],name),out)
    if mode=='corrupt' and name=='skip_schedule.py':out.write_text('invalid python @')
''')

    def invoke(self,mode='success'):
        return self.run_script('install_skip_dashboard.sh',fixtures.COMMIT,mode=mode)

    def test_installs_indices_warms_statistics_and_measures_whole_page(self):
        role=(self.base/'skip_remote_role.json').read_bytes()
        result=self.invoke()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('schedule_ms',result.stdout)
        self.assertIn('catalogue_ms',result.stdout)
        self.assertEqual((self.base/'skip_remote_role.json').read_bytes(),role)
        self.assertIn('CPUQuota=35%',self.unit.read_text())
        self.assertIn('MemoryMax=192M',self.unit.read_text())
        self.assertIn('TimeoutStartSec=120',self.unit.read_text())
        with sqlite3.connect(self.data/'provisioning.db') as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_dashboard_stats').fetchone()[0],1)
            self.assertTrue(con.execute("SELECT 1 FROM sqlite_master WHERE name='idx_skip_online_recent'").fetchone())
        state=json.loads(self.state.read_text())
        self.assertTrue(state['active']);self.assertTrue(state['progress'])
        self.assertFalse(any('epimediahub-analysis-worker.service' in e for e in state['events']))
        self.preserved()

    def test_corrupt_download_leaves_services_and_code_untouched(self):
        before=(self.base/'skip_schedule.py').read_bytes()
        result=self.invoke('corrupt')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((self.base/'skip_schedule.py').read_bytes(),before)
        self.assertEqual(json.loads(self.state.read_text())['events'],[])
        self.preserved()

    def test_failed_health_restores_code_units_and_both_timer_states(self):
        file=self.base/'skip_schedule.py';before=file.read_bytes()+b'\n# previous installed code\n';file.write_bytes(before)
        unit=self.unit.read_bytes()
        result=self.invoke('dashboard-failure')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(file.read_bytes(),before)
        self.assertEqual(self.unit.read_bytes(),unit)
        state=json.loads(self.state.read_text())
        self.assertTrue(state['active']);self.assertTrue(state['progress'])
        self.preserved()

    def test_previously_paused_analysis_and_progress_timers_remain_paused(self):
        value=json.loads(self.state.read_text());value['active']=False;value['progress']=False;self.state.write_text(json.dumps(value))
        result=self.invoke()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        state=json.loads(self.state.read_text())
        self.assertFalse(state['active']);self.assertFalse(state['progress'])
        self.preserved()


if __name__=='__main__':unittest.main()

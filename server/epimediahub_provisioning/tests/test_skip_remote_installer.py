"""Installer roles, protected keys, delayed activation and rollback without database replacement."""
import base64
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
PRIVATE = base64.b64encode(bytes(range(32))).decode()
PUBLIC = base64.b64encode(bytes(range(32, 64))).decode()


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base, self.data, self.units, self.bin, self.wg, self.source = [self.root / name
            for name in ('app', 'data', 'units', 'bin', 'wireguard', 'source')]
        for path in (self.base / '.venv/bin', self.data, self.units, self.bin, self.wg, self.source):
            path.mkdir(parents=True, exist_ok=True)
        for source in ROOT.glob('*.py'):
            shutil.copyfile(source, self.base / source.name)
            shutil.copyfile(source, self.source / source.name)
        shutil.copyfile(ROOT / 'requirements.txt', self.source / 'requirements.txt')
        self.state = self.root / 'state.json'
        self.state.write_text(json.dumps({'active': True, 'events': []}))
        self.envfile = self.root / 'server.env'
        self.envfile.write_text(f'EPIMEDIAHUB_DATA_DIR="{self.data}"\n')
        with sqlite3.connect(self.data / 'provisioning.db') as con:
            con.executescript("CREATE TABLE preserved(value TEXT);INSERT INTO preserved VALUES('manual-marker');")
        self.script('id', "print('0')")
        self.script('apt-get', '')
        self.script('getent', "print('fixture-user')")
        self.script('ufw', "print('firewall configured')")
        # Hosted CI is unprivileged. Validate requested production ownership,
        # then let the real install utility check paths, copies and modes.
        self.script('install', '''
args=sys.argv[1:]; requested={}
for flag in ('-o','-g'):
    if flag in args:
        index=args.index(flag); requested[flag]=args[index+1]
        assert args[index+1]=='root', 'Installer must request root ownership'
        if os.geteuid()!=0: del args[index:index+2]
if requested:
    log=Path(os.environ['FIXTURE_OWNERSHIP'])
    with log.open('a') as stream: stream.write(json.dumps(requested)+'\\n')
os.execv(os.environ['FIXTURE_INSTALL'],[os.environ['FIXTURE_INSTALL']]+args)
''')
        self.script('systemctl', '''
p=Path(os.environ['FIXTURE_STATE']); data=json.loads(p.read_text()); args=sys.argv[1:]
if args[0]=='is-active': raise SystemExit(0 if data['active'] else 3)
data['events'].append(args)
if args[0]=='stop' and 'epimediahub-skip-analysis.timer' in args: data['active']=False
if args[0]=='start' and 'epimediahub-skip-analysis.timer' in args: data['active']=True
p.write_text(json.dumps(data))
''')
        self.script('wg', "print(os.environ['FIXTURE_PRIVATE'] if sys.argv[1]=='genkey' else os.environ['FIXTURE_PUBLIC'])")
        self.script('python3', '''
if sys.argv[1:3]==['-m','venv']: raise SystemExit(0)
os.execv(os.environ['FIXTURE_PYTHON'],[os.environ['FIXTURE_PYTHON']]+sys.argv[1:])
''')
        python = self.base / '.venv/bin/python'
        python.write_text('#!' + sys.executable + '\nimport os,sys\n'
            "if sys.argv[1:3]==['-m','pip']: raise SystemExit(0)\n"
            "os.execv(os.environ['FIXTURE_PYTHON'],[os.environ['FIXTURE_PYTHON']]+sys.argv[1:])\n")
        python.chmod(0o755)
        self.script('curl', '''
args=sys.argv[1:]; out=Path(args[args.index('-o')+1]); url=next(x for x in args if x.startswith('http'))
mode=os.environ.get('FIXTURE_MODE','success')
if '10.87.26.1' in url or '127.0.0.1:8787' in url:
    broken=mode=='bad-health' or (mode=='dashboard-failure' and '127.0.0.1' in url)
    out.write_text(json.dumps({'status':'broken' if broken else 'ok','features':{'skip_playlist_order':not broken,'skip_fingerprint_capture':not broken and mode!='missing-app-capture'}}))
else:
    name=url.rsplit('/',1)[-1]
    source=Path(os.environ['FIXTURE_SOURCE'],name)
    if name=='activate_skip_remote.sh': source=Path(os.environ['FIXTURE_ROOT'],'deploy',name)
    if name.endswith('.html'): source=Path(os.environ['FIXTURE_ROOT'],'templates',name)
    shutil.copyfile(source,out)
    if mode=='corrupt' and name=='skip_remote_worker.py': out.write_text('invalid python @')
''')
        self.env = os.environ | dict(EPIMEDIAHUB_APP_DIR=str(self.base), EPIMEDIAHUB_WORKER_DIR=str(self.base),
            EPIMEDIAHUB_SYSTEMD_DIR=str(self.units), EPIMEDIAHUB_WIREGUARD_DIR=str(self.wg),
            EPIMEDIAHUB_ADMIN_BIN_DIR=str(self.bin), EPIMEDIAHUB_ENV_FILE=str(self.envfile),
            FIXTURE_STATE=str(self.state), FIXTURE_SOURCE=str(self.source), FIXTURE_ROOT=str(ROOT),
            FIXTURE_INSTALL=shutil.which('install'), FIXTURE_OWNERSHIP=str(self.root / 'ownership.jsonl'),
            FIXTURE_PYTHON=sys.executable, FIXTURE_PRIVATE=PRIVATE, FIXTURE_PUBLIC=PUBLIC,
            PATH=str(self.bin) + os.pathsep + os.environ['PATH'])

    def script(self, name, code):
        path = self.bin / name
        path.write_text('#!' + sys.executable + '\nimport os,sys,json,shutil\nfrom pathlib import Path\n' + code)
        path.chmod(0o755)

    def run_script(self, name, *args, mode='success'):
        return subprocess.run(['bash', str(ROOT / 'deploy' / name), *args], text=True, capture_output=True,
                              env=self.env | {'FIXTURE_MODE': mode}, timeout=40)

    def preserve(self):
        with sqlite3.connect(self.data / 'provisioning.db') as con:
            self.assertEqual(con.execute('SELECT value FROM preserved').fetchone()[0], 'manual-marker')

    def staged_client(self):
        stage = self.base / 'remote-analysis-stage'; stage.mkdir()
        (stage/'templates').mkdir()
        for source in (ROOT/'templates').glob('skip_*.html'):
            shutil.copyfile(source,stage/'templates'/source.name)
        for source in ROOT.glob('*.py'):
            shutil.copyfile(source, stage / source.name)
        (stage / 'skip_remote_client.py').write_text('''
import os
def health():
    mode=os.environ['FIXTURE_MODE']
    if mode=='unreachable' or (mode=='post-install-failure' and 'remote-analysis-stage' not in __file__):
        raise ValueError('analysis_deferred')
    return {'status':'ok'}
def match(*_): return (2500,1.0)
''')
        (stage / 'skip_remote_verify.py').write_text('''
import os,sys
if os.environ['FIXTURE_MODE']=='provider-denied': raise SystemExit('provider_http_403')
''')
        return stage

    def test_server_installs_private_api_unprivileged_service_and_protected_keys(self):
        result = self.run_script('install_skip_hetzner.sh', '2.31.6.81')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(PRIVATE, result.stdout + result.stderr)
        self.assertIn(PUBLIC, result.stdout)
        conf = self.wg / 'wg-epi-analysis.conf'
        self.assertEqual(conf.stat().st_mode & 0o077, 0)
        self.assertIn('Address = 10.87.26.1/32', conf.read_text())
        unit = (self.units / 'epimediahub-analysis-worker.service').read_text()
        self.assertIn('User=epimediahub-worker', unit)
        self.assertIn('MemoryMax=3G', unit)
        self.assertNotIn('0.0.0.0', unit)
        self.assertTrue((self.bin / 'epimediahub-allow-raspberry').is_file())
        requests = [json.loads(line) for line in (self.root / 'ownership.jsonl').read_text().splitlines()]
        self.assertTrue(requests)
        self.assertTrue(all(item == {'-o': 'root', '-g': 'root'} for item in requests))
        self.preserve()

    def test_server_corrupt_download_keeps_existing_code_and_worker(self):
        path = self.base / 'skip_remote_worker.py'
        original = path.read_bytes() + b'\n# previously installed\n'; path.write_bytes(original)
        result = self.run_script('install_skip_hetzner.sh', '2.31.6.81', mode='corrupt')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(json.loads(self.state.read_text())['events'], [])

    def test_server_failed_health_restores_previous_code_and_unit(self):
        path = self.base / 'skip_remote_worker.py'
        original = path.read_bytes() + b'\n# previously installed\n'; path.write_bytes(original)
        unit = self.units / 'epimediahub-analysis-worker.service'; unit.write_text('previous unit\n')
        result = self.run_script('install_skip_hetzner.sh', '2.31.6.81', mode='bad-health')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(unit.read_text(), 'previous unit\n')
        self.preserve()

    def test_pi_preparation_preserves_local_code_and_routes_only_worker_address(self):
        original = (self.base / 'skip_analysis.py').read_bytes()
        result = self.run_script('install_skip_remote_client.sh', '2.31.6.81', PUBLIC)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.base / 'skip_analysis.py').read_bytes(), original)
        self.assertFalse(any(event[0]=='stop' for event in json.loads(self.state.read_text())['events']))
        conf = self.wg / 'wg-epi-analysis.conf'
        self.assertIn('AllowedIPs = 10.87.26.1/32', conf.read_text())
        self.assertNotIn('0.0.0.0/0', conf.read_text())
        self.assertEqual(conf.stat().st_mode & 0o077, 0)
        self.assertNotIn(PRIVATE, result.stdout + result.stderr)
        self.preserve()

    def test_pi_unreachable_worker_leaves_timer_and_code_untouched(self):
        self.staged_client()
        original = (self.base / 'skip_analysis.py').read_bytes()
        result = self.run_script('activate_skip_remote.sh', mode='unreachable')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.base / 'skip_analysis.py').read_bytes(), original)
        self.assertEqual(json.loads(self.state.read_text())['events'], [])
        self.preserve()

    def test_pi_code_refresh_preserves_the_paired_connection_and_keys(self):
        self.assertEqual(self.run_script('install_skip_remote_client.sh','2.31.6.81',PUBLIC).returncode,0)
        conf=self.wg/'wg-epi-analysis.conf'; key=self.wg/'epimediahub-analysis-client.key'
        original_conf,original_key=conf.read_bytes(),key.read_bytes()
        original_code=(self.base/'skip_analysis.py').read_bytes()
        before=json.loads(self.state.read_text())['events']
        result=self.run_script('install_skip_remote_client.sh','--refresh-code')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(conf.read_bytes(),original_conf)
        self.assertEqual(key.read_bytes(),original_key)
        self.assertEqual((self.base/'skip_analysis.py').read_bytes(),original_code)
        self.assertNotIn(PRIVATE,result.stdout+result.stderr)
        self.assertEqual(json.loads(self.state.read_text())['events'],before)
        self.assertIn('--provider-via-raspberry',result.stdout)
        self.preserve()

    def test_server_code_update_preserves_peer_and_prints_refresh_without_key_entry(self):
        self.assertEqual(self.run_script('install_skip_hetzner.sh','2.31.6.81').returncode,0)
        conf=self.wg/'wg-epi-analysis.conf';key=self.wg/'epimediahub-analysis-server.key'
        conf.write_text(conf.read_text()+'\n[Peer]\nPublicKey = '+PUBLIC+'\nAllowedIPs = 10.87.26.2/32\n')
        original_conf,original_key=conf.read_bytes(),key.read_bytes()
        result=self.run_script('install_skip_hetzner.sh','2.31.6.81')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(conf.read_bytes(),original_conf)
        self.assertEqual(key.read_bytes(),original_key)
        self.assertIn('--refresh-code',result.stdout)
        self.assertIn('--provider-via-raspberry',result.stdout)
        self.assertNotIn(PRIVATE,result.stdout+result.stderr)
        self.preserve()

    def test_gateway_activation_persists_the_path_and_opens_only_the_private_peer_port(self):
        stage=self.staged_client()
        (stage/'skip_remote_verify.py').write_text("import os\nprint('preflight_provider_path='+os.environ['SKIP_ANALYSIS_PROVIDER_PATH'])\n")
        self.script('ufw',"Path(os.environ['FIXTURE_STATE']).with_name('firewall.json').write_text(json.dumps(sys.argv[1:]))")
        result=self.run_script('activate_skip_remote.sh','--provider-via-raspberry')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('preflight_provider_path=raspberry',result.stdout)
        role=json.loads((self.base/'skip_remote_role.json').read_text())
        self.assertEqual(role['provider_path'],'raspberry')
        conf=(self.units/'epimediahub-skip-analysis.service.d/remote.conf').read_text()
        self.assertIn('Environment=SKIP_ANALYSIS_PROVIDER_PATH=raspberry',conf)
        firewall=json.loads(self.state.with_name('firewall.json').read_text())
        self.assertEqual(firewall,['allow','in','on','wg-epi-analysis','from','10.87.26.1',
                                   'to','10.87.26.2','port','8791','proto','tcp'])
        self.preserve()

    def test_gateway_failure_restores_the_previous_provider_path(self):
        self.staged_client()
        file=self.base/'skip_remote_role.json'
        original=json.dumps(dict(protocol=1,url='http://10.87.26.1:8790',provider_path='direct'))+'\n'
        file.write_text(original)
        result=self.run_script('activate_skip_remote.sh','--provider-via-raspberry',mode='post-install-failure')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(file.read_text(),original)
        self.assertTrue(json.loads(self.state.read_text())['active'])
        self.preserve()

    def test_pi_provider_denial_resumes_original_timer_before_installing_code(self):
        self.staged_client()
        original = (self.base / 'skip_analysis.py').read_bytes()
        result = self.run_script('activate_skip_remote.sh', mode='provider-denied')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.base / 'skip_analysis.py').read_bytes(), original)
        self.assertTrue(json.loads(self.state.read_text())['active'])
        self.assertFalse((self.units / 'epimediahub-skip-analysis.service.d/remote.conf').exists())
        self.preserve()

    def test_pi_final_failure_restores_old_code_and_preserves_database(self):
        self.staged_client()
        original = (self.base / 'skip_remote_client.py').read_bytes()
        result = self.run_script('activate_skip_remote.sh', mode='post-install-failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.base / 'skip_remote_client.py').read_bytes(), original)
        self.assertTrue(json.loads(self.state.read_text())['active'])
        self.preserve()

    def test_pi_success_changes_computation_environment_without_changing_budget_or_database(self):
        self.staged_client()
        result = self.run_script('activate_skip_remote.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        conf = (self.units / 'epimediahub-skip-analysis.service.d/remote.conf').read_text()
        self.assertIn('SKIP_ANALYSIS_REMOTE_URL=http://10.87.26.1:8790', conf)
        self.assertNotIn('CPUQuota', conf)
        self.assertNotIn('MemoryMax', conf)
        self.assertNotIn('daily', conf)
        self.assertIn('--max-jobs 8 --max-seconds 600',conf)
        timer=(self.units/'epimediahub-skip-analysis.timer.d/remote.conf').read_text()
        self.assertIn('OnUnitInactiveSec=\nOnUnitInactiveSec=5s',timer)
        self.assertIn('RandomizedDelaySec=5s',timer)
        self.assertIn('AccuracySec=1s',timer)
        self.assertEqual((self.base/'skip_schedule.py').read_bytes(),(ROOT/'skip_schedule.py').read_bytes())
        self.assertEqual((self.base/'templates/skip_schedule.html').read_bytes(),(ROOT/'templates/skip_schedule.html').read_bytes())
        self.assertEqual(json.loads((self.base / 'skip_remote_role.json').read_text())['url'],
                         'http://10.87.26.1:8790')
        self.assertTrue(json.loads(self.state.read_text())['active'])
        backups = list((self.base / 'backups').glob('*/provisioning.db'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].stat().st_mode & 0o077, 0)
        self.preserve()

    def test_missing_app_capture_capability_rolls_back_code_and_resumes_timer(self):
        self.staged_client()
        original=(self.base/'skip_app_capture.py').read_bytes()+b'\n# prior capture code\n'
        (self.base/'skip_app_capture.py').write_bytes(original)
        result=self.run_script('activate_skip_remote.sh',mode='missing-app-capture')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((self.base/'skip_app_capture.py').read_bytes(),original)
        self.assertTrue(json.loads(self.state.read_text())['active'])
        self.preserve()

    def test_dashboard_failure_restores_templates_timer_order_code_and_remote_role(self):
        self.staged_client()
        (self.base/'templates').mkdir()
        old_template=self.base/'templates/skip_markers.html';old_template.write_text('old dashboard')
        schedule_template=self.base/'templates/skip_schedule.html'
        timer=self.units/'epimediahub-skip-analysis.timer.d/remote.conf'
        timer.parent.mkdir();timer.write_text('[Timer]\nOnUnitInactiveSec=30s\n')
        previous_timer=timer.read_bytes()
        previous_schedule=(self.base/'skip_schedule.py').read_bytes()+b'\n# prior code\n'
        (self.base/'skip_schedule.py').write_bytes(previous_schedule)
        result=self.run_script('activate_skip_remote.sh',mode='dashboard-failure')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(old_template.read_text(),'old dashboard')
        self.assertFalse(schedule_template.exists())
        self.assertEqual(timer.read_bytes(),previous_timer)
        self.assertEqual((self.base/'skip_schedule.py').read_bytes(),previous_schedule)
        self.assertFalse((self.base/'skip_remote_role.json').exists())
        self.assertTrue(json.loads(self.state.read_text())['active'])
        self.preserve()


if __name__ == '__main__':
    unittest.main()

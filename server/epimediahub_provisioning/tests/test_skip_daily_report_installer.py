import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'deploy'))
from install_skip_daily_reports import FILES,prepare,read_data_dir,unit_files
from build_skip_daily_report_installer import build


class Installer(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        (self.base/'templates').mkdir()
        (self.base/'wsgi.py').write_text('existing_local_changes = True\ninstall_skip_markers(app, db)\n')
        (self.base/'templates/skip_markers.html').write_text('original brand\n{% include "skip_schedule.html" %}\ncustom local footer')
        self.files={name:{'content':(ROOT/name).read_text(),'sha256':hashlib.sha256((ROOT/name).read_bytes()).hexdigest()} for name in FILES}

    def tearDown(self):self.temp.cleanup()

    def test_preserves_live_changes_and_is_idempotent(self):
        result=prepare(self.base,self.files)
        self.assertIn(b'existing_local_changes',result['wsgi.py'])
        self.assertIn(b'custom local footer',result['templates/skip_markers.html'])
        for name,raw in result.items():
            path=self.base/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        self.assertEqual(result,prepare(self.base,self.files))
        self.assertFalse(set(result)&{'skip_analysis.py','skip_automation.py','skip_schedule.py','skip_scene.py'})

    def test_unrecognized_templates_refuse_without_writing(self):
        (self.base/'templates/skip_markers.html').write_text('different dashboard')
        before=(self.base/'wsgi.py').read_bytes()
        with self.assertRaises(RuntimeError):prepare(self.base,self.files)
        self.assertEqual(before,(self.base/'wsgi.py').read_bytes())
        self.assertFalse((self.base/'skip_daily_reports.py').exists())

    def test_corrupt_payload_refuses(self):
        self.files['skip_daily_reports.py']['content']+='changed'
        with self.assertRaises(RuntimeError):prepare(self.base,self.files)

    def test_data_directory_override_and_berlin_calendar(self):
        env=self.base/'service.env';env.write_text('EPIMEDIAHUB_DATA_DIR="/custom data"\nPASSWORD=not-used\n')
        self.assertEqual(read_data_dir(env,''),Path('/custom data'))
        self.assertEqual(read_data_dir(env,'"EPIMEDIAHUB_DATA_DIR=/override"'),Path('/override'))
        units=unit_files(self.base,Path('/override'),'epimediahub','epimediahub')
        self.assertIn(b'07:00:00 Europe/Berlin',units['epimediahub-episcene-report.timer'])
        self.assertIn(b'Persistent=true',units['epimediahub-episcene-report.timer'])
        self.assertNotIn(b'provisioning.env',units['epimediahub-episcene-report.service'])
        self.assertNotIn(b'PASSWORD',units['epimediahub-episcene-report.service'])

    def test_self_contained_installer_roundtrips_exact_source_and_shell_parses(self):
        out=self.base/'installer.sh';build(out)
        text=out.read_text()
        data=base64.b64decode(re.search(r'encoded="""(.*?)"""',text,re.S).group(1))
        package=json.loads(zlib.decompress(data))
        self.assertEqual(package['files'],self.files)
        self.assertEqual(package['installer'],(ROOT/'deploy/install_skip_daily_reports.py').read_text())
        subprocess.run(['bash','-n',str(out)],check=True)


if __name__=='__main__':unittest.main()

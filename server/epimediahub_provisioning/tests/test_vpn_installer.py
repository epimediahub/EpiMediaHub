import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("vpn_installer",ROOT/"deploy/install_vpn_dashboard.py")
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
agent_spec=importlib.util.spec_from_file_location("vpn_agent_installer",ROOT/"deploy/install_vpn_agent.py")
agent_installer=importlib.util.module_from_spec(agent_spec);agent_spec.loader.exec_module(agent_installer)



class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.base=self.root/"backend";self.base.mkdir()
        for source in ROOT.glob("*.py"):shutil.copy2(source,self.base/source.name)
        for name in ("templates","static"):shutil.copytree(ROOT/name,self.base/name)
        (self.base/"vpn_dashboard.py").unlink()
        wsgi=self.base/"wsgi.py"
        wsgi.write_text(wsgi.read_text().replace("\nfrom vpn_dashboard import install as install_vpn_dashboard\ninstall_vpn_dashboard(app, db)\n","\n")+"\n# Preserve local credit/daily-report additions\n")
        for name,url in (("dashboard_v080.html","/admin/vpn"),("reseller_dashboard_v080.html","/reseller/vpn")):
            path=self.base/"templates"/name
            path.write_text(path.read_text().replace(f'    <a class="button button-ghost" href="{url}">VPN Finnland</a>\n',""))
        self.old_wsgi=wsgi.read_text()
        self.old_admin=(self.base/"templates/dashboard_v080.html").read_text()
        self.data=self.root/"data";self.data.mkdir()
        self.env=os.environ.copy();self.env["EPIMEDIAHUB_DATA_DIR"]=str(self.data)
        self.envfile=self.root/"backend.env";self.envfile.write_text(f"EPIMEDIAHUB_DATA_DIR={self.data}\n")
        subprocess.run([sys.executable,"-c","import wsgi; from app import db;\nwith db() as c: c.execute(\"INSERT INTO customers(name,created_at) VALUES('Preserved customer','2026-10-09T00:00:00Z')\")"],cwd=self.base,env=self.env,check=True,capture_output=True)

    def test_finland_installer_accepts_a_nonseekable_tty(self):
        class NonSeekableTerminal(io.StringIO):
            def seekable(self):
                return False
            def seek(self, *args, **kwargs):
                raise io.UnsupportedOperation("File or stream is not seekable")
        for line, expected in (("\n", "https://api.epimediahub.com"),
                               ("https://vpn.example.org\n", "https://vpn.example.org")):
            with self.subTest(line=line):
                with patch("builtins.open", return_value=NonSeekableTerminal(line)) as opened:
                    with contextlib.redirect_stderr(io.StringIO()) as prompt:
                        self.assertEqual(agent_installer.read_dashboard_url(), expected)
                opened.assert_called_once_with("/dev/tty", "r", encoding="utf-8")
                self.assertIn("Dashboard-URL", prompt.getvalue())

    def test_finland_installer_requires_interactive_console(self):
        with patch("builtins.open", side_effect=OSError("No TTY")):
            with self.assertRaisesRegex(SystemExit, "interaktive Konsole"):
                agent_installer.read_dashboard_url()
        with patch("builtins.open", return_value=io.StringIO("")):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaisesRegex(SystemExit, "abgebrochen"):
                    agent_installer.read_dashboard_url()

    def test_staging_is_idempotent_and_uses_isolated_database(self):
        stage=self.root/"stage";stage.mkdir()
        installer.prepare(self.base,ROOT,stage)
        self.assertEqual((stage/"wsgi.py").read_text().count("install_vpn_dashboard(app, db)"),1)
        nav=(stage/"templates/dashboard_v080.html").read_text()
        self.assertEqual(installer.patch_navigation(nav,"/admin/vpn"),nav)
        installer.verify_stage(stage,self.env,self.data/"provisioning.db")
        with sqlite3.connect(self.data/"provisioning.db") as con:
            self.assertIsNone(con.execute("SELECT name FROM sqlite_master WHERE name='vpn_devices'").fetchone())
            self.assertEqual(con.execute("SELECT name FROM customers WHERE name='Preserved customer'").fetchone()[0],"Preserved customer")

    def test_failed_health_restores_code_without_reverting_customer_data(self):
        real_run=subprocess.run
        def run(args,**kwargs):
            if args[0]=="systemctl":return SimpleNamespace(returncode=0)
            return real_run(args,**kwargs)
        argv=["installer","--source",str(ROOT),"--base",str(self.base),"--env",str(self.envfile)]
        with patch.object(sys,"argv",argv),patch.object(installer.subprocess,"run",run),patch.object(installer,"health_check",side_effect=RuntimeError("health failed")),patch.object(installer.os,"geteuid",return_value=0),patch.object(installer.pwd,"getpwnam",return_value=SimpleNamespace(pw_uid=os.getuid(),pw_gid=os.getgid())),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(RuntimeError):installer.main()
        self.assertEqual((self.base/"wsgi.py").read_text(),self.old_wsgi)
        self.assertEqual((self.base/"templates/dashboard_v080.html").read_text(),self.old_admin)
        self.assertFalse((self.base/"vpn_dashboard.py").exists())
        with sqlite3.connect(self.data/"provisioning.db") as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM customers WHERE name='Preserved customer'").fetchone()[0],1)

    def test_unknown_navigation_stops_before_overwriting(self):
        with self.assertRaises(RuntimeError):installer.patch_navigation("<html>new custom layout</html>","/admin/vpn")


if __name__=="__main__":unittest.main()

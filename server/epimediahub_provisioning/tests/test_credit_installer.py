"""Exercise the real migration preflight and file rollback in disposable copies."""
import importlib.util
import os
from pathlib import Path
import pwd
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("credit_installer", ROOT / "deploy/install_credits_v120.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class CreditInstallerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="emh-installer-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "server"
        self.base.mkdir()
        for source in ROOT.glob("*.py"):
            shutil.copy2(source, self.base / source.name)
        for directory in ("templates", "static"):
            shutil.copytree(ROOT / directory, self.base / directory)
        wsgi = self.base / "wsgi.py"
        wsgi.write_text(wsgi.read_text().replace("import license_api  # Registers additive credit and license routes.\n", ""))
        for name in ("dashboard_v080.html", "reseller_dashboard_v080.html"):
            template = self.base / "templates" / name
            template.write_text("\n".join(line for line in template.read_text().splitlines() if "Credits & Lizenzen" not in line) + "\n<!-- existing custom footer -->\n")
        self.data = self.root / "data"
        self.data.mkdir()
        self.environment = dict(os.environ, EPIMEDIAHUB_DATA_DIR=str(self.data),
                                PYTHONPATH=str(self.base), EPIMEDIAHUB_SECRET_KEY="disposable-test-secret")
        subprocess.run([sys.executable, "-c", "import wsgi\nfrom app import db,iso,utcnow\nfrom werkzeug.security import generate_password_hash\nwith db() as con:\n n=iso(utcnow())\n con.execute(\"INSERT INTO resellers(name,username,password_hash,created_at,updated_at,customer_limit) VALUES('Existing reseller','existing',?,?,?,10)\",(generate_password_hash('ExistingPass-123'),n,n))\n con.execute(\"INSERT INTO customers(name,created_at,reseller_id) VALUES('Existing customer',?,1)\",(n,))"],
                       cwd=self.base, env=self.environment, check=True, capture_output=True)
        self.database = self.data / "provisioning.db"
        self.account = pwd.getpwuid(os.getuid())
        self.backup = self.root / "backup"
        self.backup.mkdir()

    def test_payload_and_preflight_preserve_real_legacy_accounts_and_templates(self):
        files = installer.patch_files(self.base, installer.payload())
        for name in installer.PAYLOAD_PATHS:
            self.assertEqual((ROOT / name).read_text(), files[name])
        for name in ("templates/dashboard_v080.html", "templates/reseller_dashboard_v080.html"):
            self.assertIn("existing custom footer", files[name])
        skip_before = (self.base / "skip_analysis_worker.py").read_bytes()
        for name, content in files.items():
            (self.base / name).write_text(content)
        installer.run_service_check(sys.executable, self.base, self.environment, self.account,
                                    self.backup / "preflight.log", snapshot=True)
        self.assertEqual(skip_before, (self.base / "skip_analysis_worker.py").read_bytes())
        self.assertEqual(files, installer.patch_files(self.base, installer.payload()))
        with sqlite3.connect(self.database) as con:
            self.assertEqual((1, "existing", None), con.execute("SELECT id,username,credit_price_cents FROM resellers").fetchone())
            self.assertEqual(1, con.execute("SELECT reseller_id FROM customers WHERE name='Existing customer'").fetchone()[0])

    def test_unknown_navigation_aborts_before_writing_installed_files(self):
        original = (self.base / "wsgi.py").read_bytes()
        (self.base / "templates/dashboard_v080.html").write_text("<html>Other version</html>")
        with self.assertRaisesRegex(RuntimeError, "Navigationsanker"):
            installer.patch_files(self.base, installer.payload())
        self.assertEqual(original, (self.base / "wsgi.py").read_bytes())

    def test_backup_reads_committed_wal_data_without_copying_partial_transactions(self):
        with sqlite3.connect(self.database) as writer:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("INSERT INTO customers(name,created_at) VALUES('Committed','now')")
            writer.commit()
            writer.execute("INSERT INTO customers(name,created_at) VALUES('Uncommitted','now')")
            destination = self.backup / "snapshot.db"
            installer.snapshot_db(self.database, destination)
            writer.rollback()
        with sqlite3.connect(destination) as snapshot:
            self.assertEqual(1, snapshot.execute("SELECT COUNT(*) FROM customers WHERE name='Committed'").fetchone()[0])
            self.assertEqual(0, snapshot.execute("SELECT COUNT(*) FROM customers WHERE name='Uncommitted'").fetchone()[0])

    def test_failed_restart_restores_files_but_preserves_database_updates(self):
        files = {"wsgi.py": "# upgraded\n", "new_module.py": "# new\n"}
        old = (self.base / "wsgi.py").read_bytes()
        saved = self.backup / "files"
        saved.mkdir()
        shutil.copy2(self.base / "wsgi.py", saved / "wsgi.py")

        def migration(*args, **kwargs):
            with sqlite3.connect(self.database) as con:
                con.execute("CREATE TABLE additive_license_test(id INTEGER)")
                con.execute("INSERT INTO customers(name,created_at) VALUES('Concurrent update','now')")

        with patch.object(installer, "BASE", self.base), patch.object(installer, "systemctl") as service, \
             patch.object(installer, "run_service_check", side_effect=migration), \
             patch.object(installer, "wait_healthy", side_effect=RuntimeError("failed restart")):
            with self.assertRaisesRegex(RuntimeError, "failed restart"):
                installer.apply_update(files, self.backup, ["wsgi.py"], self.database,
                                       sys.executable, self.environment, self.account, {})
        self.assertEqual(old, (self.base / "wsgi.py").read_bytes())
        self.assertFalse((self.base / "new_module.py").exists())
        self.assertEqual(("start", installer.SERVICE), service.call_args.args)
        with sqlite3.connect(self.database) as con:
            self.assertEqual(1, con.execute("SELECT COUNT(*) FROM customers WHERE name='Concurrent update'").fetchone()[0])
            self.assertIsNotNone(con.execute("SELECT name FROM sqlite_master WHERE name='additive_license_test'").fetchone())


if __name__ == "__main__":
    unittest.main()

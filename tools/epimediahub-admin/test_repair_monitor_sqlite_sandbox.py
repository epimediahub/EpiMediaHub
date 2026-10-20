"""Security regression tests for the narrow EpiMediaHub monitor SQLite repair."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import deploy_admin_all as admin
import repair_monitor_sqlite_sandbox as fix

class MonitorSandboxTests(unittest.TestCase):
    def test_template_keeps_database_readonly_and_updater_constrained(self):
        data=Path("/var/lib/epimediahub")
        creds=data/"admin-mobile/firebase-fcm-service-account.json"
        monitor=admin.service_unit(admin.MONITOR,"epimediahub",data,creds)
        updater=admin.service_unit(admin.UPDATES,"epimediahub",data,creds)
        self.assertIn("ProtectSystem=strict",monitor)
        self.assertIn("ReadWritePaths=/var/lib/epimediahub\n",monitor)
        self.assertIn("ReadOnlyPaths=/var/lib/epimediahub/provisioning.db\n",monitor)
        self.assertIn("ReadWritePaths=/var/lib/epimediahub/admin-mobile\n",updater)
        self.assertNotIn("ReadWritePaths=/var/lib/epimediahub\n",updater)

    def test_repair_rejects_customized_unit(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            d=root/"private"
            d.mkdir()
            monitor=root/"epimediahub-admin-monitor.service"
            updater=root/"epimediahub-admin-update-sync.service"
            monitor.write_text("UNEXPECTED_OVERRIDE")
            updater.write_text("unchanged")
            expected={monitor:"new",updater:"unchanged"}
            with mock.patch.object(admin,"validate",return_value=(d,"epimediahub","",None,None)):
                with mock.patch.object(admin,"files",return_value=expected):
                    with mock.patch.object(admin,"UNIT_DIR",root):
                        with self.assertRaisesRegex(RuntimeError,"ADMIN_MONITOR_UNIT_UNRECOGNIZED"):
                            fix.checked_units()

if __name__=="__main__":
    unittest.main()

"""Unit-only daily scheduler safety invariants; never touches real systemd."""
import os
from unittest import mock
import unittest
from pathlib import Path
from install_daily_xtream_http import unit_text,timer_text,check,InstallRefused


class DailyXtreamInstallerTests(unittest.TestCase):
    def test_systemd_unit_is_nonroot_private_and_one_shot(self):
        unit=unit_text("epimediahub")
        self.assertIn("User=epimediahub",unit)
        self.assertIn("ExecStart=/opt/epimediahub/provisioning/.venv/bin/python",unit)
        self.assertIn("expiry_http_worker.py --once",unit)
        self.assertIn("EPIMEDIAHUB_XTREAM_DAILY_HTTP_APPROVED=YES",unit)
        self.assertIn("ProtectSystem=strict",unit)
        self.assertIn("NoNewPrivileges=true",unit)
        self.assertIn("UMask=0077",unit)
        self.assertNotIn("password",unit.lower())

    def test_one_run_per_day_berlin_and_not_installed_just_by_import(self):
        timer=timer_text()
        self.assertIn("OnCalendar=*-*-* 06:15:00 Europe/Berlin",timer)
        self.assertIn("Persistent=false",timer)
        self.assertIn("Unit=epimediahub-xtream-expiry.service",timer)
        self.assertNotIn("OnUnitActiveSec",timer)

    def test_invalid_systemd_username_rejected(self):
        for value in ("", "root; rm -rf /", "someone\nExecStart=/bin/sh", "first last"):
            with self.subTest(value=value),self.assertRaises(InstallRefused):
                unit_text(value)

    def test_nonroot_preflight_refuses_without_writes(self):
        with mock.patch("install_daily_xtream_http.os.geteuid",return_value=1000),\
             mock.patch("install_daily_xtream_http.command") as cmd:
            with self.assertRaises(InstallRefused):
                check()
            cmd.assert_not_called()


if __name__=="__main__":
    unittest.main()

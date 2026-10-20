"""Authenticated expiry report tests using synthetic provider observations.

Never contacts IPTV providers or uses actual subscriber data.
"""
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

from flask import Flask
import mobile_flask
from expiry_cache import save_verified, read_verified
from expiry_report_rows import VerifiedPlaylistExpiry


class PrivateExpiryReportsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.db=self.root/"provisioning.db"
        with sqlite3.connect(self.db) as conn:
            conn.executescript("""
                CREATE TABLE customers (id INTEGER PRIMARY KEY,name TEXT,
                    enabled INTEGER,reseller_id INTEGER);
                CREATE TABLE customer_playlists (id INTEGER PRIMARY KEY,
                    customer_id INTEGER,name TEXT,enabled INTEGER,
                    config_json TEXT);
                INSERT INTO customers VALUES (1,'Beispielkunde A',1,NULL);
                INSERT INTO customers VALUES (2,'Beispielkunde B',1,77);
                INSERT INTO customer_playlists VALUES (
                    9,1,'THE BEST',1,'{"type":"XTREAM","xtream_password":"PRIVATE_PROVIDER_SECRETS"}');
                INSERT INTO customer_playlists VALUES (
                    10,1,'4K IPTV',1,'{"type":"XTREAM","xtream_password":"PRIVATE_PASSWORD"}');
                INSERT INTO customer_playlists VALUES (
                    11,2,'THE BEST',1,'{"type":"XTREAM","xtream_password":"OTHER_CUSTOMER_PRIVATE"}');
            """)
        self.app=Flask("test-only-expiry-report")
        self.app.secret_key="synthetic-no-production"
        mobile_flask.install(self.app)
        self.client=self.app.test_client()
        self.patch=mock.patch.object(mobile_flask,"_base",return_value=self.root)
        self.patch.start()
        self.coverage=mock.patch.dict("os.environ",{
            "EPIMEDIAHUB_EXPIRY_PROVIDER_COVERAGE_CERTIFIED":"YES"})
        self.coverage.start()
        self.now=datetime.now(timezone.utc)
        self.cache=self.root/"admin-mobile"/"expiry-cache.sqlite3"

    def tearDown(self):
        self.coverage.stop()
        self.patch.stop()
        self.temp.cleanup()

    def seed(self):
        obs=[
            VerifiedPlaylistExpiry(9,date(2026,11,18),self.now),
            VerifiedPlaylistExpiry(10,date(2026,11,4),self.now),
            VerifiedPlaylistExpiry(11,date(2026,11,8),self.now)
        ]
        save_verified(self.cache,obs)

    def login(self):
        with self.client.session_transaction() as session:
            session["admin"]=True

    def test_cache_never_exposes_credentials_and_monotone_observation(self):
        self.seed()
        loaded=read_verified(self.cache)
        self.assertEqual(len(loaded),3)
        self.assertNotIn("PRIVATE_PROVIDER_SECRETS",repr(loaded))
        newer=VerifiedPlaylistExpiry(9,date(2026,11,19),self.now+timedelta(minutes=1))
        older=VerifiedPlaylistExpiry(9,date(2026,11,10),self.now-timedelta(minutes=1))
        save_verified(self.cache,[newer])
        save_verified(self.cache,[older])
        self.assertEqual(read_verified(self.cache)[0].expires_on,date(2026,11,19))

    def test_unauthenticated_reports_never_expose_names(self):
        self.seed()
        for endpoint in (
            "/admin/mobile/reports/expiry/month?year=2026&month=11",
            "/admin/mobile/reports/expiry/week?from=2026-11-02",
            "/admin/mobile/reports/expiry/month.pdf?year=2026&month=11"
        ):
            with self.subTest(endpoint=endpoint):
                reply=self.client.get(endpoint)
                self.assertEqual(reply.status_code,401)
                self.assertNotIn(b"Beispielkunde",reply.data)

    def test_monthly_grouping_and_pdf_protected(self):
        self.seed()
        self.login()
        report=self.client.get(
            "/admin/mobile/reports/expiry/month?year=2026&month=11")
        self.assertEqual(report.status_code,200)
        data=report.get_json()
        self.assertEqual(data["count"],3)
        self.assertEqual([x["name"] for x in data["playlists"]],["4K IPTV","THE BEST"])
        self.assertEqual(data["playlists"][1]["entries"][0]["customer"],"Beispielkunde B")
        self.assertEqual(data["playlists"][1]["entries"][1]["expires_on"],"2026-11-18")
        self.assertEqual(report.headers["Cache-Control"],"private, no-store")
        self.assertNotIn("PRIVATE_PROVIDER",report.get_data(as_text=True))
        pdf=self.client.get(
            "/admin/mobile/reports/expiry/month.pdf?year=2026&month=11")
        self.assertEqual(pdf.status_code,200)
        self.assertEqual(pdf.headers["Cache-Control"],"private, no-store")
        self.assertTrue(pdf.data.startswith(b"%PDF"))
        self.assertIn("attachment",pdf.headers["Content-Disposition"])

    def test_uncertified_provider_coverage_cannot_generate_partial_report(self):
        self.seed()
        self.login()
        with mock.patch.dict("os.environ",{
            "EPIMEDIAHUB_EXPIRY_PROVIDER_COVERAGE_CERTIFIED":"NO"}):
            report=self.client.get(
                "/admin/mobile/reports/expiry/month?year=2026&month=11")
            self.assertEqual(report.status_code,503)
            self.assertNotIn("Beispielkunde",report.get_data(as_text=True))
            pdf=self.client.get(
                "/admin/mobile/reports/expiry/month.pdf?year=2026&month=11")
            self.assertEqual(pdf.status_code,503)

    def test_one_missing_xtream_account_blocks_every_report(self):
        self.seed()
        with sqlite3.connect(self.cache) as db:
            db.execute("DELETE FROM verified_xtream_expiry WHERE playlist_id=11")
        self.login()
        for endpoint in (
            "/admin/mobile/reports/expiry/month?year=2026&month=11",
            "/admin/mobile/reports/expiry/month.pdf?year=2026&month=11",
            "/admin/mobile/reports/expiry/week?from=2026-11-02",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.client.get(endpoint).status_code,503)

    def test_one_stale_xtream_account_blocks_reports(self):
        self.seed()
        with sqlite3.connect(self.cache) as db:
            db.execute("UPDATE verified_xtream_expiry SET observed_epoch=? "
                       "WHERE playlist_id=11",
                       (int((self.now-timedelta(days=4)).timestamp()),))
        self.login()
        self.assertEqual(self.client.get(
            "/admin/mobile/reports/expiry/month?year=2026&month=11"
        ).status_code,503)

    def test_unknown_provider_type_fails_closed(self):
        self.seed()
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE customer_playlists SET config_json=? WHERE id=11",
                       ('{"type":"UNRECOGNIZED"}',))
        self.login()
        self.assertEqual(self.client.get(
            "/admin/mobile/reports/expiry/month?year=2026&month=11"
        ).status_code,503)

    def test_week_dates_and_fail_closed_on_missing_provider_cache(self):
        self.login()
        missing=self.client.get(
            "/admin/mobile/reports/expiry/month?year=2026&month=11")
        self.assertEqual(missing.status_code,503)
        self.seed()
        week=self.client.get(
            "/admin/mobile/reports/expiry/week?from=2026-11-02")
        self.assertEqual(week.status_code,200)
        self.assertEqual(week.get_json()["count"],2)
        self.assertEqual(week.get_json()["week_end"],"2026-11-08")
        invalid=self.client.get(
            "/admin/mobile/reports/expiry/week?from=2026-11-03")
        self.assertEqual(invalid.status_code,400)
        invalid_month=self.client.get(
            "/admin/mobile/reports/expiry/month.pdf?year=2026&month=0")
        self.assertEqual(invalid_month.status_code,400)


if __name__=="__main__":
    unittest.main()

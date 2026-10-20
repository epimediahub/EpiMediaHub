"""Synthetic provider responses only; never touch live IPTV accounts."""
from datetime import date, datetime, timezone
import unittest
from expiry_provider_adapter import xtream_expiry, verified_calendar_date


class ExpiryProviderAdapterTests(unittest.TestCase):
    def test_utc_to_berlin_date_rollover(self):
        stamp=int(datetime(2026,10,31,23,30,tzinfo=timezone.utc).timestamp())
        result=xtream_expiry({"user_info":{"exp_date":str(stamp)}})
        self.assertEqual(result.expires_on,date(2026,11,1))
        self.assertEqual(result.status,"confirmed")
        self.assertEqual(result.source,"xtream_user_info")

    def test_dst_boundary(self):
        stamp=int(datetime(2026,3,29,22,30,tzinfo=timezone.utc).timestamp())
        result=xtream_expiry({"user_info":{"exp_date":stamp}})
        self.assertEqual(result.expires_on,date(2026,3,30))

    def test_unknown_unlimited_or_invalid_never_appears_as_expiration(self):
        cases=[
            None,{}, {"user_info":{}},{"user_info":{"exp_date":"0"}},
            {"user_info":{"exp_date":0}},
            {"user_info":{"exp_date":""}},
            {"user_info":{"exp_date":"never"}},
            {"user_info":{"exp_date":"1723456789000"}},
            {"user_info":{"exp_date":-1}},
            {"user_info":{"exp_date":True}},
            {"user_info":{"exp_date":1}},
            {"user_info":{"exp_date":"1723456789\n"}},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertIsNone(xtream_expiry(payload).expires_on)

    def test_verified_expiry_calendar_date(self):
        self.assertEqual(verified_calendar_date("2026-11-07").expires_on,
                         date(2026,11,7))
        for raw in ("07.11.2026","2026-02-30","2026-1-1","",None):
            with self.subTest(raw=raw):
                self.assertIsNone(verified_calendar_date(raw).expires_on)


if __name__=="__main__":
    unittest.main()

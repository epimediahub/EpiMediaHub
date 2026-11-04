"""Safety tests for the focused manual review report."""
import sqlite3
import unittest

from fingerprint_review_report_v4 import review_label, fmt, safe_title


class ReviewReportTests(unittest.TestCase):
    def test_stable_opaque_labels(self):
        a=review_label("provider-source-series-37")
        self.assertEqual(a,review_label("provider-source-series-37"))
        self.assertEqual(len(a),10)
        self.assertNotEqual(a,review_label("provider-source-series-38"))
        self.assertNotIn("provider",a)

    def test_time_format(self):
        self.assertEqual(fmt(96_000),"01:36")
        self.assertEqual(fmt(0),"00:00")
        self.assertEqual(fmt(-4),"?")

    def test_unsafe_url_metadata_never_displayed(self):
        con=sqlite3.connect(":memory:")
        con.execute("CREATE TABLE skip_assets(asset_key TEXT,title TEXT)")
        con.execute("INSERT INTO skip_assets VALUES(?,?)",
                    ("asset1","https://provider/private?t=abc"))
        self.assertIsNone(safe_title(con,"asset1",{"title"}))
        con.execute("UPDATE skip_assets SET title=? WHERE asset_key=?",
                    ("Breaking Bad","asset1"))
        self.assertEqual(safe_title(con,"asset1",{"title"}),"Breaking Bad")
        con.close()

    def test_missing_title_column_is_acceptable(self):
        con=sqlite3.connect(":memory:")
        con.execute("CREATE TABLE skip_assets(asset_key TEXT)")
        con.execute("INSERT INTO skip_assets VALUES(?)",("asset1",))
        self.assertIsNone(safe_title(con,"asset1",{"asset_key"}))
        con.close()

if __name__=="__main__":
    unittest.main()

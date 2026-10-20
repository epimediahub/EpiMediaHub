"""No customer production data is used in PDF layout tests."""
from datetime import date
from pathlib import Path
import tempfile
import unittest
from expiry_report_pdf import Expiry, monthly_pdf


class PrintableExpiryTests(unittest.TestCase):
    def test_groups_sort_pages_and_no_real_data(self):
        rows=[
            Expiry("Beispiel B","Playlist Zwei",date(2026,11,22)),
            Expiry("Beispiel C","Playlist Eins",date(2026,11,9)),
            Expiry("Beispiel A","Playlist Zwei",date(2026,11,2)),
            Expiry("Ignored","Playlist Zwei",date(2026,12,1)),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"report.pdf"
            result=monthly_pdf(rows,2026,11,target)
            self.assertTrue(target.read_bytes().startswith(b"%PDF-"))
            self.assertLess(target.stat().st_size,1_000_000)
            self.assertEqual(result["entries"],3)
            self.assertEqual(result["playlists"],2)
            self.assertEqual(result["pages"],2)
            self.assertEqual(result["month"],"2026-11")

    def test_large_playlist_continues_without_other_playlist(self):
        rows=[Expiry(f"Muster {i}","Serie A",date(2026,11,(i%28)+1))
              for i in range(45)]
        rows.append(Expiry("Andere","Serie B",date(2026,11,1)))
        with tempfile.TemporaryDirectory() as tmp:
            report=monthly_pdf(rows,2026,11,Path(tmp)/"big.pdf")
            self.assertEqual(report["entries"],46)
            self.assertEqual(report["playlists"],2)
            self.assertGreater(report["pages"],2)

    def test_no_expiry_does_not_infer_from_unrelated_license(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"empty.pdf"
            result=monthly_pdf([],2026,11,target)
            self.assertEqual(result["entries"],0)
            self.assertEqual(result["pages"],1)
            self.assertTrue(target.read_bytes().startswith(b"%PDF-"))

    def test_invalid_dates_and_names_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"invalid.pdf"
            with self.assertRaises(ValueError):
                monthly_pdf([],2026,13,target)
            for row in (Expiry("", "Playlist", date(2026,11,1)),
                        Expiry("Customer","",date(2026,11,1)),
                        Expiry("Customer\nOther","Playlist",date(2026,11,1))):
                with self.assertRaises(ValueError):
                    monthly_pdf([row],2026,11,target)


if __name__ == "__main__":
    unittest.main()

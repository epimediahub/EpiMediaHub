"""Fixture-only calendar boundaries; never use private customers."""
from datetime import date
import unittest
from expiry_report_pdf import Expiry
from expiry_report_calendar import (
    upcoming_month_on_last_day,calendar_week_on_monday,weekly_entries
)


class ExpiryCalendarTests(unittest.TestCase):
    def test_month_ends_include_short_months_and_december(self):
        self.assertEqual(upcoming_month_on_last_day(date(2026,2,28)),(2026,3))
        self.assertEqual(upcoming_month_on_last_day(date(2028,2,29)),(2028,3))
        self.assertIsNone(upcoming_month_on_last_day(date(2028,2,28)))
        self.assertEqual(upcoming_month_on_last_day(date(2026,4,30)),(2026,5))
        self.assertEqual(upcoming_month_on_last_day(date(2026,12,31)),(2027,1))
        self.assertIsNone(upcoming_month_on_last_day(date(2026,10,30)))

    def test_monday_to_sunday_cross_year_boundary(self):
        begin=date(2026,12,28)
        self.assertEqual(calendar_week_on_monday(begin),
                         (date(2026,12,28),date(2027,1,3)))
        self.assertIsNone(calendar_week_on_monday(date(2026,12,29)))

    def test_playlist_groups_and_sorted_expiry(self):
        monday=date(2026,11,2)
        rows=[
            Expiry("Zwei","The Best",date(2026,11,8)),
            Expiry("Eins","The Best",date(2026,11,2)),
            Expiry("Vier","4K IPTV",date(2026,11,4)),
            Expiry("Ignore","The Best",date(2026,11,9))
        ]
        groups=weekly_entries(rows,monday)
        self.assertEqual(list(groups),["4K IPTV","The Best"])
        self.assertEqual([r.customer for r in groups["The Best"]],["Eins","Zwei"])
        self.assertEqual(sum(len(g) for g in groups.values()),3)

    def test_week_rejects_non_monday(self):
        with self.assertRaises(ValueError):
            weekly_entries([],date(2026,11,3))


if __name__=="__main__":
    unittest.main()

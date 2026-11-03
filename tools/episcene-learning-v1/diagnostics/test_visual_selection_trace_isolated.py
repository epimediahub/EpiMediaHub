"""Offline unit checks for isolated read-only EpiScene peer selector trace."""
import sqlite3
import unittest
import visual_selection_trace_isolated as trace

def db():
    c=sqlite3.connect(':memory:')
    c.row_factory=sqlite3.Row
    c.execute("""CREATE TABLE skip_assets(
       asset_key TEXT,source_key TEXT,season INTEGER,episode INTEGER)""")
    c.execute("INSERT INTO skip_assets VALUES('own','family',1,1)")
    c.commit()
    return c

class FakeScene:
    def __init__(self,entries):self.entries=entries
    def _cached_rows(self,con,asset,kind):
        return [(object(),peer) for peer in self.entries]

class SelectorReadOnlyTests(unittest.TestCase):
    def test_no_peers(self):
        c=db()
        self.assertEqual(trace.selected_peer_profile(c,FakeScene([]),{'asset_key':'own','segment_type':'intro'}),
                         'SELECTOR_RETURNED_NO_PEERS')
        c.close()
    def test_multiple_distinct_peers(self):
        c=db()
        self.assertEqual(trace.selected_peer_profile(c,FakeScene([
            {'source_key':'family','season':1,'episode':2},
            {'source_key':'family','season':1,'episode':3}
        ]),{'asset_key':'own','segment_type':'intro'}),'SELECTOR_RETURNED_TWO_PEERS')
        c.close()
    def test_no_cross_series_leak(self):
        c=db()
        self.assertEqual(trace.selected_peer_profile(c,FakeScene([
            {'source_key':'other','season':1,'episode':2}
        ]),{'asset_key':'own','segment_type':'intro'}),'SELECTOR_CROSS_SERIES_OR_SEASON')
        c.close()
    def test_no_production_write(self):
        c=db()
        c.execute('PRAGMA query_only=ON')
        self.assertEqual(trace.selected_peer_profile(c,FakeScene([]),{'asset_key':'own','segment_type':'outro'}),
                         'SELECTOR_RETURNED_NO_PEERS')
        c.close()

if __name__=='__main__':
    unittest.main()

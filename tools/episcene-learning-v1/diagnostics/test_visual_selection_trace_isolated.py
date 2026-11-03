"""Offline regression checks for EpiScene real cache-row selector format.

Matches production analyze(): _cached_rows yields sqlite3.Row with asset_key;
analyze() later resolves each cache row's parent from skip_assets.
"""
import sqlite3
import unittest
import visual_selection_trace_isolated as trace

def db():
    c=sqlite3.connect(':memory:')
    c.row_factory=sqlite3.Row
    c.execute("""CREATE TABLE skip_assets(
       asset_key TEXT PRIMARY KEY,source_key TEXT,season INTEGER,episode INTEGER)""")
    c.execute("CREATE TABLE fake_windows(asset_key TEXT, kind TEXT)")
    c.executemany("INSERT INTO skip_assets VALUES(?,?,?,?)",[
        ('own','family',1,1),('peer2','family',1,2),
        ('peer3','family',1,3),('peer3_dup','family',1,3),
        ('other','different_family',1,4),('wrongseason','family',2,5)
    ])
    c.commit()
    return c

class FakeScene:
    def _cached_rows(self,con,asset,kind):
        return con.execute("SELECT asset_key,kind FROM fake_windows WHERE kind=?",
                           (kind,)).fetchall()

def insert_windows(c,*keys):
    c.executemany("INSERT INTO fake_windows VALUES (?,'intro')",[(key,) for key in keys])
    c.commit()

def classify(c):
    return trace.selected_peer_profile(c,FakeScene(),{'asset_key':'own','segment_type':'intro'})

class SelectorReadOnlyTests(unittest.TestCase):
    def test_sqlite_row_returns_no_peers(self):
        c=db()
        self.assertEqual(classify(c),'SELECTOR_WITHOUT_SELF_NO_PEERS')
        c.close()

    def test_real_row_shape_with_two_distinct_peers(self):
        c=db();insert_windows(c,'peer2','peer3')
        self.assertEqual(classify(c),'SELECTOR_WITHOUT_SELF_TWO_PEERS')
        c.close()

    def test_duplicate_episode_not_counted_twice(self):
        c=db();insert_windows(c,'peer3','peer3_dup')
        self.assertEqual(classify(c),'SELECTOR_WITHOUT_SELF_ONE_PEER')
        c.close()

    def test_parent_asset_missing_is_reported(self):
        c=db();insert_windows(c,'gone')
        self.assertEqual(classify(c),'SELECTOR_PARENT_ASSET_MISSING')
        c.close()

    def test_cross_series_and_season_are_not_counted(self):
        c=db();insert_windows(c,'other')
        self.assertEqual(classify(c),'SELECTOR_CROSS_SERIES_OR_SEASON')
        c.execute("DELETE FROM fake_windows")
        insert_windows(c,'wrongseason')
        self.assertEqual(classify(c),'SELECTOR_CROSS_SERIES_OR_SEASON')
        c.close()

    def test_own_episode_is_not_comparison_peer(self):
        c=db();insert_windows(c,'own')
        self.assertEqual(classify(c),'SELECTOR_WITH_SELF_NO_PEERS')
        c.close()

    def test_own_row_does_not_hide_independent_peers_after_it(self):
        c=db();insert_windows(c,'own','peer2','peer3')
        self.assertEqual(classify(c),'SELECTOR_WITH_SELF_TWO_PEERS')
        c.close()

    def test_duplicate_windows_do_not_increase_independent_episodes(self):
        c=db();insert_windows(c,'own','peer2','peer2','peer3')
        self.assertEqual(classify(c),'SELECTOR_WITH_SELF_TWO_PEERS')
        c.close()

    def test_own_is_not_the_only_reason_no_match(self):
        c=db();insert_windows(c,'own','peer2')
        self.assertEqual(classify(c),'SELECTOR_WITH_SELF_ONE_PEER')
        c.close()

    def test_query_only_snapshot_read(self):
        c=db();insert_windows(c,'peer2')
        c.execute('PRAGMA query_only=ON')
        self.assertEqual(classify(c),'SELECTOR_WITHOUT_SELF_ONE_PEER')
        c.close()

if __name__=='__main__':
    unittest.main()

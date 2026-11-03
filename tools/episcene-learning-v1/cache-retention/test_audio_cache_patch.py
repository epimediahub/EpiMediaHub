import json
import sqlite3
import unittest

from audio_cache_patch import HELPER_NAME, LEGACY_SQL, patch

SOURCE = '''# source marker
def unrelated():
    return 123

def save_window(con, asset, kind, words, step, offset, length):
    con.execute("INSERT OR REPLACE INTO skip_auto_windows (asset_key, kind, created_at, words_json) VALUES (?, ?, ?, ?)", (asset, kind, 1, words))
    con.execute("DELETE FROM skip_auto_windows WHERE rowid NOT IN (SELECT rowid FROM skip_auto_windows ORDER BY created_at DESC LIMIT 256)")
'''

def database():
    con = sqlite3.connect(':memory:')
    con.execute('CREATE TABLE skip_auto_windows (asset_key TEXT,kind TEXT,created_at INTEGER,words_json TEXT)')
    con.execute('CREATE TABLE skip_records (id INTEGER PRIMARY KEY,segment_type TEXT,status TEXT)')
    con.execute('CREATE TABLE skip_auto_evidence (record_id INTEGER,evidence_json TEXT)')
    return con

def helper():
    after, changed = patch(SOURCE)
    assert changed
    ns = {}
    exec(compile(after, '<test>', 'exec'), ns)
    return ns[HELPER_NAME]

class AudioCachePatchTests(unittest.TestCase):
    def test_exact_patch_and_idempotency(self):
        updated, changed = patch(SOURCE)
        self.assertTrue(changed)
        self.assertNotIn(LEGACY_SQL, updated)
        self.assertIn('def unrelated():\n    return 123',updated)
        self.assertIn(HELPER_NAME + '(con)',updated)
        second, changed = patch(updated)
        self.assertFalse(changed)
        self.assertEqual(second, updated)

    def test_refuses_unknown_source(self):
        with self.assertRaises(ValueError):
            patch(SOURCE.replace('LIMIT 256', 'LIMIT 512'))
        with self.assertRaises(ValueError):
            patch(SOURCE.replace('def save_window(', 'def other('))

    def test_does_not_trim_small_cache(self):
        con = database()
        con.executemany("INSERT INTO skip_auto_windows VALUES (?,?,?,?)",
                        [('asset'+str(i),'intro',i,'[]') for i in range(100)])
        helper()(con)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_auto_windows').fetchone()[0],100)

    def test_pending_evidence_pins_oldest_row(self):
        con = database()
        con.executemany("INSERT INTO skip_auto_windows VALUES (?,?,?,?)",
                        [('asset'+str(i),'intro',i,'[]') for i in range(9000)])
        # asset0 is the oldest row and would be pruned by any plain LRU.
        e=json.dumps({'windows':[{'asset_key':'asset0','origin':'server'},
                                 {'asset_key':'asset1'}]})
        con.execute("INSERT INTO skip_records VALUES (1,'intro','pending')")
        con.execute("INSERT INTO skip_auto_evidence VALUES(1,?)",(e,))
        helper()(con)
        left={x[0] for x in con.execute('SELECT asset_key FROM skip_auto_windows')}
        self.assertEqual(len(left),8192)
        self.assertIn('asset0',left)
        self.assertIn('asset1',left)
        self.assertNotIn('asset2',left)
        self.assertIn('asset8999',left)

    def test_other_segment_not_pinned_by_wrong_kind(self):
        con = database()
        con.executemany("INSERT INTO skip_auto_windows VALUES (?,?,?,?)",
                        [('asset'+str(i),'intro',i,'[]') for i in range(9000)])
        e=json.dumps({'windows':[{'asset_key':'asset0'}]})
        con.execute("INSERT INTO skip_records VALUES (1,'outro','pending')")
        con.execute("INSERT INTO skip_auto_evidence VALUES(1,?)",(e,))
        helper()(con)
        self.assertFalse(con.execute("SELECT 1 FROM skip_auto_windows WHERE asset_key='asset0'").fetchone())

    def test_corrupted_pending_evidence_blocks_cleanup(self):
        con=database()
        con.executemany("INSERT INTO skip_auto_windows VALUES (?,?,?,?)",
                        [('asset'+str(i),'intro',i,'[]') for i in range(9000)])
        con.execute("INSERT INTO skip_records VALUES (1,'intro','pending')")
        con.execute("INSERT INTO skip_auto_evidence VALUES(1,'{broken')")
        helper()(con)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_auto_windows').fetchone()[0],9000)

if __name__ == '__main__':
    unittest.main()

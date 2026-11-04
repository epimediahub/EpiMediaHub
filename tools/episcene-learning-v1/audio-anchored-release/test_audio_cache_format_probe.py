"""Synthetic format survey tests: no real caches, streams or worker operations."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from audio_cache_format_probe import run, structure, bucket_size, SAMPLES_PER_GROUP, numeric_metadata, meta_type, step_summary

class ProbeTests(unittest.TestCase):
    def test_format_categories(self):
        cases=[
            (None,("NULL",0)),
            ('not json',("NOT_JSON",0)),
            ('[]',("LIST_EMPTY",0)),
            ('[1,2,3]',("LIST_INTEGER",3)),
            ('["a","b"]',("LIST_STRING",2)),
            ('[1,"x"]',("LIST_MIXED",2)),
            ('{"values":[1,2]}',("OBJECT",1)),
            ('"raw"',("STRING",5)),
        ]
        # JSON string itself is structural, never parsed as fingerprint words.
        for input_,expected in cases[:-1]:
            self.assertEqual(structure(input_),expected)
        self.assertEqual(structure('"raw"'),("STRING",3))
        self.assertEqual(structure('"x"'*400000),("TOO_LARGE_TO_PARSE",0))
        self.assertEqual(bucket_size(8640),"8640-49999")

    def test_step_types_and_numeric_bounds_are_nonidentifying(self):
        self.assertEqual(meta_type(100.0),'REAL')
        self.assertEqual(meta_type(None),'NULL')
        self.assertEqual(meta_type('100.5'),'TEXT_NUMERIC')
        self.assertEqual(meta_type('secret'),'TEXT_NONNUMERIC')
        self.assertIsNone(numeric_metadata('private-asset-key'))
        self.assertIsNone(numeric_metadata(float('nan')))
        summary=step_summary({'REAL':2,'NULL':1},[123.8,123.9],[124.0,124.1])
        self.assertEqual(summary['numeric_step_ms']['min'],123.8)
        self.assertEqual(summary['types'],{'NULL':1,'REAL':2})

    def test_read_only_aggregate_metadata(self):
        with tempfile.TemporaryDirectory() as dir_:
            path=Path(dir_)/"cache.db"
            with sqlite3.connect(path) as db:
                db.executescript("""
                    CREATE TABLE skip_assets(
                      asset_key TEXT PRIMARY KEY, playlist_id INTEGER, duration_ms INTEGER);
                    CREATE TABLE skip_auto_windows(
                      asset_key TEXT, kind TEXT, step_ms INTEGER, length_ms INTEGER,
                      offset_ms INTEGER, words_json TEXT, duration_ms INTEGER, created_at TEXT);
                    INSERT INTO skip_assets VALUES ('a',8,2400000),('b',10,2500000);
                """)
                db.execute("INSERT INTO skip_auto_windows VALUES (?,?,?,?,?,?,?,?)",
                           ("a","intro",55,100000,20000,json.dumps(list(range(920))),
                            2400000,"2026-11-03"))
                db.execute("INSERT INTO skip_auto_windows VALUES (?,?,?,?,?,?,?,?)",
                           ("a","outro",55,100000,2200000,json.dumps(list(range(920))),
                            2400000,"2026-11-03"))
                db.execute("INSERT INTO skip_auto_windows VALUES (?,?,?,?,?,?,?,?)",
                           ("b","intro",55,100000,2300000,json.dumps([1]*920),
                            2500000,"2026-11-03"))
                db.commit()
            before=path.read_bytes()
            result=run(path)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(result["4K ANALYSE / intro"]["step_ms"],{55:1})
            self.assertEqual(result["4K ANALYSE / intro"]["fingerprint_word_count"],{"720-1999":1})
            self.assertEqual(result["4K ANALYSE / outro"]["sampled"],1)
            self.assertEqual(result["THE BEST / intro"]["inconsistent_window_bounds"],0)
            self.assertEqual(result["THE BEST / outro"]["sampled"],0)

if __name__=="__main__":
    unittest.main()

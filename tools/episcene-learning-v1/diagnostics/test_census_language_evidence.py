#!/usr/bin/env python3
import json
import sqlite3
import unittest
import census_language_evidence as c


class CensusTests(unittest.TestCase):
    def test_strict_german_evidence_and_ambiguity(self):
        self.assertEqual(c.classify(8,'["de"]'),'explicit_de')
        self.assertEqual(c.classify(8,'["ger"]'),'explicit_de')
        self.assertEqual(c.classify(8,'["de","tr"]'),'german_and_other_codes_review')
        self.assertEqual(c.classify(8,'["it"]'),'non_de')
        self.assertEqual(c.classify(8,None),'missing')
        self.assertEqual(c.classify(8,'not-json'),'malformed')
        self.assertEqual(c.classify(10,'["it"]'),'explicit_it')
        self.assertEqual(c.classify(10,'[]'),'missing')

    def test_no_identifiers_or_titles_in_census(self):
        db=sqlite3.connect(':memory:')
        db.executescript("""
          CREATE TABLE skip_jobs(asset_key TEXT,status TEXT);
          CREATE TABLE skip_assets(asset_key TEXT,playlist_id INTEGER,media_type TEXT,title TEXT);
          CREATE TABLE skip_asset_languages(asset_key TEXT,codes TEXT);
          INSERT INTO skip_assets VALUES('sensitive-key-1',8,'episode','Private Example'),
                 ('sensitive-key-2',8,'episode','Example2'),
                 ('sensitive-key-3',10,'episode','Example3');
          INSERT INTO skip_jobs VALUES('sensitive-key-1','queued'),
              ('sensitive-key-2','queued'),('sensitive-key-3','review');
          INSERT INTO skip_asset_languages VALUES('sensitive-key-1','["de"]'),
              ('sensitive-key-2','["it"]'),('sensitive-key-3','["it"]');
        """)
        summary=c.census(db)
        self.assertEqual(summary['8']['queued'],{'explicit_de':1,'non_de':1})
        self.assertEqual(summary['10']['review'],{'explicit_it':1})
        output=json.dumps(summary)
        self.assertNotIn('sensitive-key',output)
        self.assertNotIn('Private Example',output)


if __name__=='__main__':
    unittest.main()

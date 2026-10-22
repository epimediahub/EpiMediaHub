#!/usr/bin/env python3
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import failure_template_triage as x

class TestTriager(unittest.TestCase):
    def test_fstring_site_matches_without_revealing_details(self):
        code='def failure(reason):\n    return f"Stream failed: {reason}"\n'
        got=x.sites(code,'Stream failed: https://private.provider/tokenSECRET','skip_analysis_worker.py')
        self.assertEqual(got,[{'file':'skip_analysis_worker.py','function':'failure','line':2,'match':'FORMATTED_TEMPLATE'}])
        self.assertEqual(x.sites('def broken(:','failed abcdefghijk','skip_scene.py'),[])

    def test_private_report_and_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'skip_analysis_worker.py').write_text(
                'def failure(reason):\n    return f"Stream failed: {reason}"\n',encoding='utf-8')
            data=root/'database.sqlite3'
            with sqlite3.connect(data) as db:
                db.executescript('''
                    CREATE TABLE skip_assets(asset_key TEXT, playlist_id INTEGER);
                    CREATE TABLE skip_jobs(asset_key TEXT, status TEXT, detail TEXT);
                ''')
                db.executemany('INSERT INTO skip_assets VALUES (?,?)',
                               [('alpha',10),('beta',10),('gamma',8)])
                db.executemany('INSERT INTO skip_jobs VALUES (?,?,?)', [
                    ('alpha','failed','Stream failed: https://private.provider/tokenSECRET'),
                    ('beta','failed','Stream failed: https://private.provider/tokenSECRET'),
                    ('gamma','review','generic needs check')])
            with sqlite3.connect(data.resolve().as_uri()+'?mode=ro',uri=True) as db:
                report=x.database_report(db,root)
            self.assertEqual(report['jobs']['10']['failed']['dominant_count'],2)
            self.assertEqual(report['jobs']['10']['failed']['allowlisted_technical_words'],['stream','failed'])
            self.assertEqual(report['jobs']['10']['failed']['corresponding_source_locations'][0]['function'],'failure')
            out=json.dumps(report)
            for secret in ('tokenSECRET','private.provider','https://','alpha','beta','generic needs check'):
                self.assertNotIn(secret,out)
            with sqlite3.connect(data) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM skip_jobs').fetchone()[0],3)

if __name__=='__main__':unittest.main()

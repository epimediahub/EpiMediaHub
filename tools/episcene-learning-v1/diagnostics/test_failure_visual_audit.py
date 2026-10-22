import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from failure_visual_audit import audit, classify

class Checks(unittest.TestCase):
    def make_db(self,fn):
        d=sqlite3.connect(fn)
        d.executescript('''
            CREATE TABLE skip_assets (asset_key TEXT PRIMARY KEY, playlist_id INTEGER NOT NULL);
            CREATE TABLE skip_jobs (asset_key TEXT, status TEXT, detail TEXT, attempts INTEGER);
            CREATE TABLE skip_records (id INTEGER PRIMARY KEY, asset_key TEXT, status TEXT,source TEXT, segment_type TEXT);
            CREATE TABLE skip_auto_evidence (record_id INTEGER, evidence_json TEXT);
            CREATE TABLE skip_scene_windows (asset_key TEXT, kind TEXT);
        ''')
        d.executemany('INSERT INTO skip_assets VALUES (?,?)', [('one',8),('two',10),('three',99)])
        d.executemany('INSERT INTO skip_jobs VALUES (?,?,?,?)', [
            ('one','failed','HTTP 429 for secret://private/url',3),('two','partial','ffmpeg decode failed secret',1),
            ('two','failed','timeout while downloading stream',2),('three','failed','403 forbidden',9),
            ('one','review','scene could not confirm',0)])
        d.executemany('INSERT INTO skip_records VALUES (?,?,?,?,?)',[(1,'one','pending','audio','intro'),(2,'two','pending','episcene','outro')])
        d.executemany('INSERT INTO skip_auto_evidence VALUES (?,?)',[(1,json.dumps({'episcene_required':True})),(2,json.dumps({'method':'episcene_consensus','decision':{'status':'REVIEW'}}))])
        d.executemany('INSERT INTO skip_scene_windows VALUES (?,?)',[('one','intro'),('one','intro'),('two','outro')])
        d.commit();d.close()

    def test_read_only_and_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'test.sqlite3'
            self.make_db(p)
            with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True) as db:
                report=audit(db)
                out=json.dumps(report)
                self.assertNotIn('private',out)
                self.assertNotIn('secret',out)
                self.assertNotIn('one',out)
                self.assertEqual(report['jobs']['8']['failure_classes_by_status']['failed'],{'PROVIDER_RATE_OR_CONNECTION_LIMIT':1})
                self.assertEqual(report['jobs']['10']['failure_classes_by_status']['failed'],{'TIMEOUT_OR_BUDGET':1})
                self.assertEqual(report['jobs']['10']['failure_classes_by_status']['partial'],{'DECODER_OR_MEDIA':1})
                self.assertEqual(report['visual_cache']['by_playlist_kind']['8']['intro']['windows'],2)
                self.assertEqual(report['approval_evidence']['by_playlist']['8'],{'AWAITING_VISUAL_CONSENSUS':1})
                self.assertEqual(report['approval_evidence']['by_playlist']['10'],{'VISUAL_DECISION_REVIEW':1})
                self.assertEqual(report['marker_approvals_triggered'],0)
            with sqlite3.connect(p) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM skip_jobs').fetchone()[0],5)

    def test_missing_optional_schemas(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript('CREATE TABLE skip_assets(asset_key TEXT,playlist_id INTEGER);CREATE TABLE skip_jobs(asset_key TEXT,status TEXT);')
            r=audit(db)
            self.assertEqual(r['visual_cache']['status'],'NOT_PRESENT')
            self.assertEqual(r['approval_evidence']['status'],'NOT_PRESENT')

    def test_classification(self):
        self.assertEqual(classify('HTTP 401 Unauthorized'),'PROVIDER_AUTH_OR_EXPIRED')
        self.assertEqual(classify('processing reached time budget'),'TIMEOUT_OR_BUDGET')
        self.assertEqual(classify('unrecognized reason'),'OTHER_NOT_CLASSIFIED')
        self.assertEqual(classify(None),'NO_DETAIL')

if __name__=='__main__':unittest.main()

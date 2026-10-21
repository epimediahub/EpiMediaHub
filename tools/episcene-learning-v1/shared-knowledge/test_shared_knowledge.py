#!/usr/bin/env python3
import sqlite3
import tempfile
import unittest
from pathlib import Path
from shared_knowledge import (Episode, Marker, Knowledge, search_windows,
    parse_introdb_app, parse_theintrodb, admitted_external)

CUT_A = "a" * 64
CUT_B = "b" * 64

def ep(cut=CUT_A, playlist=8):
    return Episode("imdb","tt1234567",2,3,2_400_000,cut)

class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dbpath = Path(self.temp.name)/"learn.sqlite3"
        self.knowledge = Knowledge(self.dbpath)

    def tearDown(self):
        self.temp.cleanup()

    def test_both_playlists_teach_a_shared_reference(self):
        original=ep()
        self.knowledge.add(original, Marker("intro",50000,123000,"human_verified",8,CUT_A))
        self.knowledge.add(original, Marker("recap",10000,50000,"analyzer_verified",10,CUT_A))
        decided=self.knowledge.resolve(original)
        self.assertEqual({r["kind"] for r in decided},{"intro","recap"})
        self.assertTrue(all(r["eligible_for_original_release_gate"] for r in decided))

    def test_provider_switch_not_directly_trusted_when_cut_differs(self):
        self.knowledge.add(ep(), Marker("intro",50000,123000,"human_verified",8,CUT_A))
        result=self.knowledge.resolve(ep(CUT_B))[0]
        self.assertEqual(result["status"],"needs_cut_alignment")
        self.assertFalse(result["eligible_for_original_release_gate"])

    def test_equal_runtime_without_fingerprint_is_not_cut_proof(self):
        self.knowledge.add(ep(""),Marker("intro",50000,123000,"introdb",8,""))
        result=self.knowledge.resolve(ep(""))[0]
        self.assertEqual(result["status"],"needs_cut_alignment")

    def test_conflicting_same_cut_sources_are_held_for_review(self):
        self.knowledge.add(ep(),Marker("intro",50000,123000,"human_verified",8,CUT_A))
        self.knowledge.add(ep(),Marker("intro",60000,145000,"theintrodb",10,CUT_A))
        result=self.knowledge.resolve(ep())[0]
        self.assertEqual(result["status"],"conflict_review")

    def test_repeat_ingest_is_idempotent(self):
        for _ in range(2):
            self.knowledge.add(ep(),Marker("intro",50000,123000,"human_verified",8,CUT_A))
        with sqlite3.connect(self.dbpath) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM verified_references").fetchone()[0],1)

    def test_rejects_customer_playlist_and_bad_marker(self):
        with self.assertRaises(ValueError):
            self.knowledge.add(ep(),Marker("intro",1,10000,"human_verified",999,CUT_A))
        with self.assertRaises(ValueError):
            self.knowledge.add(ep(),Marker("intro",-1,10000,"human_verified",8,CUT_A))

    def test_scan_windows_are_preferences(self):
        w=search_windows(2_400_000)
        self.assertEqual(w["recap"],(0,180_000))
        self.assertEqual(w["intro"],(0,600_000))
        self.assertEqual(w["outro"],(2_100_000,2_400_000))
        self.assertTrue(w["expand_on_miss"])

    def test_introdb_parsing_and_absence(self):
        data={"imdb_id":"tt1234567","season":2,"episode":3,
              "intro":{"start_ms":30000,"end_ms":90000},
              "no_recap":True,"recap":None}
        self.assertEqual(len(admitted_external(ep(""),data,provider="introdb",playlist_id=10)),1)
        data["recap"]={"start_ms":30000,"end_ms":90000}
        with self.assertRaises(ValueError):
            admitted_external(ep(""),data,provider="introdb",playlist_id=10)

    def test_theintrodb_v4_nullable_edges_and_multiple_segments(self):
        data={"tvdb_id":169,"season":1,"episode":4,
              "intro":[{"start_ms":None,"end_ms":90000},{"start_ms":200000,"end_ms":230000}],
              "credits":[{"start_ms":2250000,"end_ms":None}]}
        tv=Episode("tvdb","169",1,4,2_400_000)
        self.assertEqual(len(admitted_external(tv,data,provider="theintrodb",playlist_id=8)),3)
        self.assertEqual(parse_theintrodb(data,2_400_000)[-1]["end_ms"],2_400_000)

    def test_external_source_never_fakes_fingerprint(self):
        data={"imdb_id":"tt1234567","season":2,"episode":3,
              "intro":{"start_ms":30000,"end_ms":90000}}
        refs=admitted_external(ep(),data,provider="introdb",playlist_id=8)
        self.assertEqual(refs[0].cut_digest,"")
        with self.assertRaises(ValueError):
            self.knowledge.add(ep(),refs[0])

    def test_wrong_external_identity_rejected(self):
        data={"imdb_id":"tt9999999","season":2,"episode":3,
              "intro":{"start_ms":30000,"end_ms":90000}}
        with self.assertRaises(ValueError):
            admitted_external(ep(),data,provider="introdb",playlist_id=8)

if __name__ == "__main__":
    unittest.main()

"""Synthetic EpiScene review handler integration; no real marker database."""
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
import unittest
import uuid
from unittest import mock

from flask import Flask,abort,current_app,request,session
import mobile_flask


def csrf():
    supplied=request.form.get("csrf","")
    known=session.get("_marker_session_csrf","")
    if not known or not secrets.compare_digest(supplied,known):
        abort(400)


def v082_skip_review(record_id):
    csrf()
    decision=request.form.get("decision")
    if decision not in ("approve","reject"):
        abort(400)
    path=current_app.config["MARKER_TEST_DB"]
    with sqlite3.connect(path) as con:
        exists=con.execute("SELECT id FROM skip_records WHERE id=? AND status='pending'",
                           (record_id,)).fetchone()
        if not exists:abort(404)
        con.execute("UPDATE skip_records SET status=? WHERE id=?",
                    ("approved" if decision=="approve" else "rejected",record_id))
    return "303 original redirect"


class NativeMarkerReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.db=self.root/"provisioning.db"
        with sqlite3.connect(self.db) as db:
            db.executescript("""
                CREATE TABLE skip_assets(
                    asset_key TEXT PRIMARY KEY,playlist_id INTEGER,title TEXT,
                    season INTEGER,episode INTEGER);
                CREATE TABLE skip_records(
                    id INTEGER PRIMARY KEY,asset_key TEXT,segment_type TEXT,
                    start_ms INTEGER,end_ms INTEGER,status TEXT);
                INSERT INTO skip_assets VALUES
                   ('a',8,'Synthetic Series',1,2),
                   ('b',10,'Synthetic Show',3,4),
                   ('c',11,'Other Account',1,2);
                INSERT INTO skip_records VALUES
                   (21,'a','intro',1000,50000,'pending'),
                   (22,'b','outro',120000,180000,'pending'),
                   (23,'c','recap',2000,40000,'pending');
            """)
        self.app=Flask("test-marker-private")
        self.app.secret_key="testing-only"
        self.app.config["MARKER_TEST_DB"]=self.db
        mobile_flask.install(self.app)
        self.app.view_functions["v082_skip_review"]=v082_skip_review
        self.client=self.app.test_client()
        self.patch=mock.patch.object(mobile_flask,"_base",return_value=self.root)
        self.patch.start()
        self.env=mock.patch.dict(os.environ,{
            "EPIMEDIAHUB_NATIVE_EPISCENE_REVIEW_ENABLED":"YES"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.patch.stop()
        self.temp.cleanup()

    def login(self):
        with self.client.session_transaction() as sess:
            sess["admin"]=True
            sess["_dashboard_csrf"]="TEST_"+("A"*40)
        return self.client.get("/admin/mobile/bootstrap").get_json()["csrf"]

    def post(self,id,decision,marker_token,dashboard_token,key=None):
        return self.client.post(
            f"/admin/mobile/episcene/reviews/{id}/{decision}",
            data={"csrf":marker_token,"decision":decision,"confirm":"true",
                  "request_id":key or str(uuid.uuid4())},
            headers={"X-Dashboard-CSRF":dashboard_token}
        )

    def test_private_queue_and_original_approved_rejected_postconditions(self):
        self.assertEqual(self.client.get("/admin/mobile/episcene/reviews").status_code,401)
        dashboard=self.login()
        preview=self.client.get("/admin/mobile/episcene/reviews")
        self.assertEqual(preview.status_code,200)
        data=preview.get_json()
        self.assertEqual(len(data["markers"]),2)
        self.assertEqual({row["id"] for row in data["markers"]},{"21","22"})
        self.assertNotIn("Other Account",preview.get_data(as_text=True))
        marker_csrf=data["review_csrf"]
        self.assertGreater(len(marker_csrf),31)
        self.assertEqual(self.post(21,"approve",marker_csrf,"wrong").status_code,403)
        self.assertEqual(self.post(21,"approve","wrong",dashboard).status_code,400)
        key=str(uuid.uuid4())
        yes=self.post(21,"approve",marker_csrf,dashboard,key)
        self.assertEqual(yes.status_code,200,yes.get_data(as_text=True))
        self.assertTrue(yes.get_json()["applied"])
        repeated=self.post(21,"approve",marker_csrf,dashboard,key)
        self.assertEqual(repeated.status_code,200)
        self.assertTrue(repeated.get_json()["replayed"])
        no=self.post(22,"reject",marker_csrf,dashboard)
        self.assertEqual(no.status_code,200)
        with sqlite3.connect(self.db) as con:
            self.assertEqual(con.execute(
                "SELECT status FROM skip_records WHERE id=21").fetchone()[0],"approved")
            self.assertEqual(con.execute(
                "SELECT status FROM skip_records WHERE id=22").fetchone()[0],"rejected")
            self.assertEqual(con.execute(
                "SELECT status FROM skip_records WHERE id=23").fetchone()[0],"pending")

    def test_disabled_feature_and_out_of_scope_record_never_mutated(self):
        dashboard=self.login()
        response=self.client.get("/admin/mobile/episcene/reviews")
        token=response.get_json()["review_csrf"]
        out=self.post(23,"approve",token,dashboard)
        self.assertEqual(out.status_code,409)
        with mock.patch.dict(os.environ,{"EPIMEDIAHUB_NATIVE_EPISCENE_REVIEW_ENABLED":"NO"}):
            self.assertEqual(self.client.get(
                "/admin/mobile/episcene/reviews").status_code,503)
            self.assertEqual(self.post(21,"approve",token,dashboard).status_code,503)


if __name__=="__main__":
    unittest.main()

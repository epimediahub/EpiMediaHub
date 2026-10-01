from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["EPIMEDIAHUB_DATA_DIR"] = tempfile.mkdtemp(prefix="epimediahub-skip-tests-")
os.environ["EPIMEDIAHUB_ADMIN_TOKEN"] = "skip-test-token"
os.environ["EPIMEDIAHUB_ADMIN_PASSWORD"] = "skip-test-password"
os.environ["EPIMEDIAHUB_SECRET_KEY"] = "skip-test-secret"
os.environ["EPIMEDIAHUB_SECURE_COOKIES"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import db, digest
from wsgi import app
from skip_markers import now, migrate, parse_time, timecode
from skip_analysis import provider_asset_key, register_asset, source_url, public_address, chapter_candidates, matching_offset
from skip_analysis_worker import process_one


class SkipMarkersTest(unittest.TestCase):
    def setUp(self):
        self.admin = app.test_client()
        self.a = app.test_client(); self.b = app.test_client()
        with db() as con:
            for table in ("skip_fingerprints", "skip_jobs", "skip_assets", "skip_presence", "skip_analysis_sources", "skip_records", "skip_identities", "skip_rate"):
                con.execute("DELETE FROM " + table)
            con.execute("DELETE FROM customers WHERE name IN ('Skip test a','Skip test b')")
            self.customers = []; self.devices = []
            for label in ("a", "b"):
                customer = con.execute("INSERT INTO customers(name,config_json,created_at) VALUES(?,'{}',?)", ("Skip test " + label, now())).lastrowid
                device = con.execute("INSERT INTO devices(customer_id,device_id,platform,session_token_hash,created_at) VALUES(?,?,'android',?,?)", (customer, "skip-" + label, digest("token-" + label), now())).lastrowid
                self.customers.append(customer); self.devices.append(device)
        self.ha = {"Authorization": "Bearer token-a"}; self.hb = {"Authorization": "Bearer token-b"}
        self.data = dict(asset_key="a" * 64, source_key="b" * 64, media_type="episode", title="Beispielserie", year="2024", season=1, episode=1, duration_ms=2_400_000, imdb_id="tt0903747", tmdb_id=1396)
        self.mark = self.data | dict(segment_type="intro", start_ms=30_123, end_ms=90_456, disabled=False)
        self.admin.post("/admin/login", data={"password": "skip-test-password"})
        self.admin.get("/admin/skip")
        with self.admin.session_transaction() as session:
            self.csrf = session["skip_csrf"]

    def submit(self, data=None, headers=None):
        return self.a.post("/v1/device/skip/submit", json=self.mark if data is None else data, headers=self.ha if headers is None else headers)

    def lookup(self, data=None):
        return self.b.post("/v1/device/skip/lookup", json=self.data if data is None else data, headers=self.hb)

    def review(self, record, decision="approve", **fields):
        return self.admin.post(f"/admin/skip/{record}/review", data=dict(csrf=self.csrf, decision=decision, **fields))

    def test_pending_proposals_are_private_and_idempotent(self):
        first = self.submit(); second = self.submit()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json()["id"], second.get_json()["id"])
        self.assertEqual(self.lookup().get_json()["segments"], [])
        self.assertNotIn("customer_id", self.lookup().get_json())
        self.assertEqual(self.a.get("/admin/skip").status_code, 302)

    def test_reviewed_mark_is_shared_without_rounding_away_milliseconds(self):
        record = self.submit().get_json()["id"]
        self.assertEqual(self.review(record).status_code, 302)
        result = self.lookup().get_json()["segments"]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["start_ms"], 30_123)
        self.assertEqual(result[0]["end_ms"], 90_456)

    def test_changed_runtime_file_or_episode_never_reuses_the_mark(self):
        record = self.submit().get_json()["id"]; self.review(record)
        for changes in (dict(duration_ms=2_410_000), dict(asset_key="c" * 64), dict(episode=2)):
            self.assertEqual(self.lookup(self.data | changes).get_json()["segments"], [])
        # A corrected display title does not invalidate the same measured file.
        self.assertEqual(len(self.lookup(self.data | dict(source_key="d" * 64, title="Korrigierter Titel")).get_json()["segments"]), 1)

    def test_rejects_unknown_disabled_devices_and_customers(self):
        self.assertEqual(self.submit(headers={}).status_code, 401)
        self.assertEqual(self.submit(headers={"Authorization": "Bearer wrong"}).status_code, 401)
        with db() as con:
            con.execute("UPDATE devices SET enabled=0 WHERE id=?", (self.devices[0],))
        self.assertEqual(self.submit().status_code, 401)
        with db() as con:
            con.execute("UPDATE devices SET enabled=1 WHERE id=?", (self.devices[0],))
            con.execute("UPDATE customers SET enabled=0 WHERE id=?", (self.customers[0],))
        self.assertEqual(self.submit().status_code, 401)

    def test_invalid_ranges_and_credential_fields_never_get_saved(self):
        invalid = [dict(start_ms=-1), dict(start_ms=100_000, end_ms=30_000), dict(end_ms=2_400_001), dict(disabled="true"), dict(url="http://localhost/private"), dict(duration_ms=True), dict(asset_key="not-a-key")]
        for change in invalid:
            self.assertEqual(self.submit(self.mark | change).status_code, 400, change)
        self.assertEqual(self.submit([]).status_code, 400)
        with db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_records").fetchone()[0], 0)

    def test_review_requires_admin_and_valid_csrf(self):
        record = self.submit().get_json()["id"]
        self.assertEqual(self.a.post(f"/admin/skip/{record}/review", data=dict(decision="approve", csrf=self.csrf)).status_code, 302)
        self.assertEqual(self.admin.post(f"/admin/skip/{record}/review", data=dict(decision="approve", csrf="bad")).status_code, 403)
        self.assertEqual(self.lookup().get_json()["segments"], [])

    def test_new_review_supersedes_only_the_same_file_and_kind(self):
        first = self.submit().get_json()["id"]; self.review(first)
        second = self.submit(self.mark | dict(start_ms=40_000, end_ms=80_000)).get_json()["id"]
        self.assertEqual(self.lookup().get_json()["segments"][0]["start_ms"], 30_123)
        self.review(second)
        self.assertEqual(self.lookup().get_json()["segments"][0]["start_ms"], 40_000)
        with db() as con:
            self.assertEqual(con.execute("SELECT status FROM skip_records WHERE id=?", (first,)).fetchone()[0], "superseded")

    def test_explicit_absence_can_be_reviewed_and_withdrawn(self):
        record = self.submit(self.mark | dict(disabled=True, start_ms=0, end_ms=0)).get_json()["id"]
        self.review(record, disabled="1")
        self.assertTrue(self.lookup().get_json()["segments"][0]["disabled"])
        self.review(record, decision="reject", disabled="1")
        self.assertEqual(self.lookup().get_json()["segments"], [])

    def test_identity_edits_are_scoped_and_require_valid_ids(self):
        record = self.submit().get_json()["id"]
        path = f"/admin/skip/{record}/identity"
        self.assertEqual(self.admin.post(path, data=dict(csrf=self.csrf, imdb_id="invalid", tmdb_id="1")).status_code, 400)
        self.assertEqual(self.admin.post(path, data=dict(csrf=self.csrf, imdb_id="tt0944947", tmdb_id="1399")).status_code, 302)
        self.assertEqual(self.lookup().get_json()["identity"]["imdb_id"], "tt0944947")
        self.assertEqual(self.lookup(self.data | dict(source_key="c" * 64)).get_json()["identity"], {})

    def playlist(self, customer):
        config = dict(playlist_type="XTREAM", xtream_server="https://provider.example", xtream_username="account", xtream_password="never-print-this")
        with db() as con:
            row = con.execute("INSERT INTO customer_playlists(customer_id,name,config_json,created_at,updated_at) VALUES(?,?,?,?,?)", (customer, "Testprovider", json.dumps(config), now(), now())).lastrowid
            con.execute("INSERT INTO skip_analysis_sources VALUES(?,1,?)", (row, now()))
        return row

    def test_analysis_uses_only_owned_playlists_and_matching_provider_files(self):
        owned = self.playlist(self.customers[0]); foreign = self.playlist(self.customers[1])
        asset = provider_asset_key("https://provider.example/series/account/never-print-this/81.mkv", "episode")
        raw = self.data | dict(asset_key=asset, playlist_id=foreign, stream_id="81", extension="mkv")
        self.a.post("/v1/device/skip/lookup", json=raw, headers=self.ha)
        with db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_assets").fetchone()[0], 0)
        raw["playlist_id"] = owned
        self.assertEqual(self.a.post("/v1/device/skip/lookup", json=raw, headers=self.ha).status_code, 200)
        with db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_assets").fetchone()[0], 1)
        self.assertEqual(self.a.post("/v1/device/skip/presence", json=dict(playlist_id=foreign), headers=self.ha).status_code, 404)
        self.assertEqual(self.a.post("/v1/device/skip/presence", json=dict(playlist_id=owned), headers=self.ha).status_code, 200)
        with patch("skip_analysis_worker.provider_proxy") as proxy:
            self.assertEqual(process_one(db), "queued")
            proxy.assert_not_called()

    def test_private_destinations_redirects_and_embedded_credentials_are_blocked(self):
        addr = [(2, 1, 6, "", ("127.0.0.1", 443))]
        with patch("skip_analysis.socket.getaddrinfo", return_value=addr):
            with self.assertRaises(ValueError):
                public_address("https://provider.example/stream", "provider.example")
        for url in ("file:///etc/passwd", "http://localhost/private", "https://name:password@provider.example/a"):
            with self.assertRaises(ValueError):
                public_address(url, "provider.example")

    def test_chapter_and_fingerprint_analysis_reject_weak_ambiguous_matches(self):
        chapters = [dict(start_time="30", end_time="90", tags=dict(title="Intro")), dict(start_time="90", end_time="150", tags=dict(title="Final scene")), dict(start_time="-1", end_time="90", tags=dict(title="Intro"))]
        self.assertEqual(chapter_candidates(chapters, 2_400_000), [("intro", 30_000, 90_000)])
        import random
        rng = random.Random(124)
        reference = [rng.getrandbits(32) for _ in range(80)]
        target = [rng.getrandbits(32) for _ in range(20)] + reference + [rng.getrandbits(32) for _ in range(20)]
        self.assertEqual(matching_offset(reference, target, 125)[0], 2500)
        self.assertIsNone(matching_offset(reference, target + reference, 125))
        self.assertIsNone(matching_offset([1] * 80, [1] * 120, 125))
        self.assertIsNone(matching_offset(reference, [rng.getrandbits(32) for _ in range(120)], 125))

    def test_timecode_round_trip_retains_subsecond_precision(self):
        self.assertEqual(parse_time(timecode(90_456)), 90_456)
        self.assertEqual(parse_time("01:30"), 90_000)
        with self.assertRaises(ValueError):
            parse_time("01:90")

    def test_real_audio_pipeline_finds_shifted_intro_and_keeps_it_pending(self):
        import array, ctypes.util, io, math, random, shutil, threading, urllib.parse, wave
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        if not shutil.which("ffmpeg") or not ctypes.util.find_library("chromaprint"):
            self.skipTest("ffmpeg and libchromaprint are required for the audio integration test")
        rate = 11025
        rng = random.Random(170)
        music = array.array("h")
        for _ in range(14):
            freq = rng.choice([110, 146.83, 196, 220, 261.63, 329.63, 392, 493.88, 587.33])
            music.extend(int(5500 * math.sin(2 * math.pi * freq * n / rate) + 2400 * math.sin(2 * math.pi * freq * 1.5 * n / rate) + 1200 * math.sin(2 * math.pi * (freq * 2 + 13) * n / rate)) for n in range(rate * 2))
        def audio(prefix):
            samples = array.array("h", [0]) * (rate * prefix) + music + array.array("h", [0]) * (rate * 12)
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate); wav.writeframes(samples.tobytes())
            return buffer.getvalue()
        clips = {"81.mkv": audio(18), "82.mkv": audio(29)}
        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                content = clips.get(self.path.rsplit("/", 1)[-1])
                if content is None:
                    self.send_error(404); return
                start, end = 0, len(content) - 1
                requested = self.headers.get("Range")
                if requested:
                    numbers = requested.removeprefix("bytes=").split("-")
                    start = int(numbers[0]); end = min(int(numbers[1]) if numbers[1] else end, end)
                self.send_response(206 if requested else 200)
                self.send_header("Content-Length", str(end - start + 1)); self.send_header("Accept-Ranges", "bytes")
                if requested:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{len(content)}")
                self.end_headers()
                try:
                    self.wfile.write(content[start:end + 1])
                except (BrokenPipeError, ConnectionResetError):
                    pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Provider); server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            config = dict(playlist_type="XTREAM", xtream_server=f"http://provider.test:{server.server_port}", xtream_username="account", xtream_password="test-password")
            with db() as con:
                playlist = con.execute("INSERT INTO customer_playlists(customer_id,name,config_json,created_at,updated_at) VALUES(?,?,?,?,?)", (self.customers[0], "Audiofixture", json.dumps(config), now(), now())).lastrowid
                con.execute("INSERT INTO skip_analysis_sources VALUES(?,1,?)", (playlist, now()))
            files = []
            for stream, length, episode in (("81", 58_000, 1), ("82", 69_000, 2)):
                url = f"{config['xtream_server']}/series/account/test-password/{stream}.mkv"
                data = self.data | dict(asset_key=provider_asset_key(url, "episode"), duration_ms=length, episode=episode, playlist_id=playlist, stream_id=stream, extension="mkv")
                files.append(data)
                self.assertEqual(self.a.post("/v1/device/skip/lookup", json=data, headers=self.ha).status_code, 200)
            record = self.submit(files[0] | dict(segment_type="intro", start_ms=18_000, end_ms=46_000, disabled=False)).get_json()["id"]
            self.review(record)
            def local_address(url, host):
                if host != "provider.test":
                    raise ValueError("fixture_host")
                return urllib.parse.urlsplit(url), "127.0.0.1"
            with patch("skip_analysis.public_address", side_effect=local_address):
                self.assertEqual(process_one(db), "done")
                self.assertEqual(process_one(db), "review")
            with db() as con:
                proposal = con.execute("SELECT * FROM skip_records WHERE asset_key=? AND source='audio'", (files[1]["asset_key"],)).fetchone()
            self.assertIsNotNone(proposal)
            self.assertEqual(proposal["status"], "pending")
            self.assertLessEqual(abs(proposal["start_ms"] - 29_000), 150)
            self.assertLessEqual(abs(proposal["end_ms"] - 57_000), 150)
            self.assertGreaterEqual(proposal["confidence"], .9)
            self.assertEqual(self.lookup(files[1]).get_json()["segments"], [])
            self.review(proposal["id"])
            self.assertEqual(len(self.lookup(files[1]).get_json()["segments"]), 1)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()


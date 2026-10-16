import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from monitor_rules import evaluate


NOW = int(datetime(2026, 10, 16, 9, 0, tzinfo=ZoneInfo("Europe/Berlin")).timestamp())


def keys(data):
    return {alert.key for alert in evaluate(data, NOW)}


class MonitoringRulesTest(unittest.TestCase):
    def test_stall_requires_queued_jobs_and_not_paused(self):
        self.assertIn("analysis_stalled:8", keys({"analysis_lanes": [
            {"id": 8, "last_progress_epoch": NOW - 901, "queued_jobs": 3}
        ]}))
        self.assertEqual(set(), keys({"analysis_lanes": [
            {"id": 8, "last_progress_epoch": NOW - 901, "queued_jobs": 3, "paused": True}
        ]}))
        self.assertEqual(set(), keys({"analysis_lanes": [
            {"id": 8, "last_progress_epoch": NOW - 901, "queued_jobs": 0}
        ]}))

    def test_expired_playlist_and_auth_errors_have_one_key(self):
        items = evaluate({"playlists": [
            {"id": 8, "expires_at_epoch": NOW - 1, "consecutive_auth_failures": 6}
        ]}, NOW)
        self.assertEqual(["playlist_access:8"], [a.key for a in items])
        self.assertNotIn("playlist_access:10", keys({"playlists": [{"id": 10}]}))

    def test_playlist_expiring_early_warning(self):
        self.assertIn("playlist_expiring:8", keys({"playlists": [
            {"id": 8, "expires_at_epoch": NOW + 3600}
        ]}))

    def test_worker_checksum_mismatch(self):
        self.assertIn("worker_preflight:hetzner", keys({"workers": [
            {"id": "hetzner", "expected_versions": {"skip_scene.py": "a"},
             "actual_versions": {"skip_scene.py": "b"}}
        ]}))
        self.assertEqual(set(), keys({"workers": [
            {"id": "hetzner", "expected_versions": {"x": "a"},
             "actual_versions": {"x": "a"}, "consecutive_preflight_failures": 0}
        ]}))

    def test_repeated_preflight_errors(self):
        self.assertIn("worker_preflight:hetzner", keys({"workers": [
            {"id": "hetzner", "consecutive_preflight_failures": 2}
        ]}))

    def test_service_requires_repeated_failures(self):
        self.assertEqual(set(), keys({"services": [
            {"id": "api", "consecutive_health_failures": 2}
        ]}))
        self.assertIn("service_down:api", keys({"services": [
            {"id": "api", "consecutive_health_failures": 3}
        ]}))

    def test_build_failure(self):
        self.assertIn("build_failed:release-17", keys({"builds": [
            {"id": "release-17", "outcome": "failure"}
        ]}))
        self.assertEqual(set(), keys({"builds": [
            {"id": "release-17", "outcome": "success"}
        ]}))

    def test_playback_requires_rate_and_diverse_devices(self):
        sample = {"playback_windows": [
            {"id": "app:10m", "errors": 10, "sessions": 20,
             "distinct_affected_devices": 3}
        ]}
        self.assertIn("playback_errors:app:10m", keys(sample))
        sample["playback_windows"][0]["distinct_affected_devices"] = 1
        self.assertEqual(set(), keys(sample))

    def test_daily_report_berlin_calendar_date(self):
        self.assertIn("daily_report:2026-10-16:episcene", keys({"daily_report": {
            "ready": True, "generated_date_berlin": "2026-10-16"
        }}))
        self.assertEqual(set(), keys({"daily_report": {
            "ready": True, "generated_date_berlin": "2026-10-15"
        }}))

    def test_empty_input_and_secret_free_messages(self):
        self.assertEqual([], evaluate({}, NOW))
        alert = evaluate({"playlists": [{"id": 8, "consecutive_auth_failures": 3}]}, NOW)[0]
        self.assertNotIn("username", alert.message)
        self.assertEqual("critical", alert.severity)


if __name__ == "__main__":
    unittest.main()

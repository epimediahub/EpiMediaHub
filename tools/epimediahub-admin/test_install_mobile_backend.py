"""Regression tests: dashboard startup can be slower than systemd ActiveState."""
from __future__ import annotations

import unittest
from unittest import mock
from urllib.error import URLError

import install_mobile_backend as installer


class Response:
    status=200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class HealthStartupTests(unittest.TestCase):
    def test_transient_connection_failure_retries(self):
        responses=[URLError("not ready"), Response()]
        with mock.patch.object(installer.urllib.request, "urlopen", side_effect=responses) as getter:
            with mock.patch.object(installer.time, "sleep") as pause:
                installer.wait_for_health(timeout_seconds=5)
        self.assertEqual(getter.call_count, 2)
        pause.assert_called_once_with(1)

    def test_http_503_then_200_retries(self):
        unhealthy=mock.MagicMock()
        unhealthy.status=503
        with mock.patch.object(installer.urllib.request, "urlopen", side_effect=[unhealthy, Response()]) as getter:
            with mock.patch.object(installer.time, "sleep"):
                installer.wait_for_health(timeout_seconds=5)
        self.assertEqual(getter.call_count, 2)

    def test_persistent_failure_aborts_without_fake_success(self):
        with mock.patch.object(installer.time, "monotonic", side_effect=[0,0,10]):
            with mock.patch.object(installer.time, "sleep"):
                with mock.patch.object(installer.urllib.request, "urlopen", side_effect=URLError("down")):
                    with self.assertRaisesRegex(RuntimeError, "LOCAL_DASHBOARD_HEALTH_NOT_READY:URLError"):
                        installer.wait_for_health(timeout_seconds=5)


if __name__=="__main__":
    unittest.main()

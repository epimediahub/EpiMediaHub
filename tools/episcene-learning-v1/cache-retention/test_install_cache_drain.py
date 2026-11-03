"""Unit tests for safe EpiScene analysis-batch drain coordination."""
import unittest
from unittest.mock import MagicMock, patch

import install_audio_cache_retention as installer


class DrainTests(unittest.TestCase):
    def test_nowait_refuses_to_interrupt_running_job(self):
        guard=MagicMock()
        with patch.object(installer.fcntl,'flock',side_effect=BlockingIOError), \
             patch.object(installer.time,'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'running analysis'):
                installer.wait_for_analysis_idle(guard,drain_analysis=False)
            sleep.assert_not_called()

    def test_waits_for_current_batch_without_killing_it(self):
        guard=MagicMock()
        calls=[BlockingIOError(),None,None,None]
        def lock(*a,**kw):
            value=calls.pop(0)
            if isinstance(value,BaseException):
                raise value
        with patch.object(installer.fcntl,'flock',side_effect=lock) as flock, \
             patch.object(installer,'active',side_effect=[True,False]) as active, \
             patch.object(installer.time,'sleep') as sleep:
            installer.wait_for_analysis_idle(guard,drain_analysis=True)
            self.assertEqual(sleep.call_count,2)
            self.assertEqual(active.call_count,2)
            self.assertEqual(flock.call_count,4)
            self.assertEqual(calls,[])

    def test_nowait_does_not_skip_service_state_guard(self):
        guard=MagicMock()
        with patch.object(installer.fcntl,'flock',return_value=None), \
             patch.object(installer,'active',return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'analysis batch still active'):
                installer.wait_for_analysis_idle(guard,drain_analysis=False)


if __name__ == '__main__':
    unittest.main()

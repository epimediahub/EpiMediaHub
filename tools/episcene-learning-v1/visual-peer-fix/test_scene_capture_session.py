import unittest
from contextlib import contextmanager
from scene_capture_session import capture_chunks


class SessionTests(unittest.TestCase):
    def test_reuses_one_session_and_saves_each_miss(self):
        opened = []
        closed = []
        saved = []
        @contextmanager
        def source():
            opened.append(1)
            try:
                yield object()
            finally:
                closed.append(1)
        chunks = list(capture_chunks(
            [(0, 60), (60, 60), (120, 60)],
            lambda offset, length: [99] if offset == 60 else None,
            source,
            lambda handle, offset, length: [offset],
            lambda offset, length, frames: saved.append((offset, frames)),
            lambda: False))
        self.assertEqual(chunks, [[0], [99], [120]])
        self.assertEqual(len(opened), 1)
        self.assertEqual(len(closed), 1)
        self.assertEqual(saved, [(0, [0]), (120, [120])])

    def test_closes_on_failure_after_completed_chunk(self):
        closed = []
        saved = []
        @contextmanager
        def source():
            try:
                yield object()
            finally:
                closed.append(True)
        def fingerprint(handle, offset, length):
            if offset == 60:
                raise RuntimeError("provider error")
            return [offset]
        with self.assertRaises(RuntimeError):
            list(capture_chunks([(0, 60), (60, 60)], lambda *_: None,
                source, fingerprint, lambda offset, length, frames: saved.append(offset),
                lambda: False))
        self.assertEqual(saved, [0])
        self.assertEqual(closed, [True])


if __name__ == "__main__":
    unittest.main()

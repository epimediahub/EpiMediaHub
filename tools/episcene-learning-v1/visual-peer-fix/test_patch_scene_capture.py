import ast
import unittest
from patch_scene_capture import patch, START, END


class PatchTests(unittest.TestCase):
    def test_fail_closed_on_unknown_source(self):
        with self.assertRaisesRegex(ValueError, "UNRECOGNIZED"):
            patch("def capture(): pass")

    def test_rejects_already_patched(self):
        with self.assertRaisesRegex(ValueError, "ALREADY_PATCHED"):
            patch("with ExitStack() as sources:")

    def test_inserts_one_session_and_preserves_tail(self):
        original = ("def capture(db, asset, kind, start, end, busy, verified=False):\n"
                    "    from skip_analysis import probe, provider_proxy, source_url\n"
                    "    from skip_remote_client import visual_fingerprint\n"
                    + START
                    + "        with provider_proxy(source_url(None, asset), busy) as source:\n"
                    + "            chunk = visual_fingerprint(source, cursor, part, STEP_MS, busy)\n"
                    + END)
        result = patch(original)
        ast.parse(result)
        self.assertEqual(result.count("sources.enter_context("), 1)
        self.assertIn("with ExitStack() as sources:", result)
        self.assertIn("_save(con, asset, kind, cursor, part, chunk)", result)


if __name__ == "__main__":
    unittest.main()

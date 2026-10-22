import ast
import json
import tempfile
import unittest
from pathlib import Path
from inspect_worker_return_contract import summarize,scan


class ReturnProtocolTests(unittest.TestCase):
    def test_does_not_disclose_strings_source_sql_or_credentials(self):
        source='''def analyze(db, job):
    secret="https://private.test/token=VERY_PRIVATE"
    sql="DELETE FROM skip_records WHERE credential=VERY_PRIVATE"
    if job["kind"] == "intro":
        return ("done", {"status":"review", "password":"VERY_PRIVATE"})
    return ("failed", secret)
'''
        import hashlib
        fn=ast.parse(source).body[0]
        hash16=hashlib.sha256(ast.dump(fn,include_attributes=False).encode()).hexdigest()[:16]
        row=summarize(source,{"analyze":(hash16,)})
        encoded=json.dumps(row)
        for word in ("VERY_PRIVATE","private.test","password","DELETE FROM","credential","https://"):
            self.assertNotIn(word,encoded)
        self.assertIn("Literal:done",encoded)
        self.assertIn("Literal:failed",encoded)

    def test_duplicate_functions_kept_separate_by_hash(self):
        source='''def analyze(a): return ("done",a)
class Nested:
    def analyze(self): return ("review",)
'''
        nodes=[n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.FunctionDef)
               and n.name=="analyze"]
        import hashlib
        ids=tuple(hashlib.sha256(ast.dump(n,include_attributes=False).encode()).hexdigest()[:16]
                  for n in nodes)
        self.assertEqual(len(summarize(source,{"analyze":ids})["analyze"]),2)

    def test_changed_code_does_not_pass_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"skip_schedule.py").write_text("def select_job(): return 'unexpected'")
            x=scan(root,{"skip_schedule.py":{"select_job":("0000000000000000",)}})
            self.assertFalse(x["exact_shape_gate"])


if __name__=="__main__":
    unittest.main()

import ast
import json
import tempfile
import unittest
from pathlib import Path
from inspect_active_runtime import scan, _functions, _summary


class ActiveRuntimeInspectionTests(unittest.TestCase):
    def test_no_credentials_queries_or_raw_source_exported(self):
        code='''def process_job(secret):\n x="https://private.example/token=TOP_SECRET"\n db.execute("UPDATE skip_jobs SET password=TOP_SECRET")\n return ("done",secret)\n'''
        n,parent=_functions(ast.parse(code))[0]
        output=json.dumps(_summary(n,parent))
        for s in ("TOP_SECRET","private.example","password","UPDATE skip_jobs","https://"):
            self.assertNotIn(s,output)
        self.assertIn("skip_jobs",output)
        self.assertIn("done",output)

    def test_missing_files_preserves_live_production(self):
        with tempfile.TemporaryDirectory() as td:
            result=scan(Path(td))
            self.assertEqual(result["production_writes"],0)
            self.assertTrue(all(x["status"]=="UNAVAILABLE"
                                for x in result["files"].values()))

    def test_nested_owners_disambiguated(self):
        tree=ast.parse('''class Runner:\n def process_job(self): return "done"\ndef process_job(): return "partial"\n''')
        self.assertEqual(
            { _summary(n,o)["owner"] for n,o in _functions(tree)},
            {"module","Runner"})

if __name__=="__main__":
    unittest.main()

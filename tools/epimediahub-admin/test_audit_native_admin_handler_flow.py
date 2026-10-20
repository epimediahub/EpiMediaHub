"""The sensitive AST export may expose structure but NEVER source literals."""
import ast
from pathlib import Path
import tempfile
import unittest

from audit_native_admin_handler_flow import HideLiterals, export_one

class RedactedFlowTests(unittest.TestCase):
    def test_all_literal_values_are_removed(self):
        snippet='''
def login():
    password = "SENSITIVE_PROD_PASSWORD"
    pin = 987654321
    auth_key = os.environ.get("EPIMEDIAHUB_SECRET_VALUE")
    return f"VERY_SENSITIVE_{password}", password, pin, auth_key
'''
        safe=HideLiterals().visit(ast.parse(snippet))
        ast.fix_missing_locations(safe)
        output=ast.unparse(safe)
        self.assertNotIn("SENSITIVE_PROD_PASSWORD",output)
        self.assertNotIn("987654321",output)
        self.assertNotIn("EPIMEDIAHUB_SECRET_VALUE",output)
        self.assertNotIn("VERY_SENSITIVE",output)
        self.assertIn("<literal-redacted>",output)
        self.assertIn("<format-redacted>",output)

    def test_selected_functions_only_and_no_comments(self):
        snippet='''
def grant_trial_auto():
    # NEVER_EXPORT_THIS_COMMENT
    return "HIDDEN_STRING"

def out_of_scope():
    return "ANOTHER_HIDDEN_STRING"
'''
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"vpn_auto_enroll.py"
            path.write_text(snippet,encoding="utf-8")
            result=export_one(path,{"grant_trial_auto"})
        self.assertEqual(len(result),1)
        output=str(result)
        self.assertNotIn("NEVER_EXPORT_THIS_COMMENT",output)
        self.assertNotIn("HIDDEN_STRING",output)
        self.assertNotIn("out_of_scope",output)

if __name__=="__main__":
    unittest.main()

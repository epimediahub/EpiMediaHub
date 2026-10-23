"""Offline checks; does not open any Firebase or provider network connection."""
import json
import unittest
from unittest import mock
import diagnose_fcm_validate_only as diagnose

class FirebaseDiagnosisTests(unittest.TestCase):
    def test_classifies_permission_denied_without_exposing_provider_details(self):
        raw=json.dumps({"error":{
            "code":403,"status":"PERMISSION_DENIED",
            "message":"SECRET ACCOUNT AND TOKEN SHOULD NOT APPEAR",
            "details":[
                {"@type":"type.googleapis.com/google.rpc.ErrorInfo",
                 "reason":"IAM_PERMISSION_DENIED",
                 "metadata":{"token":"SENSITIVE_TOKEN"}}]}}).encode()
        out=diagnose.safe_fcm_error(raw)
        self.assertEqual(out,{"fcm_status":"PERMISSION_DENIED",
                             "fcm_code":"UNKNOWN",
                             "google_reason":"IAM_PERMISSION_DENIED"})
        self.assertNotIn("SECRET",repr(out))
        self.assertNotIn("SENSITIVE_TOKEN",repr(out))

    def test_classifies_sender_token_mismatch(self):
        raw=json.dumps({"error":{"status":"PERMISSION_DENIED","details":[{
            "@type":"type.googleapis.com/google.firebase.fcm.v1.FcmError",
            "errorCode":"SENDER_ID_MISMATCH"}]}}).encode()
        result=diagnose.safe_fcm_error(raw)
        self.assertEqual(result["fcm_code"],"SENDER_ID_MISMATCH")

    def test_handles_invalid_and_untrusted_google_error_values(self):
        for response in (b"not json", b"[]", b"null",
                         b'{"error":{"status":"RAW_SECRET","details":[{"errorCode":"UNKNOWN_TOKEN_SECRET"}]}}'):
            with self.subTest(response=response):
                got=diagnose.safe_fcm_error(response)
                self.assertEqual(set(got),{"fcm_status","fcm_code","google_reason"})
                self.assertNotIn("SECRET",repr(got))

    def test_validation_is_non_delivering_and_scoped(self):
        import inspect
        source=inspect.getsource(diagnose.perform)
        self.assertIn('payload["validate_only"]=True',source)
        self.assertIn('os.setuid(account.pw_uid)',source)
        self.assertIn('sys.path.insert(0,str(BASE))',source)
        self.assertIn('GOOGLE_REQUEST_DID_NOT_SEND_A_NOTIFICATION',source)
        self.assertNotIn('print(token)',source)
        self.assertEqual(diagnose.SCOPED_ENV,{
            'EPIMEDIAHUB_ADMIN_FCM_PROJECT_ID','GOOGLE_APPLICATION_CREDENTIALS'})

if __name__=="__main__": unittest.main()

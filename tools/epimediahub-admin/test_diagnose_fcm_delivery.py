"""Offline regression tests: never print Firebase credentials, response messages, or tokens."""
import json
import unittest
import urllib.error

import diagnose_fcm_delivery as subject

class FcmDeliveryDiagnosisTests(unittest.TestCase):
    def test_public_google_error_status_and_fcm_code(self):
        data={"error":{
            "status":"PERMISSION_DENIED",
            "message":"DONOTEXPOSE_PRIVATE_ACCOUNT_OR_TOKEN",
            "details":[{"@type":"type.googleapis.com/google.rpc.ErrorInfo",
                        "reason":"SERVICE_DISABLED",
                        "metadata":{"service":"SECRET_SERVICE"}}]}}
        result=subject.category(data)
        self.assertEqual(result["google_status"],"PERMISSION_DENIED")
        self.assertEqual(result["google_reason"],"SERVICE_DISABLED")
        self.assertNotIn("DONOTEXPOSE",str(result))
        self.assertNotIn("SECRET_SERVICE",str(result))

    def test_google_fcm_sender_id_mismatch(self):
        data={"error":{
            "status":"PERMISSION_DENIED","message":"SECRET",
            "details":[{"@type":"type.googleapis.com/google.firebase.fcm.v1.FcmError",
                        "errorCode":"SENDER_ID_MISMATCH"}]}}
        result=subject.category(data)
        self.assertEqual(result["fcm_error"],"SENDER_ID_MISMATCH")

    def test_expired_token_classification(self):
        data={"error":{
            "status":"NOT_FOUND",
            "details":[{"@type":"type.googleapis.com/google.firebase.fcm.v1.FcmError",
                        "errorCode":"UNREGISTERED"}]}}
        self.assertEqual(subject.category(data)["fcm_error"],"UNREGISTERED")

    def test_unknown_data_never_leaked(self):
        secret="my-secret-token-123"
        payload={"error":{
            "status":secret,
            "message":secret,
            "details":[{"@type":"type.googleapis.com/google.firebase.fcm.v1.FcmError",
                        "errorCode":secret},
                       {"@type":"type.googleapis.com/google.rpc.ErrorInfo",
                        "reason":secret,
                        "domain":secret}]}}
        self.assertNotIn(secret,str(subject.category(payload)))
        self.assertNotIn(secret,str(subject.category({"error":[] })))
        self.assertNotIn(secret,str(subject.category({"something": secret})))

    def test_http_error_exception_is_classified(self):
        error=urllib.error.URLError("SECRET_REMOTE_PROVIDER_URL")
        self.assertEqual(subject.classify_exception(error),"GOOGLE_NETWORK_OR_DNS_FAILURE")
        self.assertNotIn("SECRET",subject.classify_exception(error))

    def test_no_child_request_on_import(self):
        self.assertTrue(callable(subject.main))
        self.assertTrue(callable(subject.category))
        self.assertIn("--service-probe",subject.main.__code__.co_consts.__str__())

if __name__=="__main__":
    unittest.main()

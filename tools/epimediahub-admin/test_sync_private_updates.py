"""Private Admin release sync never forwards GitHub tokens or trusts arbitrary archives."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

import sync_private_updates as sync


class SyncTests(unittest.TestCase):
    def test_only_completed_main_manual_signed_workflow_is_selected(self):
        requests=[]
        def fake(token,path):
            requests.append(path)
            if path.endswith("/runs?branch=main&status=success&per_page=10"):
                return {"workflow_runs":[
                    {"id":1,"name":sync.WORKFLOW,"head_branch":"dev",
                     "event":"workflow_dispatch","status":"completed","conclusion":"success"},
                    {"id":2,"name":"EpiMediaHub Admin private signed release",
                     "head_branch":"main","event":"workflow_dispatch",
                     "status":"completed","conclusion":"success"}]}
            return {"artifacts":[{"id":123,"name":sync.ARTIFACT,
                   "expired":False,"size_in_bytes":4000}]}
        with mock.patch.object(sync,"json_endpoint",side_effect=fake):
            self.assertEqual(sync.latest_signed_artifact("fake"),123)
        self.assertFalse(any("/runs/1/" in p for p in requests))

    def test_private_archive_accepts_exact_two_names(self):
        with tempfile.TemporaryDirectory() as temp:
            def pack(names):
                buffer=io.BytesIO()
                with zipfile.ZipFile(buffer,"w") as archive:
                    for name in names:
                        archive.writestr(name,b"x"*1024)
                return buffer.getvalue()
            sync.unpack_safe(pack(["current.apk","current.json"]),Path(temp))
            self.assertEqual((Path(temp)/"current.apk").stat().st_size,1024)
            with self.assertRaises(ValueError):
                sync.unpack_safe(pack(["current.apk","../secrets"]),Path(temp))


if __name__=="__main__":
    unittest.main()

"""Private Admin release publication never exposes artifacts publicly."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

import publish_private_release as publisher
from mobile_updates import read_release


class TestPrivateAdminPublisher(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.bundle=self.root/"signed-ci-bundle"
        self.bundle.mkdir()
        self.admin=self.root/"admin-mobile"
        self.admin.mkdir(mode=0o700)
        self.admin.chmod(0o700)
        self.payload=b"fake-file-not-an-apk"*1024
        (self.bundle/"current.apk").write_bytes(self.payload)
        self.meta={
            "package":"de.epimediahub.admin", "version_code":10,
            "version_name":"1.0.0","size_bytes":len(self.payload),
            "sha256":hashlib.sha256(self.payload).hexdigest()
        }
        self.write_manifest()

    def tearDown(self):
        self.temp.cleanup()

    def write_manifest(self):
        (self.bundle/"current.json").write_text(json.dumps(self.meta))

    def test_publish_private_monotonic_and_manifest_digest(self):
        result=publisher.publish(self.bundle,self.admin)
        self.assertFalse(result["public_release"])
        release=read_release(self.root)
        self.assertEqual(release.version_code,10)
        self.assertEqual(release.sha256,self.meta["sha256"])
        self.assertEqual((self.admin/"releases"/"current.apk").read_bytes(),self.payload)
        with self.assertRaises(ValueError):
            publisher.publish(self.bundle,self.admin)
        self.meta["version_code"]=11
        self.write_manifest()
        self.assertEqual(publisher.publish(self.bundle,self.admin)["version_code"],11)

    def test_corrupt_artifact_never_published(self):
        self.meta["sha256"]="0"*64
        self.write_manifest()
        with self.assertRaises(ValueError):
            publisher.publish(self.bundle,self.admin)
        self.assertFalse((self.admin/"releases"/"current.apk").exists())

    def test_invalid_package_and_symlinks_not_allowed(self):
        self.meta["package"]="de.epimediahub.app"
        self.write_manifest()
        with self.assertRaises(ValueError):
            publisher.publish(self.bundle,self.admin)
        self.meta["package"]="de.epimediahub.admin"
        self.write_manifest()
        (self.bundle/"current.apk").unlink()
        (self.bundle/"current.apk").symlink_to(self.root/"nonexistent")
        with self.assertRaises(PermissionError):
            publisher.publish(self.bundle,self.admin)


if __name__=="__main__":
    unittest.main()

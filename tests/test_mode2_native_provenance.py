from __future__ import annotations
import hashlib
import tempfile
import unittest
from pathlib import Path
from mcp_adobe.mode2_native_provenance import verify_native_copy_files


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.test_dir = self.root / "mode2-isolated"
        self.test_dir.mkdir()
        self.origin = self.root / "panda.xd"
        self.copy = self.test_dir / "panda-copy.xd"
        self.original_bytes = b"fake-native-file-for-guard-test-only"
        self.origin.write_bytes(self.original_bytes)
        self.copy.write_bytes(self.original_bytes)
        self.digest = hashlib.sha256(self.original_bytes).hexdigest()
        self.args = dict(origin_path=str(self.origin), copy_path=str(self.copy),
                         allowed_test_directory=str(self.test_dir), expected_sha256=self.digest)

    def test_matching_isolated_copy_passes_without_host_authorization(self):
        result = verify_native_copy_files(**self.args)
        self.assertTrue(result["verified"])
        self.assertFalse(result["live_mutation_authorized"])
        self.assertFalse(result["host_active_document_verified"])
        self.assertFalse(result["undo_capability_verified"])

    def test_changed_copy_rejected(self):
        self.copy.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "size mismatch"):
            verify_native_copy_files(**self.args)

    def test_wrong_digest_and_wrong_directory_rejected(self):
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            verify_native_copy_files(**{**self.args, "expected_sha256": "0" * 64})
        outside = self.root / "not-inside.xd"
        outside.write_bytes(self.original_bytes)
        with self.assertRaisesRegex(ValueError, "outside dedicated"):
            verify_native_copy_files(**{**self.args, "copy_path": str(outside)})

    def test_self_copy_and_invalid_paths_rejected(self):
        with self.assertRaises(ValueError):
            verify_native_copy_files(**{**self.args, "copy_path": str(self.origin)})
        with self.assertRaisesRegex(ValueError, "absolute"):
            verify_native_copy_files(**{**self.args, "copy_path": "relative.xd"})

    def test_symlink_rejected(self):
        link = self.test_dir / "linked.xd"
        try:
            link.symlink_to(self.origin)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ValueError, "symlinks"):
            verify_native_copy_files(**{**self.args, "copy_path": str(link)})


if __name__ == "__main__":
    unittest.main()

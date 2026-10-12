"""Fail closed when known-good Adobe adapter/plugin source changes silently.

To intentionally upgrade one locked component:
  - re-run its unit tests and live host/native readback;
  - update its git_blob_sha in contracts/adobe_connection_goldens.json;
  - document old/new SHA, reason, rollback and timings in the PR.
This is a source gate; deployment hash readback is a separate acceptance gate.
"""
from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "contracts" / "adobe_connection_goldens.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


class AdobeConnectionGoldenSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_goldens_are_unique_reviewed_source_paths(self):
        self.assertEqual(self.baseline["schema"], "mcp-adobe-golden-baseline/v1")
        self.assertTrue(self.baseline["baseline_ref"])
        items = self.baseline["locked"]
        self.assertGreaterEqual(len(items), 7)
        paths = [p["path"] for p in items]
        self.assertEqual(len(set(paths)), len(paths))
        self.assertTrue(any("adobe-xd-plugin/main.js" == p for p in paths))
        self.assertTrue(any("illustrator_cep.py" in p for p in paths))
        self.assertTrue(any(p.endswith("photoshop.py") for p in paths))
        for p in items:
            path = p["path"]
            self.assertFalse(path.startswith("/"))
            self.assertNotIn("..", Path(path).parts)
            self.assertTrue(SHA_RE.fullmatch(p["git_blob_sha"]), path)
            self.assertIsInstance(p["evidence_run"], int, path)
            self.assertGreater(p["evidence_run"], 1)
            self.assertTrue(p["verification_scope"], path)

    def test_protected_known_good_code_matches_pinned_blobs(self):
        for p in self.baseline["locked"]:
            with self.subTest(path=p["path"]):
                source = ROOT / p["path"]
                self.assertTrue(source.is_file(), p["path"])
                self.assertEqual(
                    git_blob_sha(source.read_bytes()),
                    p["git_blob_sha"],
                    "GOLDEN_SOURCE_CHANGED: "
                    + p["path"]
                    + "; preserve proven code; update baseline only after explicit review, "
                    + "live readback and rollback checkpoint",
                )

    def test_latency_reference_never_claims_unmeasured_e2e(self):
        metrics = self.baseline["latency_reference"]
        self.assertEqual(metrics["serial_ai_xd_ps_one_rectangle_status"], "NOT_YET_ACCEPTED")
        self.assertIn("NOT full E2E", metrics["scope"])
        for key in ("xd_health", "xd_scenegraph"):
            reference = metrics[key]
            self.assertEqual(reference["samples"], 30)
            self.assertGreater(reference["p95_ms"], reference["p50_ms"])
            self.assertGreater(reference["p50_ms"], 0)


if __name__ == "__main__":
    unittest.main()

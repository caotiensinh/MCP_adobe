"""Contract gate for the XD Fast Session live benchmark and MRCAO workflow."""
import ast
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/adobe_fast_session_live_probe.py"
WORKFLOW=ROOT/".github/workflows/adobe-fast-session-live-readonly.yml"

class LiveProbeContractTests(unittest.TestCase):
    def test_script_compiles(self):
        ast.parse(SCRIPT.read_text(encoding="utf8"),filename=str(SCRIPT))

    def test_only_xd_warm_host_is_accepted(self):
        source=SCRIPT.read_text(encoding="utf8")
        self.assertIn('if app!="xd": raise RuntimeError',source)
        self.assertIn('snapshot.get("complete") is True',source)
        self.assertIn('snapshot.get("document_id")',source)
        self.assertIn('session.trusted_observe',source)

    def test_workflow_guard_is_read_only_exclusive(self):
        content=WORKFLOW.read_text(encoding="utf8")
        self.assertIn("workflow_dispatch:",content)
        self.assertIn("options: [xd]",content)
        self.assertIn("adobe-panda-desktop-exclusive",content)
        self.assertIn("OTHER_ADOBE_ACTIVE",content)
        self.assertIn("WRONG_HOST_SESSION",content)
        self.assertIn("GATEWAY_NOT_UNIQUE",content)
        self.assertNotIn("workflow_dispatch: {}",content)
        self.assertNotIn("creative_write",content)
        self.assertNotIn("force-kill",content)

    def test_runtime_write_not_enabled(self):
        src=(ROOT/"src/mcp_adobe/fast_session.py").read_text(encoding="utf8")
        self.assertIn('write gated until durable journal',src)
        self.assertIn('cache_allowlist=()',src)

if __name__=="__main__":
    unittest.main()

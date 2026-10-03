from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == "nt", "Windows bootstrap smoke requires Windows")
class WindowsFullBootstrapTests(unittest.TestCase):
    def test_full_bootstrap_with_existing_ci_toolchain(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        script = repo / "scripts" / "install_windows.ps1"
        uv = shutil.which("uv")
        node = shutil.which("node")
        npx = shutil.which("npx")
        self.assertIsNotNone(uv, "CI must provide uv before full bootstrap smoke")
        self.assertIsNotNone(node, "CI must provide node before full bootstrap smoke")
        self.assertIsNotNone(npx, "CI must provide npx before full bootstrap smoke")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "configs"
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-PythonVersion",
                    "3.12",
                    "-UvCommandPath",
                    str(uv),
                    "-OutputDir",
                    str(output),
                ],
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            combined = completed.stdout + completed.stderr
            self.assertEqual(completed.returncode, 0, combined)
            self.assertIn("project=sync", completed.stdout)
            self.assertIn("smoke=mcp-adobe", completed.stdout)
            self.assertIn("smoke=oauth-preflight", completed.stdout)
            self.assertIn("smoke=remote-probe", completed.stdout)
            self.assertIn("result=PASS", completed.stdout)

            self.assertTrue((output / "claude-code.mcp.json").is_file())
            self.assertTrue((output / "codex.config.toml.snippet").is_file())
            self.assertTrue((output / "LOCAL_MCP_SETUP.txt").is_file())

            # Full bootstrap must remain local-only unless the caller separately
            # configures OAuth/tunneling. It must not emit or request secrets.
            self.assertNotIn("MCP_ADOBE_OAUTH_CLIENT_SECRET", combined)
            self.assertNotIn("Bearer ", combined)
            self.assertNotIn("New-NetFirewallRule", combined)


if __name__ == "__main__":
    unittest.main()

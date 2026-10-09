from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class WindowsInstallerTests(unittest.TestCase):
    def test_generate_configs_only_produces_shared_http_host_configs(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        script = repo / "scripts" / "install_windows.ps1"
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "configs"
            fake_uv = r"C:\Tools\uv.exe"
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-GenerateConfigsOnly",
                    "-UvCommandPath",
                    fake_uv,
                    "-OutputDir",
                    str(output),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("result=PASS generate-configs-only", completed.stdout)

            claude_path = output / "claude-code.mcp.json"
            codex_path = output / "codex.config.toml.snippet"
            instructions_path = output / "LOCAL_MCP_SETUP.txt"
            self.assertTrue(claude_path.is_file())
            self.assertTrue(codex_path.is_file())
            self.assertTrue(instructions_path.is_file())

            claude = json.loads(claude_path.read_text(encoding="utf-8-sig"))
            server = claude["mcpServers"]["adobe-creative"]
            self.assertEqual(server["type"], "http")
            self.assertEqual(server["url"], "http://127.0.0.1:8787/mcp")
            self.assertNotIn("command", server)
            self.assertNotIn("args", server)

            codex = codex_path.read_text(encoding="utf-8-sig")
            self.assertIn("[mcp_servers.adobe_creative]", codex)
            self.assertIn('url = "http://127.0.0.1:8787/mcp"', codex)
            self.assertNotIn("command =", codex)

            instructions = instructions_path.read_text(encoding="utf-8-sig")
            self.assertIn("claude mcp add --transport http", instructions)
            self.assertIn("codex mcp add adobe-creative --url http://127.0.0.1:8787/mcp", instructions)
            self.assertIn("persistent local host", instructions)
            self.assertNotIn("MCP_ADOBE_OAUTH_CLIENT_SECRET", instructions)
            self.assertNotIn("Bearer ", instructions)


if __name__ == "__main__":
    unittest.main()

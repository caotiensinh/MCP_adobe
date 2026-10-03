from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class WindowsInstallerTests(unittest.TestCase):
    def test_generate_configs_only_produces_claude_and_codex_stdio_configs(self) -> None:
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
            self.assertEqual(server["type"], "stdio")
            self.assertEqual(server["command"], fake_uv)
            self.assertEqual(server["args"][0:2], ["run", "--directory"])
            self.assertIn("mcp-adobe", server["args"])
            self.assertEqual(server["args"][-2:], ["--transport", "stdio"])

            codex = codex_path.read_text(encoding="utf-8-sig")
            self.assertIn("[mcp_servers.adobe_creative]", codex)
            self.assertIn('command = "C:\\\\Tools\\\\uv.exe"', codex)
            self.assertIn('"mcp-adobe"', codex)
            self.assertIn('"--transport", "stdio"', codex)

            instructions = instructions_path.read_text(encoding="utf-8-sig")
            self.assertIn("claude mcp add --transport stdio", instructions)
            self.assertIn("Codex:", instructions)
            self.assertNotIn("MCP_ADOBE_OAUTH_CLIENT_SECRET", instructions)
            self.assertNotIn("Bearer ", instructions)


if __name__ == "__main__":
    unittest.main()

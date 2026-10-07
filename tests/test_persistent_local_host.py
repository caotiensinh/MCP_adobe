from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


class PersistentLocalHostContractTests(unittest.TestCase):
    def setUp(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        self.script = (repo / "scripts" / "install_local_host.ps1").read_text(encoding="utf-8")
        self.windows = (repo / "scripts" / "install_windows.ps1").read_text(encoding="utf-8")

    def test_host_uses_one_streamable_http_gateway_and_prewarms_adobe_bridges(self) -> None:
        self.assertIn("--transport streamable-http", self.script)
        self.assertIn("--host 127.0.0.1", self.script)
        self.assertIn("--path /mcp", self.script)
        self.assertIn("--prewarm illustrator --prewarm xd", self.script)
        self.assertIn("GatewayPort = 8787", self.script)
        self.assertIn("IllustratorPort = 8081", self.script)
        self.assertIn("XdPort = 8765", self.script)

    def test_host_survives_github_runner_cleanup_and_restarts(self) -> None:
        self.assertIn("RUNNER_TRACKING_ID", self.script)
        self.assertIn("while ($true)", self.script)
        self.assertIn("restart in 3s", self.script)
        self.assertIn("host-wrapper.pid", self.script)

    def test_host_supports_controlled_stop_only_for_backend_upgrade(self) -> None:
        self.assertIn("[switch]$StopOnly", self.script)
        self.assertIn("if ($StopOnly)", self.script)
        self.assertIn('Write-Host "local_host_stop_only=PASS"', self.script)

    def test_installer_refuses_to_kill_unrelated_port_owner(self) -> None:
        self.assertIn("Refusing to stop unrelated process on MCP Adobe port", self.script)
        self.assertIn("illustrator_mcp\\.server", self.script)
        self.assertIn('venv\\Scripts\\mcp-adobe.exe', self.script)
        self.assertIn("ownedGatewayCommand", self.script)

    def test_main_windows_installer_enables_persistent_host_by_default(self) -> None:
        self.assertIn("[switch]$SkipPersistentHost", self.windows)
        self.assertIn('Write-Host "local_host=install"', self.windows)
        self.assertIn("install_local_host.ps1", self.windows)
        self.assertIn("if (-not $SkipPersistentHost)", self.windows)

    @unittest.skipUnless(os.name == "nt", "PowerShell parser validation requires Windows")
    def test_persistent_host_script_parses_as_powershell(self) -> None:
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "install_local_host.ps1"
        command = (
            "$tokens=$null;$errors=$null;"
            f"[System.Management.Automation.Language.Parser]::ParseFile('{script_path}',[ref]$tokens,[ref]$errors)|Out-Null;"
            "if($errors.Count){$errors|ForEach-Object{Write-Error $_.Message};exit 1}"
        )
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()

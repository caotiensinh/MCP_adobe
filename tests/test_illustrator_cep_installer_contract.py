from __future__ import annotations

import unittest
from pathlib import Path


class IllustratorCepInstallerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path(__file__).resolve().parents[1]
        self.backend_installer = (self.repo / "scripts" / "install_illustrator_cep_backend.ps1").read_text(
            encoding="utf-8"
        )
        self.windows_installer = (self.repo / "scripts" / "install_windows.ps1").read_text(
            encoding="utf-8"
        )

    def test_backend_installer_pins_proven_upstream_and_version(self) -> None:
        self.assertIn("jinkeda/Illustrator_MCP.git", self.backend_installer)
        self.assertIn("5d7a3edc8ebc89a0fc56b059e1311d3b2bfca815", self.backend_installer)
        self.assertIn('$ExpectedPackageVersion = "3.0.0"', self.backend_installer)
        self.assertIn('$ExtensionId = "com.illustrator.mcp.panel"', self.backend_installer)

    def test_backend_installer_fetches_only_the_pinned_commit(self) -> None:
        self.assertIn('"fetch", "--no-tags", "--depth=1", "origin", $UpstreamSha', self.backend_installer)
        self.assertIn('"checkout", "--detach", "FETCH_HEAD"', self.backend_installer)
        self.assertNotIn('"clone", "--no-checkout"', self.backend_installer)

    def test_backend_installer_matches_runtime_default_path(self) -> None:
        self.assertIn('"MCPAdobe\\illustrator-mcp"', self.backend_installer)
        self.assertIn('"venv\\Scripts\\python.exe"', self.backend_installer)
        runtime = (self.repo / "src" / "mcp_adobe" / "mcp_stdio.py").read_text(encoding="utf-8")
        self.assertIn('"MCPAdobe" / "illustrator-mcp" / "venv" / "Scripts" / "python.exe"', runtime)

    def test_installer_refuses_to_replace_a_running_bridge(self) -> None:
        self.assertIn("Get-NetTCPConnection -State Listen -LocalPort 8081", self.backend_installer)
        self.assertIn("Close the active Illustrator MCP bridge before installing", self.backend_installer)

    def test_installer_uses_staging_backup_and_rollback(self) -> None:
        self.assertIn(".staging.$nonce", self.backend_installer)
        self.assertIn('$previousRoot = "$InstallRoot.previous"', self.backend_installer)
        self.assertIn('$previousPanel = "$PanelTarget.previous"', self.backend_installer)
        self.assertIn("illustrator_backend=FAIL", self.backend_installer)
        self.assertIn("Move-Item -LiteralPath $previousPanel -Destination $PanelTarget", self.backend_installer)
        self.assertIn("Move-Item -LiteralPath $previousRoot -Destination $InstallRoot", self.backend_installer)

    def test_installer_validates_panel_before_and_after_install(self) -> None:
        self.assertIn("validate-panel.mjs", self.backend_installer)
        self.assertIn("Illustrator source CEP validation", self.backend_installer)
        self.assertIn("Illustrator staged CEP validation", self.backend_installer)
        self.assertIn("Installed Illustrator CEP validation", self.backend_installer)
        self.assertIn('"CSXS\\manifest.xml"', self.backend_installer)

    def test_installer_enables_panel_start_on_application_activate(self) -> None:
        self.assertIn("Enable-CepPanelAutoStart", self.backend_installer)
        self.assertIn("Test-CepPanelAutoStart", self.backend_installer)
        self.assertIn("<StartOn>", self.backend_installer)
        self.assertIn("<Event>applicationActivate</Event>", self.backend_installer)
        self.assertIn("<Event>com.adobe.csxs.events.ApplicationActivate</Event>", self.backend_installer)
        self.assertIn("Illustrator staged CEP auto-start", self.backend_installer)
        self.assertIn("Installed Illustrator CEP auto-start", self.backend_installer)

    def test_installer_replaces_react_entry_with_panel_context_compat_transport(self) -> None:
        self.assertIn("Install-CepPanelCompatTransport", self.backend_installer)
        self.assertIn("Test-CepPanelCompatTransport", self.backend_installer)
        self.assertIn("illustrator_cep_fallback_transport.html", self.backend_installer)
        self.assertIn("MCP_ADOBE_CEP_COMPAT_TRANSPORT_V1", self.backend_installer)
        self.assertIn("compat-v1", self.backend_installer)
        self.assertIn("./CSInterface.js", self.backend_installer)
        self.assertIn("bootstrap-relative CSInterface path leaked", self.backend_installer)
        self.assertIn("real panel transport must not recursively open itself", self.backend_installer)

    def test_installer_builds_missing_pinned_panel_dist(self) -> None:
        self.assertIn('"dist\\index.html"', self.backend_installer)
        self.assertIn('Invoke-Checked $npm @("ci", "--no-audit", "--no-fund")', self.backend_installer)
        self.assertIn('Invoke-Checked $npm @("run", "build")', self.backend_installer)
        self.assertIn("Illustrator CEP dist is absent at the pinned upstream SHA", self.backend_installer)
        self.assertIn("illustrator_cep_build=PASS", self.backend_installer)

    def test_main_windows_installer_installs_backend_by_default(self) -> None:
        self.assertIn("install_illustrator_cep_backend.ps1", self.windows_installer)
        self.assertIn('Write-Host "illustrator_backend=install"', self.windows_installer)
        self.assertIn("-PythonVersion $PythonVersion -UvCommandPath $uvExe", self.windows_installer)
        backend_call = self.windows_installer.index("install_illustrator_cep_backend.ps1")
        config_write = self.windows_installer.rindex("Write-ClientConfigs $uvExe")
        self.assertLess(backend_call, config_write)


if __name__ == "__main__":
    unittest.main()

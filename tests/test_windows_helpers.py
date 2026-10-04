from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "Windows PowerShell helper tests")
class WindowsHelperSyntaxTests(unittest.TestCase):
    def test_all_powershell_helpers_parse(self) -> None:
        scripts = sorted((ROOT / "scripts").glob("*.ps1"))
        self.assertTrue(scripts, "expected at least one PowerShell helper")

        failures: list[str] = []
        for script in scripts:
            escaped = str(script).replace("'", "''")
            command = (
                "$tokens=$null; $errors=$null; "
                f"[void][System.Management.Automation.Language.Parser]::ParseFile('{escaped}', [ref]$tokens, [ref]$errors); "
                "if ($errors.Count -gt 0) { "
                "$errors | ForEach-Object { Write-Error $_.Message }; exit 1 }"
            )
            result = subprocess.run(
                ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                failures.append(
                    f"{script.name}: rc={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
                )

        self.assertEqual(failures, [], "\n\n".join(failures))

    def test_xd_installer_discovers_modern_package_sandbox(self) -> None:
        installer = ROOT / "scripts" / "install_xd_plugin.ps1"
        with tempfile.TemporaryDirectory() as temp_dir:
            local_app_data = Path(temp_dir)
            local_state = (
                local_app_data
                / "Packages"
                / "Adobe.XD_testpublisher"
                / "LocalState"
            )
            local_state.mkdir(parents=True)

            env = os.environ.copy()
            env["LOCALAPPDATA"] = str(local_app_data)
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(installer),
                    "-NoReloadHint",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )

            self.assertEqual(
                result.returncode,
                0,
                f"stdout={result.stdout}\nstderr={result.stderr}",
            )
            destination = local_state / "develop" / "MCPAdobeBridge"
            self.assertTrue((destination / "manifest.json").is_file())
            self.assertTrue((destination / "main.js").is_file())
            self.assertIn("PASS: Adobe XD MCP bridge installed", result.stdout)


if __name__ == "__main__":
    unittest.main()

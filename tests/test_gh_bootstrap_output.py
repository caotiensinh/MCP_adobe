from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "Windows GitHub CLI bootstrap regression")
class GitHubCliBootstrapOutputTests(unittest.TestCase):
    def test_winget_diagnostics_do_not_contaminate_resolved_gh_path(self) -> None:
        dispatcher = ROOT / "scripts" / "dispatch_adobe_live_e2e.ps1"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            fake_gh = temp / "installed-gh.cmd"
            fake_winget = temp / "winget.cmd"
            fake_winget.write_text(
                "@echo off\r\n"
                "echo simulated winget installer diagnostic\r\n"
                ">\"%MCP_ADOBE_GH_PATH%\" echo @echo off\r\n"
                ">>\"%MCP_ADOBE_GH_PATH%\" echo if \"%%1\"==\"--version\" echo gh version 99.0.0\r\n"
                ">>\"%MCP_ADOBE_GH_PATH%\" echo exit /b 0\r\n"
                "exit /b 0\r\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["MCP_ADOBE_GH_PATH"] = str(fake_gh)
            env["ProgramFiles"] = str(temp / "program-files")
            env["ProgramFiles(x86)"] = str(temp / "program-files-x86")
            env["LOCALAPPDATA"] = str(temp / "local-app-data")
            system_root = Path(env.get("SystemRoot", r"C:\\Windows"))
            env["PATH"] = os.pathsep.join([str(temp), str(system_root / "System32"), str(system_root)])

            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(dispatcher),
                    "-BootstrapOnly",
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

            self.assertEqual(result.returncode, 0, f"stdout={result.stdout}\nstderr={result.stderr}")
            self.assertIn("simulated winget installer diagnostic", result.stdout)
            self.assertIn(f"GitHub CLI={fake_gh}", result.stdout)
            self.assertIn("gh version 99.0.0", result.stdout)
            self.assertIn("PASS: GitHub CLI bootstrap ready", result.stdout)


if __name__ == "__main__":
    unittest.main()

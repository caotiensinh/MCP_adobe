from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "Windows PowerShell parser test")
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


if __name__ == "__main__":
    unittest.main()

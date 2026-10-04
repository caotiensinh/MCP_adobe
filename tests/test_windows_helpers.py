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

    def test_live_dispatch_helper_builds_guarded_workflow_command(self) -> None:
        dispatcher = ROOT / "scripts" / "dispatch_adobe_live_e2e.ps1"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            gh_log = temp / "gh.log"
            fake_gh = temp / "gh.cmd"
            fake_gh.write_text(
                "@echo off\r\n"
                ">>\"%GH_LOG%\" echo %*\r\n"
                "exit /b 0\r\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["GH_LOG"] = str(gh_log)
            env["PATH"] = str(temp) + os.pathsep + env.get("PATH", "")
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
                    "-XdWrite",
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
            calls = gh_log.read_text(encoding="utf-8", errors="replace")
            self.assertIn("auth status --hostname github.com", calls)
            self.assertIn(
                "workflow run adobe-windows-e2e.yml --repo caotiensinh/MCP_adobe --ref main",
                calls,
            )
            self.assertIn("run_adobe_live=true", calls)
            self.assertIn("xd_live=true", calls)
            self.assertIn("xd_write=true", calls)
            self.assertIn("PASS: Adobe live E2E workflow dispatched", result.stdout)

    def test_live_dispatch_rejects_xd_write_when_xd_live_is_disabled(self) -> None:
        dispatcher = ROOT / "scripts" / "dispatch_adobe_live_e2e.ps1"
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
                "-NoXdLive",
                "-XdWrite",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        combined = result.stdout + result.stderr
        self.assertIn("-XdWrite requires XD live E2E", combined)

    def test_one_command_wrapper_preflights_github_before_interactive_guard(self) -> None:
        launcher = ROOT / "scripts" / "run_adobe_live_e2e.ps1"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            gh_log = temp / "gh.log"
            fake_gh = temp / "gh.cmd"
            fake_gh.write_text(
                "@echo off\r\n"
                ">>\"%GH_LOG%\" echo %*\r\n"
                "exit /b 0\r\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["GH_LOG"] = str(gh_log)
            env["PATH"] = str(temp) + os.pathsep + env.get("PATH", "")
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(launcher),
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

            self.assertNotEqual(result.returncode, 0)
            calls = gh_log.read_text(encoding="utf-8", errors="replace")
            self.assertIn("auth status --hostname github.com", calls)
            self.assertNotIn("workflow run", calls)
            self.assertIn("PASS: GitHub CLI live-E2E dispatch preflight", result.stdout)
            combined = result.stdout + result.stderr
            self.assertIn("logged-in MRCAO desktop session", combined)

    def test_live_dispatch_uses_explicit_gh_path(self) -> None:
        dispatcher = ROOT / "scripts" / "dispatch_adobe_live_e2e.ps1"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            gh_log = temp / "gh.log"
            fake_gh = temp / "portable-gh.cmd"
            fake_gh.write_text(
                "@echo off\r\n"
                ">>\"%GH_LOG%\" echo %*\r\n"
                "exit /b 0\r\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["GH_LOG"] = str(gh_log)
            env["MCP_ADOBE_GH_PATH"] = str(fake_gh)
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
                    "-PreflightOnly",
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
            self.assertIn(f"GitHub CLI={fake_gh}", result.stdout)
            self.assertIn("PASS: GitHub CLI live-E2E dispatch preflight", result.stdout)
            self.assertIn("auth status --hostname github.com", gh_log.read_text(encoding="utf-8"))

    def test_live_dispatch_bootstraps_gh_with_winget_when_missing(self) -> None:
        dispatcher = ROOT / "scripts" / "dispatch_adobe_live_e2e.ps1"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            fake_gh = temp / "installed-gh.cmd"
            winget_log = temp / "winget.log"
            fake_winget = temp / "winget.cmd"
            fake_winget.write_text(
                "@echo off\r\n"
                ">>\"%WINGET_LOG%\" echo %*\r\n"
                ">\"%MCP_ADOBE_GH_PATH%\" echo @echo off\r\n"
                ">>\"%MCP_ADOBE_GH_PATH%\" echo exit /b 0\r\n"
                "exit /b 0\r\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["MCP_ADOBE_GH_PATH"] = str(fake_gh)
            env["WINGET_LOG"] = str(winget_log)
            env["ProgramFiles"] = str(temp / "program-files")
            env["ProgramFiles(x86)"] = str(temp / "program-files-x86")
            env["LOCALAPPDATA"] = str(temp / "local-app-data")
            system_root = Path(env.get("SystemRoot", r"C:\Windows"))
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
                    "-PreflightOnly",
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
            self.assertTrue(fake_gh.is_file())
            winget_calls = winget_log.read_text(encoding="utf-8", errors="replace")
            self.assertIn("install --id GitHub.cli --exact --source winget", winget_calls)
            self.assertIn("PASS: GitHub CLI installed", result.stdout)
            self.assertIn("PASS: GitHub CLI live-E2E dispatch preflight", result.stdout)


if __name__ == "__main__":
    unittest.main()

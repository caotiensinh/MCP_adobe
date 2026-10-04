from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InteractiveWorkspaceOwnershipTests(unittest.TestCase):
    def test_interactive_runner_repairs_workspace_before_launch(self) -> None:
        script = (ROOT / "scripts" / "start_adobe_runner_interactive.ps1").read_text(
            encoding="utf-8"
        )

        repair_call = "Repair-InteractiveWorkspaceOwnership -Root $RunnerRoot"
        launch_call = "Start-Process -FilePath 'cmd.exe'"
        self.assertIn("'/setowner'", script)
        self.assertIn("'/grant:r'", script)
        self.assertIn("safe.directory", script)
        self.assertIn(repair_call, script)
        self.assertIn(launch_call, script)
        self.assertLess(script.index(repair_call), script.index(launch_call))

    def test_repair_targets_only_mcp_adobe_worktree(self) -> None:
        script = (ROOT / "scripts" / "start_adobe_runner_interactive.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("Join-Path $Root '_work\\MCP_adobe'", script)
        self.assertNotIn("_work\\AWS", script)
        self.assertNotIn("_work\\workspace", script)


if __name__ == "__main__":
    unittest.main()

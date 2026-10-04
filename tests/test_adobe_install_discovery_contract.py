from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AdobeInstallDiscoveryContractTests(unittest.TestCase):
    def test_prepare_helper_prefers_process_and_shortcut_discovery(self) -> None:
        text = (ROOT / "scripts" / "prepare_adobe_live_e2e.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-Process -Name $ProcessName", text)
        self.assertIn("discovery=running-process", text)
        self.assertIn("WScript.Shell", text)
        self.assertIn("discovery=start-menu-shortcut", text)
        self.assertIn("-ProcessName 'Photoshop' -ExeName 'Photoshop.exe'", text)
        self.assertIn("-ProcessName 'Illustrator' -ExeName 'Illustrator.exe'", text)

    def test_workflow_inventory_uses_same_custom_install_evidence(self) -> None:
        text = (ROOT / ".github" / "workflows" / "adobe-windows-e2e.yml").read_text(encoding="utf-8")
        self.assertIn("Get-Process -Name $ProcessName", text)
        self.assertIn("discovery=running-process", text)
        self.assertIn("WScript.Shell", text)
        self.assertIn("discovery=start-menu-shortcut", text)
        self.assertIn("photoshop_found=", text)
        self.assertIn("illustrator_found=", text)


if __name__ == "__main__":
    unittest.main()

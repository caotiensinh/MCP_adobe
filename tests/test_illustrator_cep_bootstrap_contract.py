from __future__ import annotations

import unittest
from pathlib import Path


class IllustratorCepBootstrapContractTests(unittest.TestCase):
    def setUp(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        self.script = (repo / "scripts" / "ensure_illustrator_cep_bootstrap.ps1").read_text(
            encoding="utf-8"
        )

    def test_bootstrap_is_invisible_and_started_by_adobe_events(self) -> None:
        self.assertIn('com.illustrator.mcp.bootstrap', self.script)
        self.assertIn('<AutoVisible>false</AutoVisible>', self.script)
        self.assertIn('<Type>Custom</Type>', self.script)
        self.assertIn('<Event>applicationActivate</Event>', self.script)
        self.assertIn('<Event>com.adobe.csxs.events.ApplicationActivate</Event>', self.script)
        self.assertIn('<Event>com.adobe.csxs.events.ApplicationInitialized</Event>', self.script)

    def test_bootstrap_uses_cep_api_to_open_existing_panel(self) -> None:
        self.assertIn('requestOpenExtension', self.script)
        self.assertIn('com.illustrator.mcp.panel', self.script)
        self.assertIn('../dist/CSInterface.js', self.script)

    def test_patch_is_idempotent_and_has_verify_only_mode(self) -> None:
        self.assertIn('[switch]$VerifyOnly', self.script)
        self.assertIn('Test-BootstrapContract', self.script)
        self.assertIn('illustrator_cep_bootstrap=VERIFY_PASS', self.script)
        self.assertIn('illustrator_cep_bootstrap=PATCH_PASS', self.script)


if __name__ == "__main__":
    unittest.main()

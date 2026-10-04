from __future__ import annotations

import unittest
from pathlib import Path


class IllustratorCepWindowsBootstrapContractTests(unittest.TestCase):
    def test_windows_bootstrap_keeps_illustrator_cep_opt_in(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        text = (repo / "scripts" / "install_windows.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$InstallIllustratorCep", text)
        self.assertIn("[switch]$EnableUnsignedIllustratorCepDebug", text)
        self.assertIn('Join-Path $PSScriptRoot "install_illustrator_cep.ps1"', text)
        self.assertIn("$EnableUnsignedIllustratorCepDebug -and -not $InstallIllustratorCep", text)
        self.assertIn('$installerArgs += "-EnableUnsignedDebug"', text)

    def test_dedicated_installer_defaults_to_no_debug_mode_mutation(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        text = (repo / "scripts" / "install_illustrator_cep.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$EnableUnsignedDebug", text)
        self.assertIn("if ($EnableUnsignedDebug)", text)
        self.assertIn("illustrator_cep_unsigned_debug=unchanged", text)
        self.assertIn("5d7a3edc8ebc89a0fc56b059e1311d3b2bfca815", text)
        self.assertIn("prepare_illustrator_cep.py", text)


if __name__ == "__main__":
    unittest.main()

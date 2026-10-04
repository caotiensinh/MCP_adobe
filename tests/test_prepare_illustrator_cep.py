from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "scripts" / "prepare_illustrator_cep.py"
SPEC = importlib.util.spec_from_file_location("prepare_illustrator_cep", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class IllustratorCepPreparationTests(unittest.TestCase):
    def _fixture(self, root: Path) -> None:
        (root / "CSXS").mkdir(parents=True)
        (root / "dist" / "assets").mkdir(parents=True)
        (root / "CSXS" / "manifest.xml").write_text(
            "<Extension><AutoVisible>true</AutoVisible></Extension>", encoding="utf-8"
        )
        (root / "dist" / "index.html").write_text(
            '<html><head><script type="module" crossorigin src="./assets/index.js"></script>'
            '</head><body><div id="root"></div></body></html>',
            encoding="utf-8",
        )

    def test_prepare_adds_starton_and_deferred_classic_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            result = MODULE.prepare(root)
            self.assertTrue(result["manifest_changed"])
            self.assertTrue(result["index_changed"])

            manifest = (root / "CSXS" / "manifest.xml").read_text(encoding="utf-8")
            index = (root / "dist" / "index.html").read_text(encoding="utf-8")
            self.assertIn("<StartOn>", manifest)
            self.assertIn("applicationActivate", manifest)
            self.assertIn('<script defer src="./assets/index.js"></script>', index)
            self.assertNotIn('type="module"', index)
            self.assertNotIn("mcp_adobe_cep_inline_probe", index)

    def test_prepare_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            MODULE.prepare(root)
            first_manifest = (root / "CSXS" / "manifest.xml").read_bytes()
            first_index = (root / "dist" / "index.html").read_bytes()
            result = MODULE.prepare(root)
            self.assertFalse(result["manifest_changed"])
            self.assertFalse(result["index_changed"])
            self.assertEqual(first_manifest, (root / "CSXS" / "manifest.xml").read_bytes())
            self.assertEqual(first_index, (root / "dist" / "index.html").read_bytes())

    def test_prepare_fails_closed_on_unexpected_vite_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            (root / "dist" / "index.html").write_text(
                '<html><body><div id="root"></div><script src="./assets/index.js"></script></body></html>',
                encoding="utf-8",
            )
            with self.assertRaises(MODULE.CepPreparationError):
                MODULE.prepare(root)

    def test_prepare_rejects_diagnostic_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            index = root / "dist" / "index.html"
            index.write_text(index.read_text(encoding="utf-8") + "mcp_adobe_cep_inline_probe", encoding="utf-8")
            with self.assertRaises(MODULE.CepPreparationError):
                MODULE.prepare(root)


if __name__ == "__main__":
    unittest.main()

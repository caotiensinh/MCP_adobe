"""Real local PDF path parsing and negative geometry cases. No Adobe GUI."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import panda_illustrator_native_pdf_audit as audit


class NativeIllustratorGeometryTests(unittest.TestCase):
    def setUp(self):
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF not installed")
        self.fitz = fitz
        self.folder = tempfile.TemporaryDirectory()
        self.base = Path(self.folder.name) / "one.ai"
        self.two = Path(self.folder.name) / "two.ai"
        self._make_pdf(self.base, False)
        self._make_pdf(self.two, True)

    def tearDown(self):
        self.folder.cleanup()

    def _make_pdf(self, second):
        fitz = self.fitz
        doc = fitz.open()
        page = doc.new_page(width=880, height=1265)
        page.draw_rect(fitz.Rect(0, 0, 880, 1265), color=None, fill=(.74, 0, 0))
        if second:
            page.draw_rect(fitz.Rect(0, 0, 880, 700), color=None, fill=(.96, .18, .03))
        doc.save(str(self.two if second else self.base))
        doc.close()

    def test_real_persisted_second_rectangle_detected(self):
        one = audit.drawing_geometry(self.base)
        two = audit.drawing_geometry(self.two)
        result = audit.comparable_second_vector(one, two)
        self.assertTrue(result["verified"])
        self.assertEqual(result["baseline_drawing_count"], 1)
        self.assertEqual(result["target_drawing_count"], 2)

    def test_equal_geometry_is_not_claimed_as_extra_component(self):
        same = audit.drawing_geometry(self.base)
        result = audit.comparable_second_vector(same, same)
        self.assertFalse(result["verified"])

    def test_second_wrong_size_is_not_claimed_as_upper_field(self):
        self._make_pdf(self.two, False)
        fitz = self.fitz
        doc = fitz.open(str(self.two))
        doc[0].draw_rect(fitz.Rect(0, 0, 300, 90), color=None, fill=(1, .1, .1))
        other = Path(self.folder.name)/"wrong.ai"
        doc.save(str(other))
        doc.close()
        result = audit.comparable_second_vector(audit.drawing_geometry(self.base), audit.drawing_geometry(other))
        self.assertFalse(result["verified"])

    def test_non_pdf_does_not_falsely_verify_vector(self):
        corrupted = Path(self.folder.name) / "corrupt.ai"
        corrupted.write_bytes(b"This is not Adobe Illustrator PDF")
        result = audit.comparable_second_vector(
            audit.drawing_geometry(self.base), audit.drawing_geometry(corrupted)
        )
        self.assertFalse(result["verified"])

    def test_modified_source_sha_blocks_full_audit(self):
        with self.assertRaisesRegex(RuntimeError,"NATIVE_SHA_CHANGED"):
            audit.inspect(self.base, self.two)

if __name__ == "__main__":
    unittest.main()

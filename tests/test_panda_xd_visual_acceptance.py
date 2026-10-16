"""Behavioral tests of XD visual gate, not a substitute for real Adobe export."""
import tempfile
import unittest
from pathlib import Path
from PIL import Image,ImageDraw
from panda_xd_visual_acceptance import audit

class VisualPandaGateTests(unittest.TestCase):
    def test_empty_scene_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/"empty.png"
            Image.new("RGB",(1920,1080),(242,249,248)).save(target)
            with self.assertRaisesRegex(RuntimeError,"XD_PANDA_VISUAL_CONTENT_FAIL"):
                audit(target)

    def test_required_regions_with_real_pixels_pass(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/"regions.png"
            image=Image.new("RGB",(1920,1080),(242,249,248))
            pen=ImageDraw.Draw(image)
            pen.ellipse((300,260,580,575),fill=(39,45,49))
            pen.ellipse((320,205,560,388),fill=(247,246,235))
            pen.ellipse((350,360,530,542),fill=(247,246,235))
            pen.ellipse((540,350,602,378),fill=(74,153,65))
            pen.rectangle((330,80,555,183),fill=(220,173,108))
            image.save(target)
            audit(target)

    def test_wrong_image_dimensions_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/"small.png"
            Image.new("RGB",(100,100),"white").save(target)
            with self.assertRaisesRegex(RuntimeError,"XD_PANDA_VISUAL_WRONG"):
                audit(target)

if __name__=="__main__":
    unittest.main()

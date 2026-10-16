"""Behavioral unit tests; synthetic pixels do NOT count as Adobe E2E."""
import tempfile
import unittest
from pathlib import Path
from PIL import Image,ImageDraw
from scripts.panda_red_poster_visual_acceptance import audit

class PandaRedPosterVisualGateTests(unittest.TestCase):
    def make(self, folder,kind):
        file=Path(folder)/(kind+".png")
        img=Image.new("RGB",(880,1265),(221,8,5))
        if kind=="valid_parts":
            pen=ImageDraw.Draw(img)
            pen.ellipse((200,90,710,705),fill=(36,35,37))
            pen.ellipse((350,105,605,365),fill=(237,235,223))
            pen.ellipse((375,350,605,600),fill=(247,242,229))
            pen.rectangle((225,530,810,685),fill=(30,27,28))
            pen.line([(20,165),(325,0)],fill=(184,127,62),width=15)
            pen.rectangle((100,810,770,885),fill=(255,255,254))
            pen.rectangle((350,1070,495,1210),fill=(255,255,254))
        elif kind=="old_green_garden":
            ImageDraw.Draw(img).rectangle((0,0,880,750),fill=(160,205,147))
        img.save(file)
        return file

    def test_detailed_red_scene_pixels_are_recognized(self):
        with tempfile.TemporaryDirectory() as td:
            checks=audit(self.make(td,"valid_parts"))
            self.assertTrue(all(c["passed"] for c in checks.values()))

    def test_solid_red_canvas_is_not_a_poster(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError,"PANDA_RED_POSTER_VISUAL_FAIL"):
                audit(self.make(td,"red_only"))

    def test_old_green_garden_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError,"PANDA_RED_POSTER_VISUAL_FAIL"):
                audit(self.make(td,"old_green_garden"))

    def test_wrong_image_ratio_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/"wrong.png"
            Image.new("RGB",(880,640),(220,6,5)).save(file)
            with self.assertRaisesRegex(RuntimeError,"PANDA_RED_WRONG_SIZE_OR_FORMAT"):
                audit(file)

if __name__=="__main__":
    unittest.main()

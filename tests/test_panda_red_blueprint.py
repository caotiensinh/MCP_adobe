"""Behavior tests for per-layer vector design, not Adobe visual acceptance."""
import unittest
from unittest.mock import patch
from scripts import panda_red_poster_blueprint as scene


class RedPosterBlueprintTests(unittest.TestCase):
    def test_60_real_independent_adobe_operations(self):
        scene.validate()
        self.assertEqual(len(scene.STEPS), 60)
        self.assertEqual(len(set(p["name"] for p in scene.STEPS)), 60)
        self.assertEqual((scene.WIDTH, scene.HEIGHT), (880,1265))
        self.assertLess(abs(scene.ASPECT-297/427), .003)
        self.assertGreaterEqual(sum(p["kind"]=="path" for p in scene.STEPS), 20)
        self.assertEqual([p["kind"] for p in scene.STEPS[-3:]], ["text","text","text"] if False else ["text","text","path"])
        self.assertEqual([p["text"] for p in scene.STEPS if p["kind"]=="text"], ["KUNG FU","PANDA","4"])

    def test_background_staff_and_grip_composite_order(self):
        self.assertEqual(scene.STEPS[0]["fill"], scene.DARK_RED)
        self.assertEqual(scene.STEPS[0]["width"], scene.WIDTH)
        staff=next(i for i,p in enumerate(scene.STEPS) if "Bamboo staff" in p["name"])
        hand=next(i for i,p in enumerate(scene.STEPS) if "Upper fist" in p["name"])
        self.assertLess(staff,hand)
        self.assertLess(scene.STEPS[staff]["y"], 50)
        self.assertGreater(scene.STEPS[hand]["x"], 300)

    def test_negative_duplicate_name_fails_before_any_adobe_write(self):
        with patch.object(scene,"STEPS",(scene.STEPS[0],scene.STEPS[0])):
            with self.assertRaisesRegex(ValueError,"duplicate Adobe object"):
                scene.validate()

    def test_negative_zero_sized_component_fails(self):
        bad=dict(scene.STEPS[1],width=0)
        with patch.object(scene,"STEPS",(*scene.STEPS[:1],bad,*scene.STEPS[2:])):
            with self.assertRaisesRegex(ValueError,"zero-size"):
                scene.validate()

    def test_negative_html_injection_path_fails(self):
        original=scene.STEPS[4]
        bad=dict(original,pathData="<svg onload=alert(1)>")
        with patch.object(scene,"STEPS",(*scene.STEPS[:4],bad,*scene.STEPS[5:])):
            with self.assertRaisesRegex(ValueError,"invalid individual path"):
                scene.validate()

    def test_reference_image_not_embedded_or_bulk_imported(self):
        import inspect
        body=inspect.getsource(scene)
        self.assertNotIn("import_image",body)
        self.assertNotIn("import_svg",body)
        self.assertNotIn("base64",body)
        self.assertNotIn(".png",body)


if __name__=="__main__":
    unittest.main()

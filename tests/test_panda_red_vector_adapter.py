"""Contract tests for separately executed Adobe editable vector operations."""
import unittest

from scripts.panda_red_poster_blueprint import STEPS,validate
from scripts.panda_red_vector_adapter import rgb,sample_path,translate


class RedVectorAdapterTests(unittest.TestCase):
    def test_every_component_translates_to_one_xd_mcp_operation(self):
        validate()
        writes=[translate("xd",part) for part in STEPS]
        self.assertEqual(len(writes),60)
        self.assertEqual(len(set(args["name"] for _,args in writes)),60)
        for step,(cap,args) in zip(STEPS,writes):
            self.assertEqual(args["name"],step["name"])
            self.assertTrue(cap.startswith("creative."))
            self.assertEqual(args["fill"],step["fill"])
            if step["kind"]=="path":
                self.assertEqual(cap,"creative.path.create")
                self.assertEqual(args["pathData"],step["pathData"])

    def test_illustrator_editable_sampled_path_and_global_minimum(self):
        curves=[s for s in STEPS if s["kind"]=="path"]
        self.assertGreaterEqual(len(curves),20)
        for part in curves:
            cap,args=translate("illustrator",part)
            self.assertEqual(cap,"creative.path.create")
            self.assertTrue(args["closed"])
            self.assertGreaterEqual(len(args["points"]),3)
            self.assertLessEqual(len(args["points"]),512)
            self.assertAlmostEqual(min(p[0] for p in args["points"]),part["x"],delta=0.11)
            self.assertAlmostEqual(min(p[1] for p in args["points"]),part["y"],delta=0.11)
            self.assertEqual(args["fill"],rgb(part["fill"]))

    def test_cubic_negative_control_point_and_closed_polygon(self):
        path="M0 0 C-10 -20 30 30 40 40 L40 0 Z"
        values=sample_path(path,count=20)
        self.assertGreater(len(values),21)
        self.assertEqual(values[0],values[-1])
        self.assertEqual(values[-2],(40,0))

    def test_invalid_svg_markup_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"unsupported|malformed"):
            sample_path("<svg onload='alert(1)'>")
        with self.assertRaisesRegex(ValueError,"unsupported|malformed"):
            sample_path("M0 0 Q10 20 30 40 Z")

    def test_open_or_repeated_contour_rejected(self):
        for path in ("M0 0 L10 0 L10 10","M0 0 L10 0 L10 10 Z M0 0 L1 1 Z"):
            with self.assertRaises(ValueError):
                sample_path(path)

    def test_photoshop_path_is_explicitly_unsupported_not_silently_rasterized(self):
        one=next(step for step in STEPS if step["kind"]=="path")
        with self.assertRaisesRegex(ValueError,"Photoshop path capability unavailable"):
            translate("photoshop",one)

    def test_rgb_positive_and_bad_fill_negative(self):
        self.assertEqual(rgb("#BC0000"),{"r":188,"g":0,"b":0})
        with self.assertRaises(ValueError):rgb("red")

    def test_nonfinite_coordinates_never_reach_host(self):
        bad=dict(STEPS[0],x=float("inf"))
        with self.assertRaisesRegex(ValueError,"nonfinite global"):
            translate("illustrator",bad)


if __name__=="__main__":
    unittest.main()

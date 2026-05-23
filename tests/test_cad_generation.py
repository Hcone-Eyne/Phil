import ast
import unittest

from voice_input.cad_assist.ai_core import _offline_spec
from voice_input.cad_assist.builder import json_to_freecad


class CadGenerationTests(unittest.TestCase):
    def _code_for(self, prompt):
        spec = _offline_spec(prompt)
        code = json_to_freecad(spec)
        ast.parse(code)
        self.assertIn("final_shape =", code)
        self.assertIn("exportStep", code)
        return code

    def test_small_ten_tooth_gear(self):
        code = self._code_for("small gear diameter of 4 mm with 10 teeth thickness 3 mm")
        self.assertIn("for i in range(10)", code)
        self.assertIn("_spur_gear_outer_r = 4.0 / 2", code)
        self.assertIn("extrude(App.Vector(0, 0, 3.0))", code)

    def test_sg90_gear_arm_pattern(self):
        code = self._code_for(
            "Create a gear and robotic arm fitted to SG90 servo motor gear shaft"
        )
        self.assertIn("for i in range(10)", code)
        self.assertIn("for i in range(21)", code)
        self.assertIn("4.8 / 2", code)
        self.assertIn("sg90_robotic_arm", code)

    def test_l_bracket(self):
        code = self._code_for("make an L bracket 30 20 25 mm thickness 3 mm")
        self.assertIn("l_bracket_base", code)
        self.assertIn("l_bracket_wall", code)
        self.assertIn(".cut(_l_bracket_base_hole)", code)

    def test_flange(self):
        code = self._code_for("make a flange outer diameter 30 inner bore 10 thickness 5")
        self.assertIn("Part.makeCylinder(15.0, 5.0)", code)
        self.assertIn("for i in range(4)", code)
        self.assertIn(".cut(_flange_center)", code)

    def test_plate_with_holes(self):
        code = self._code_for("make a plate 40 20 3 with 3 mm holes")
        self.assertIn("mounting_plate = Part.makeBox(40.0, 20.0, 3.0)", code)
        self.assertEqual(code.count(".cut(_mounting_plate_hole_"), 4)

    def test_shaft_with_keyway(self):
        code = self._code_for("make a shaft diameter 8 length 40 with keyway")
        self.assertIn("shaft = Part.makeCylinder(4.0, 40.0)", code)
        self.assertIn("_shaft_keyway", code)


if __name__ == "__main__":
    unittest.main()

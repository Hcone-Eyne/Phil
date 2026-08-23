import ast
from pathlib import Path
import tempfile
import unittest

from voice_input.cad_assist import ai_core
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

    def test_servo_mount_with_shaft_holes_is_not_a_shaft(self):
        code = self._code_for(
            "make a robot servo mount with a hollow rectangular body and two shaft holes"
        )
        self.assertIn("outer_body = Part.makeBox", code)
        self.assertIn("inner_cavity = Part.makeBox", code)
        self.assertIn("shaft_hole_1 = Part.makeCylinder", code)
        self.assertIn("shaft_hole_2 = Part.makeCylinder", code)
        self.assertIn("final_shape = outer_body.cut(inner_cavity).cut(shaft_hole_1).cut(shaft_hole_2)", code)
        self.assertNotIn("shaft = Part.makeCylinder", code)

    def test_bare_asset_type_from_llm_expands_to_spur_gear(self):
        spec = {
            "parts": [{"type": "ten_tooth_gear", "name": "gear_5mm"}],
            "operations": [],
        }
        expanded = ai_core._expand_asset_references(spec)
        code = json_to_freecad(expanded)
        ast.parse(code)
        self.assertIn("gear_5mm = Part.Face", code)
        self.assertIn("for i in range(10)", code)
        self.assertIn("final_shape = gear_5mm", code)
        self.assertNotIn("Part.makeBox(10,10,10)", code)

    def test_empty_operations_defaults_to_fuse_all(self):
        code = json_to_freecad({
            "parts": [{"type": "cylinder", "name": "pin", "r": 2, "h": 8}],
            "operations": [],
        })
        ast.parse(code)
        self.assertIn("final_shape = pin", code)
        self.assertNotIn("final_shape = Part.makeBox(1,1,1)", code)

    def test_generated_asset_library_is_added_to_prompt(self):
        original_path = ai_core._GENERATED_ASSET_LIBRARY_PATH
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                ai_core._GENERATED_ASSET_LIBRARY_PATH = Path(tmpdir) / "assets.json"
                spec = {
                    "description": "Make a motor housing with a shaft hole.",
                    "parts": [
                        {"type": "cylinder", "name": "housing_body", "r": 15, "h": 50},
                        {"type": "cylinder", "name": "shaft_hole", "r": 5, "h": 50.2},
                    ],
                    "operations": [
                        {"type": "cut", "base": "housing_body", "cutters": ["shaft_hole"]}
                    ],
                }
                ai_core._register_generated_asset(
                    "make a motor housing 50mm long 30mm diameter with a 10mm shaft hole",
                    spec,
                )
                prompt = ai_core._build_asset_library_prompt()
                self.assertIn("asset:motor_housing_shaft_hole", prompt)
                self.assertIn("Make a motor housing with a shaft hole.", prompt)
        finally:
            ai_core._GENERATED_ASSET_LIBRARY_PATH = original_path


if __name__ == "__main__":
    unittest.main()

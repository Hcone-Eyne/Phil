"""Translator between user requests and generated FreeCAD scripts.

This restores the JSON pipeline:
prompt -> LLM -> JSON spec -> builder.py -> FreeCAD Python.
"""

import json
import os
import re

import ollama  # type: ignore
from dotenv import load_dotenv  # type: ignore

from voice_input import stage_manager
from voice_input.Keys.config import ai_gen_folder
from voice_input.cad_assist.builder import build_and_save

load_dotenv()
api_key = os.getenv("api_key")


SHAPE_PATTERNS = {
    "sg90_gear_arm": {
        "description": (
            "Make a 4 mm outside-diameter spur gear with exactly 10 teeth and "
            "3 mm thickness.\n\n"
            "Add a separate SG90-compatible robotic servo arm: 28 mm long, "
            "5 mm wide, 3 mm thick, with a 7 mm hub, a 4.8 mm 21-spline "
            "shaft bore, 1.8 mm center screw bore, and repeated 1.4 mm "
            "mounting holes.\n\n"
            "Place the arm beside the gear so both parts are visible in preview."
        ),
        "parts": [
            {
                "type": "spur_gear",
                "name": "ten_tooth_gear",
                "diameter": 4,
                "root_diameter": 3.12,
                "teeth": 10,
                "thickness": 3,
                "bore_diameter": 0.9,
            },
            {
                "type": "sg90_servo_arm",
                "name": "sg90_robotic_arm",
                "length": 28,
                "width": 5,
                "thickness": 3,
                "hub_diameter": 7,
                "shaft_bore_diameter": 4.8,
                "shaft_minor_diameter": 4.35,
                "shaft_spline_teeth": 21,
                "screw_bore_diameter": 1.8,
                "mounting_hole_diameter": 1.4,
                "mounting_hole_spacing": 5,
                "translate": [12, 0, 0],
            },
        ],
        "operations": [{"type": "fuse_all"}],
    },
    "ten_tooth_gear": {
        "description": (
            "Make a 4 mm outside-diameter spur gear with exactly 10 teeth, "
            "3 mm thickness, and a small centered bore."
        ),
        "parts": [
            {
                "type": "spur_gear",
                "name": "ten_tooth_gear",
                "diameter": 4,
                "root_diameter": 3.12,
                "teeth": 10,
                "thickness": 3,
                "bore_diameter": 0.9,
            },
        ],
        "operations": [{"type": "assign", "part": "ten_tooth_gear"}],
    },
    "sg90_servo_arm": {
        "description": (
            "Make an SG90-compatible robotic servo arm: 28 mm long, 5 mm wide, "
            "3 mm thick, with a 7 mm hub, a 4.8 mm 21-spline shaft bore, "
            "1.8 mm center screw bore, and repeated 1.4 mm mounting holes."
        ),
        "parts": [
            {
                "type": "sg90_servo_arm",
                "name": "sg90_robotic_arm",
                "length": 28,
                "width": 5,
                "thickness": 3,
                "hub_diameter": 7,
                "shaft_bore_diameter": 4.8,
                "shaft_minor_diameter": 4.35,
                "shaft_spline_teeth": 21,
                "screw_bore_diameter": 1.8,
                "mounting_hole_diameter": 1.4,
                "mounting_hole_spacing": 5,
            },
        ],
        "operations": [{"type": "assign", "part": "sg90_robotic_arm"}],
    },
    "l_bracket": {
        "description": (
            "Make an L bracket with a horizontal base, vertical wall, and one "
            "mounting hole through each face."
        ),
        "parts": [
            {
                "type": "l_bracket",
                "name": "l_bracket",
                "length": 30,
                "width": 18,
                "height": 30,
                "thickness": 3,
                "hole_diameter": 4,
            },
        ],
        "operations": [{"type": "assign", "part": "l_bracket"}],
    },
    "flange": {
        "description": (
            "Make a circular flange with a center bore and four bolt holes on "
            "a bolt circle."
        ),
        "parts": [
            {
                "type": "flange",
                "name": "flange",
                "outer_diameter": 30,
                "inner_diameter": 10,
                "thickness": 5,
                "bolt_count": 4,
                "bolt_diameter": 3,
                "bolt_circle_diameter": 22,
            },
        ],
        "operations": [{"type": "assign", "part": "flange"}],
    },
    "plate": {
        "description": "Make a rectangular mounting plate with corner holes.",
        "parts": [
            {
                "type": "plate",
                "name": "mounting_plate",
                "length": 40,
                "width": 20,
                "thickness": 3,
                "holes": [
                    {"x": 5, "y": 5, "diameter": 3},
                    {"x": 35, "y": 5, "diameter": 3},
                    {"x": 5, "y": 15, "diameter": 3},
                    {"x": 35, "y": 15, "diameter": 3},
                ],
            },
        ],
        "operations": [{"type": "assign", "part": "mounting_plate"}],
    },
    "shaft": {
        "description": "Make a cylindrical shaft with an optional flat keyway.",
        "parts": [
            {
                "type": "shaft",
                "name": "shaft",
                "diameter": 8,
                "length": 40,
                "keyway": True,
            },
        ],
        "operations": [{"type": "assign", "part": "shaft"}],
    },
    "aeroplane": {
        "parts": [
            {
                "type": "cylinder",
                "name": "fuselage",
                "r": 8,
                "h": 80,
                "rotate": {"axis": [0, 1, 0], "angle": 90},
            },
            {
                "type": "box",
                "name": "left_wing",
                "l": 20,
                "w": 40,
                "h": 2,
                "translate": [30, 0, -1],
            },
            {
                "type": "box",
                "name": "right_wing",
                "l": 20,
                "w": 40,
                "h": 2,
                "translate": [30, -40, -1],
            },
            {
                "type": "box",
                "name": "tail_fin",
                "l": 10,
                "w": 2,
                "h": 15,
                "translate": [65, -1, 0],
            },
        ],
        "operations": [{"type": "fuse_all"}],
    },
    "bolt": {
        "parts": [
            {"type": "hex_prism", "name": "head", "r": 8, "h": 8},
            {
                "type": "cylinder",
                "name": "shaft",
                "r": 4,
                "h": 40,
                "translate": [0, 0, 8],
            },
        ],
        "operations": [{"type": "fuse_all"}],
    },
    "pipe": {
        "parts": [
            {
                "type": "pipe",
                "name": "pipe_body",
                "r_outer": 10,
                "r_inner": 8,
                "h": 60,
            },
        ],
        "operations": [{"type": "assign", "part": "pipe_body"}],
    },
}

SHAPE_KEYWORDS = {
    "sg90_gear_arm": [
        "sg90 servo",
        "sg90",
        "servo motor",
        "servo moto",
        "robotic arm",
        "gear shaft",
    ],
    "ten_tooth_gear": ["10 teeth", "ten teeth", "small gear", "spur gear", "gear"],
    "sg90_servo_arm": ["servo arm", "servo horn"],
    "l_bracket": ["l bracket", "angle bracket", "corner bracket"],
    "flange": ["flange", "bolt circle", "bolt holes"],
    "plate": ["plate", "mounting plate", "base plate"],
    "shaft": ["shaft", "axle", "keyway"],
    "aeroplane": ["aeroplane", "airplane", "plane", "aircraft"],
    "bolt": ["bolt", "hex bolt", "screw"],
    "pipe": ["pipe", "tube", "hollow cylinder"],
}


def get_pattern_json(user_request):
    req = user_request.lower()
    if "gear" in req and any(token in req for token in ("sg90", "servo", "robotic arm")):
        return SHAPE_PATTERNS["sg90_gear_arm"]
    for shape, keywords in SHAPE_KEYWORDS.items():
        if any(keyword in req for keyword in keywords):
            return SHAPE_PATTERNS[shape]
    return None


JSON_SYSTEM_RULE = """You are a FreeCAD 3D model spec generator.
Return ONLY a valid JSON object. No markdown. No backticks. No explanation.

=== OUTPUT FORMAT ===
{
  "parts": [
    {
      "type": "<primitive>",
      "name": "<unique_name>",
      "... dimensions ...": "...",
      "translate": [x, y, z],
      "rotate": {"axis": [ax,ay,az], "angle": deg},
      "mirror": {"source": "<name>", "axis": [ax,ay,az]}
    }
  ],
  "operations": [
    {"type": "fuse_all"}
    OR {"type": "fuse", "parts": ["a","b","c"]}
    OR {"type": "cut", "base": "a", "cutters": ["b","c"]}
    OR {"type": "assign", "part": "a"}
  ]
}

=== PRIMITIVES ===
box        -> l, w, h
cylinder   -> r, h
sphere     -> r
cone       -> r1, r2, h
torus      -> r1, r2
hex_prism  -> r (side length), h
pipe       -> r_outer, r_inner, h
plate      -> length, width, thickness, holes[{x,y,diameter}]
l_bracket  -> length, width, height, thickness, hole_diameter
flange     -> outer_diameter, inner_diameter, thickness, bolt_count, bolt_diameter, bolt_circle_diameter
shaft      -> diameter, length, keyway
spur_gear  -> diameter, root_diameter, teeth, thickness, bore_diameter
sg90_servo_arm -> length, width, thickness, hub_diameter, shaft_bore_diameter, shaft_spline_teeth, screw_bore_diameter, mounting_hole_diameter

=== TRANSFORM RULES ===
- rotate axis [0,1,0] angle 90 = horizontal along X-axis (use for fuselage)
- wings span along Y-axis to be visible outside fuselage radius
- translate moves from origin after creation

=== HARD RULES ===
- ALWAYS include at least one operation
- fuse_all fuses every part in order
- For hollow shapes use type "pipe"
- Prefer plate, l_bracket, flange, shaft, spur_gear, and sg90_servo_arm when the request matches those mechanical parts
- Output ONLY the JSON object, nothing else
"""


def validate_json_spec(spec: dict) -> bool:
    if "parts" not in spec or not isinstance(spec["parts"], list):
        return False
    if "operations" not in spec or not isinstance(spec["operations"], list):
        return False
    for part in spec["parts"]:
        if "type" not in part or "name" not in part:
            return False
    return True


def extract_json(raw: str) -> dict:
    clean = raw.replace("```json", "").replace("```", "").strip()
    start = clean.find("{")
    end = clean.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(clean[start:end])


def _save_json_spec(spec: dict, user_request: str):
    json_path = ai_gen_folder / "last_spec.json"
    with open(json_path, "w") as file:
        json.dump(
            {
                "request": user_request,
                "description": spec.get("description", user_request),
                "spec": spec,
            },
            file,
            indent=2,
        )
    print(f"[AI Core] JSON spec saved -> {json_path}")


def _numbers(text: str) -> list[float]:
    return [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]


def _first_number_near(
    text: str, words: tuple[str, ...], default: float, allow_before: bool = True
) -> float:
    for word in words:
        match = re.search(rf"{word}\D{{0,20}}(\d+(?:\.\d+)?)", text)
        if match:
            return float(match.group(1))
        if allow_before:
            match = re.search(rf"(\d+(?:\.\d+)?)\s*(?:mm|millimeter|millimeters)?\s+{word}", text)
            if match:
                return float(match.group(1))
    return default


def _offline_spec(user_request: str) -> dict:
    req = user_request.lower()

    if any(token in req for token in ("sg90", "servo arm", "servo horn")) and "gear" not in req:
        return SHAPE_PATTERNS["sg90_servo_arm"]

    if "gear" in req:
        diameter = _first_number_near(req, ("diameter", "od", "outside"), 20, allow_before=False)
        thickness = _first_number_near(req, ("thick", "thickness", "height"), 5, allow_before=True)
        teeth_match = (
            re.search(r"(\d+(?:\.\d+)?)\s*(?:teeth|tooth)", req)
            or re.search(r"(?:teeth|tooth)\D{0,8}(\d+(?:\.\d+)?)", req)
        )
        teeth = int(float(teeth_match.group(1))) if teeth_match else 16
        spec = {
            "description": (
                f"Make a {diameter:g} mm outside-diameter spur gear with exactly "
                f"{teeth} teeth and {thickness:g} mm thickness."
            ),
            "parts": [
                {
                    "type": "spur_gear",
                    "name": "spur_gear",
                    "diameter": diameter,
                    "root_diameter": diameter * 0.78,
                    "teeth": teeth,
                    "thickness": thickness,
                    "bore_diameter": max(0.8, diameter * 0.22),
                }
            ],
            "operations": [{"type": "assign", "part": "spur_gear"}],
        }
        if any(token in req for token in ("sg90", "servo", "robotic arm", "servo arm")):
            return SHAPE_PATTERNS["sg90_gear_arm"]
        return spec

    if any(token in req for token in ("flange", "bolt circle")):
        outer = _first_number_near(req, ("outer", "outside", "diameter"), 30, allow_before=False)
        inner = _first_number_near(req, ("inner", "bore", "hole"), 10, allow_before=False)
        thick = _first_number_near(req, ("thick", "thickness"), 5, allow_before=False)
        bolt_count = int(_first_number_near(req, ("bolt", "holes"), 4))
        return {
            "description": (
                f"Make a {outer:g} mm flange, {thick:g} mm thick, with a "
                f"{inner:g} mm center bore and {bolt_count} bolt holes."
            ),
            "parts": [
                {
                    "type": "flange",
                    "name": "flange",
                    "outer_diameter": outer,
                    "inner_diameter": inner,
                    "thickness": thick,
                    "bolt_count": bolt_count,
                    "bolt_diameter": 3,
                    "bolt_circle_diameter": outer * 0.72,
                }
            ],
            "operations": [{"type": "assign", "part": "flange"}],
        }

    if any(token in req for token in ("bracket", "l bracket", "angle bracket")):
        nums = _numbers(req)
        length = nums[0] if len(nums) > 0 else 30
        width = nums[1] if len(nums) > 1 else 18
        height = nums[2] if len(nums) > 2 else 30
        thick = _first_number_near(req, ("thick", "thickness"), 3)
        return {
            "description": (
                f"Make an L bracket {length:g} x {width:g} x {height:g} mm "
                f"with {thick:g} mm wall thickness and mounting holes."
            ),
            "parts": [
                {
                    "type": "l_bracket",
                    "name": "l_bracket",
                    "length": length,
                    "width": width,
                    "height": height,
                    "thickness": thick,
                    "hole_diameter": 4,
                }
            ],
            "operations": [{"type": "assign", "part": "l_bracket"}],
        }

    if any(token in req for token in ("plate", "base")):
        nums = _numbers(req)
        length = nums[0] if len(nums) > 0 else 40
        width = nums[1] if len(nums) > 1 else 20
        thick = _first_number_near(req, ("thick", "thickness"), nums[2] if len(nums) > 2 else 3)
        hole_d = _first_number_near(req, ("hole", "holes"), 3)
        inset = max(hole_d, 4)
        return {
            "description": (
                f"Make a {length:g} x {width:g} x {thick:g} mm mounting plate "
                f"with four {hole_d:g} mm corner holes."
            ),
            "parts": [
                {
                    "type": "plate",
                    "name": "mounting_plate",
                    "length": length,
                    "width": width,
                    "thickness": thick,
                    "holes": [
                        {"x": inset, "y": inset, "diameter": hole_d},
                        {"x": length - inset, "y": inset, "diameter": hole_d},
                        {"x": inset, "y": width - inset, "diameter": hole_d},
                        {"x": length - inset, "y": width - inset, "diameter": hole_d},
                    ],
                }
            ],
            "operations": [{"type": "assign", "part": "mounting_plate"}],
        }

    if any(token in req for token in ("shaft", "axle")):
        diameter = _first_number_near(req, ("diameter", "dia"), 8, allow_before=False)
        length = _first_number_near(req, ("long", "length"), 40, allow_before=False)
        return {
            "description": (
                f"Make a {diameter:g} mm diameter, {length:g} mm long shaft"
                f"{' with a keyway' if 'keyway' in req else ''}."
            ),
            "parts": [
                {
                    "type": "shaft",
                    "name": "shaft",
                    "diameter": diameter,
                    "length": length,
                    "keyway": "keyway" in req,
                }
            ],
            "operations": [{"type": "assign", "part": "shaft"}],
        }

    nums = _numbers(req)
    l = nums[0] if len(nums) > 0 else 10
    w = nums[1] if len(nums) > 1 else l
    h = nums[2] if len(nums) > 2 else l
    return {
        "description": f"Make a simple {l:g} x {w:g} x {h:g} mm solid block.",
        "parts": [{"type": "box", "name": "block", "l": l, "w": w, "h": h}],
        "operations": [{"type": "assign", "part": "block"}],
    }


def translator(user_request):
    previous_memory = stage_manager.get_memory()
    req = user_request.lower()

    offline_first_tokens = (
        "gear",
        "flange",
        "bracket",
        "plate",
        "shaft",
        "axle",
        "servo arm",
        "servo horn",
    )
    if any(token in req for token in offline_first_tokens):
        print("[AI Core] Mechanical task - using deterministic builder")
        spec = _offline_spec(user_request)
        try:
            filename = build_and_save(spec)
            _save_json_spec(spec, user_request)
            return filename
        except Exception as exc:
            print(f"[AI Core] Deterministic build failed: {exc}, falling back to LLM")

    pattern = get_pattern_json(user_request)
    if pattern:
        print("[AI Core] Known shape - using pattern directly")
        try:
            filename = build_and_save(pattern)
            _save_json_spec(pattern, user_request)
            return filename
        except Exception as exc:
            print(f"[AI Core] Pattern build failed: {exc}, falling back to LLM")

    user_prompt = (
        f"Previous build context:\n{previous_memory}\n\n"
        f"Build request: {user_request}"
    )

    print("Builder Model Active...")
    print("[Qwen 2.5]: Generating JSON spec...")

    try:
        response = ollama.chat(
            model="qwen2.5-coder:7b",
            messages=[
                {"role": "system", "content": JSON_SYSTEM_RULE},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.message.content
        print("\n[Builder Model]: JSON received.")
        spec = extract_json(raw)
    except Exception as exc:
        print(f"[AI Core] LLM path failed: {exc}")
        print("[AI Core] Using offline mechanical fallback.")
        spec = _offline_spec(user_request)

    if not validate_json_spec(spec):
        print("[AI Core] JSON spec invalid")
        return None

    _save_json_spec(spec, user_request)

    try:
        filename = build_and_save(spec)
    except Exception as exc:
        print(f"[AI Core] Builder failed: {exc}")
        return None

    print("Qwen 2.5 successfully ran (JSON pipeline)")
    return filename

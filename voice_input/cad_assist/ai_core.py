"""Translator between user requests and generated FreeCAD scripts.

This restores the JSON pipeline:
prompt -> LLM -> JSON spec -> builder.py -> FreeCAD Python.
"""

import json
import os
import re

try:
    from dotenv import load_dotenv  # type: ignore
except ModuleNotFoundError:
    def load_dotenv(*args, **kwargs):
        return False

from setup.llm_client import get_client
from voice_input import stage_manager
from voice_input.Keys.config import (
    ai_gen_folder,
    error_memory_path,
    generated_asset_library_path,
)
from voice_input.cad_assist.builder import build_and_save

load_dotenv()
api_key = os.getenv("api_key")

from datetime import datetime
from pathlib import Path

# ── Error Memory System ────────────────────────────────────────────────────────
# This is the model's "mistake journal".
# Every time the LLM returns bad output (wrong format, missing keys, hallucinated
# structure), we log it here. Before every new generation, we read recent mistakes
# and inject them into the prompt — so the model sees what it got wrong before
# and avoids repeating those exact mistakes.
# This is persistent across sessions — the model gets smarter over time.

# error_memory.json  = LLM format/logic mistakes (voice_input.Keys.config)
# correction.log.txt = FreeCAD runtime errors (config.correction_log_path, used in runner.py)
_ERROR_MEMORY_PATH = Path(error_memory_path)
_GENERATED_ASSET_LIBRARY_PATH = Path(generated_asset_library_path)

# How many past errors to inject per prompt
# 5 is the sweet spot — enough to cover patterns, not enough to confuse 7B
_MAX_ERRORS_TO_INJECT = 5
_MAX_GENERATED_ASSETS = 20


def _load_error_memory() -> list:
    """
    Load all stored LLM mistakes from error_memory.json.
    Returns empty list if file missing or corrupted — never crashes.
    Each entry: {timestamp, error_type, bad_output_preview, lesson}
    """
    if not _ERROR_MEMORY_PATH.exists():
        return []
    try:
        with open(_ERROR_MEMORY_PATH, "r") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        # Corrupted file? Start fresh. Don't crash the whole app over this.
        return []


def _save_error_memory(errors: list):
    """Write the updated error list back to disk. Creates directory if needed."""
    _ERROR_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_ERROR_MEMORY_PATH, "w") as f:
        json.dump(errors, f, indent=2)


def log_format_error(bad_output: str, error_type: str, lesson: str):
    """
    Record a new LLM mistake into the persistent error memory.

    bad_output  — the raw string the model returned (stored truncated to 300 chars)
    error_type  — short tag for the kind of mistake:
                    'wrong_format'     = returned thoughts/steps instead of JSON
                    'invalid_json'     = JSON parse failed
                    'missing_parts_key'= JSON parsed but had wrong structure
                    'geometry_fail'    = script ran but produced bad/empty geometry
    lesson      — plain-English rule the model must learn:
                    e.g. "Do not return thoughts/steps — return ONLY the raw JSON object"

    Rotates at 30 entries max so the file never grows unbounded.
    Called from: translator() when validate_json_spec() fails
    """
    errors = _load_error_memory()

    new_entry = {
        "timestamp": datetime.now().isoformat(),
        "error_type": error_type,
        # Truncate so the memory file stays small and readable
        "bad_output_preview": bad_output[:300].strip(),
        "lesson": lesson,
    }

    errors.append(new_entry)

    # Rotate: discard oldest beyond 30 so memory stays focused on recent behaviour
    if len(errors) > 30:
        errors = errors[-30:]

    _save_error_memory(errors)
    print(f"[ErrorMemory] Logged: {error_type} — {lesson[:60]}")


def _build_error_memory_prompt() -> str:
    """
    Read the last N errors and format them as a prompt block.

    This is the "injection" step — called every time before we send to the LLM.
    The model reads its own past mistakes as part of the system context,
    so it knows what NOT to do before it even starts generating.

    Returns empty string on first run (no mistakes yet) — safe to concatenate.
    Uses plain direct language because 7B models respond better to explicit
    rules than structured JSON in the system prompt.
    """
    errors = _load_error_memory()
    if not errors:
        return ""  # First ever run — nothing to inject yet

    # Only inject the most recent N to avoid prompt bloat
    recent = errors[-_MAX_ERRORS_TO_INJECT:]

    lines = ["\n=== YOUR PAST MISTAKES — DO NOT REPEAT ==="]
    for i, entry in enumerate(recent, 1):
        lines.append(f"{i}. [{entry['error_type']}] {entry['lesson']}")
        preview = entry.get("bad_output_preview", "")
        if preview:
            # Show just enough of the bad output so the model recognises the pattern
            lines.append(f"   You returned: {preview[:120]}...")
    lines.append("=== END OF PAST MISTAKES ===\n")

    return "\n".join(lines)


def _load_generated_asset_library() -> dict:
    if not _GENERATED_ASSET_LIBRARY_PATH.exists():
        return {}
    try:
        with open(_GENERATED_ASSET_LIBRARY_PATH, "r") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_generated_asset_library(assets: dict):
    _GENERATED_ASSET_LIBRARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_GENERATED_ASSET_LIBRARY_PATH, "w") as file:
        json.dump(assets, file, indent=2)


def _asset_key_from_request(user_request: str) -> str:
    text = user_request.lower()
    text = re.sub(r"\b\d+(?:\.\d+)?\s*(?:mm|millimeter|millimeters|cm|inch|inches)?\b", " ", text)
    words = re.findall(r"[a-z][a-z0-9_]*", text)
    stop_words = {
        "a", "an", "and", "the", "with", "without", "make", "create", "build",
        "generate", "simple", "model", "part", "mm", "long", "wide", "tall",
        "diameter", "thick", "thickness", "through", "center", "centre",
    }
    useful = []
    for word in words:
        if word not in stop_words and word not in useful:
            useful.append(word)
    key = "_".join(useful[:5]) or "generated_asset"
    return re.sub(r"[^a-z0-9_]+", "_", key).strip("_")


def _clone_json(data):
    return json.loads(json.dumps(data))


def _asset_library() -> dict:
    assets = {}
    for name, spec in SHAPE_PATTERNS.items():
        assets[name] = {
            "source": "built_in",
            "description": spec.get("description", f"Reusable CAD asset: {name}."),
            "spec": spec,
        }
    assets.update(_load_generated_asset_library())
    return assets


def _compact_spec_for_prompt(spec: dict) -> dict:
    compact = {
        "parts": spec.get("parts", [])[:6],
        "operations": spec.get("operations", [])[:4],
    }
    return compact


def _build_asset_library_prompt() -> str:
    assets = _asset_library()
    if not assets:
        return ""

    lines = [
        "\n=== CAD ASSET LIBRARY ===",
        "These assets are examples/tools, not routers. The user's full prompt is the source of truth.",
        "Use an asset only when it genuinely helps. If no asset fits, generate the model from primitives.",
        "If an asset word appears as a feature, do not turn the whole model into that asset.",
        "Example: 'shaft hole' means a cylinder cutter unless the user asks for a shaft itself.",
        'You may reference a single-part asset as {"type": "asset:name", "name": "my_part"}.',
        "For multi-part assets, copy/adapt the shown parts into your JSON instead of referencing blindly.",
        "",
        "Available assets:",
    ]

    for name, entry in sorted(assets.items()):
        description = entry.get("description", "").replace("\n", " ").strip()
        source = entry.get("source", "built_in")
        spec = entry.get("spec", {})
        parts = spec.get("parts", [])
        single_part = "single-part" if len(parts) == 1 else f"{len(parts)} parts"
        lines.append(f"- asset:{name} ({source}, {single_part}): {description[:180]}")
        if source == "generated":
            snippet = json.dumps(_compact_spec_for_prompt(spec), separators=(",", ":"))
            lines.append(f"  JSON snippet: {snippet[:900]}")

    lines.append("=== END CAD ASSET LIBRARY ===\n")
    return "\n".join(lines)


def _uses_asset_reference(spec: dict) -> bool:
    for part in spec.get("parts", []):
        ptype = part.get("type", "")
        if isinstance(ptype, str) and (ptype.startswith("asset:") or ptype.startswith("pattern:")):
            return True
    return False


def _register_generated_asset(user_request: str, spec: dict):
    if not validate_json_spec(spec) or _uses_asset_reference(spec):
        return

    assets = _load_generated_asset_library()
    base_key = _asset_key_from_request(user_request)
    key = base_key
    suffix = 2
    while key in SHAPE_PATTERNS or key in assets:
        existing = assets.get(key, {})
        if existing.get("request") == user_request:
            break
        key = f"{base_key}_{suffix}"
        suffix += 1

    assets[key] = {
        "source": "generated",
        "created_at": datetime.now().isoformat(),
        "request": user_request,
        "description": spec.get("description", user_request),
        "spec": _clone_json(spec),
    }

    if len(assets) > _MAX_GENERATED_ASSETS:
        ordered = sorted(assets.items(), key=lambda item: item[1].get("created_at", ""))
        assets = dict(ordered[-_MAX_GENERATED_ASSETS:])

    _save_generated_asset_library(assets)
    print(f"[AssetLibrary] Registered generated asset: asset:{key}")




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
    "lego_brick": {
        "description": "Make a standard 4x2 Lego brick with hollow bottom and 8 studs.",
        "parts": [
            {
                "type":           "lego_brick",
                "name":           "lego_brick",
                "studs_x":        4,
                "studs_y":        2,
                "stud_diameter":  4.8,
                "stud_height":    1.8,
                "plate_height":   9.6,
                "wall_thickness": 1.2,
                "hollow":         True,
            }
        ],
        "operations": [{"type": "assign", "part": "lego_brick"}],
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
            # Only use pattern if keyword is the main subject, not a feature mention
            if _is_main_intent(req, tuple(keywords)):
                return SHAPE_PATTERNS[shape]
    return None


JSON_SYSTEM_RULE = """You are a FreeCAD 3D model spec generator.

CRITICAL: Your ENTIRE response must be a single raw JSON object.
- NO thoughts, NO steps, NO code_changes, NO explanation
- NO markdown, NO backticks, NO comments
- Start with { and end with } — nothing before, nothing after
- If you return anything other than raw JSON you have failed

=== OUTPUT FORMAT ===
{
  "parts": [
    {
      "type": "<primitive>",
      "name": "<unique_name>",
      "... dimensions ...": "...",
      "translate": [x, y, z],
      "rotate": {"axis": [ax,ay,az], "angle": deg}
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
- translate moves the part AFTER creation, from origin [0,0,0]
- rotate axis [0,0,1] = spin around Z (vertical), [0,1,0] = tip forward, [1,0,0] = roll
- to stack parts vertically, translate Z by the height of the part below
- to cut a hole through a part, make the cutter cylinder slightly taller (+0.2) and offset Z by -0.1

=== HARD RULES ===
- ALWAYS use cylinder (not box) for round/circular features like studs, pins, holes, shafts
- ALWAYS use pipe for hollow tubes — never cut a cylinder manually unless dimensions require it
- NEVER use mirror — it causes geometry errors; instead place each part with translate
- For hollow boxes (enclosures, shells): make outer box, make inner box slightly smaller, use cut operation
- fuse combines solid parts; cut removes material; assign = single part output
- Output ONLY the raw JSON object — no markdown, no backticks, no comments

=== READY-MADE PARTS (optional — use when helpful) ===
These are pre-built high-quality parts. You may use them directly, combine
multiple together, or modify them by overriding dimensions. Use type="asset:name"
to reference a single-part asset. Or ignore them entirely and build from primitives.

Available ready-made parts:
- asset:bolt          → hex bolt (hex head + cylindrical shaft)
- asset:pipe          → hollow tube (outer cylinder + inner cutout)
- asset:plate         → rectangular plate with corner mounting holes
- asset:shaft         → cylindrical rod with optional flat keyway
- asset:l_bracket     → L-shaped mounting bracket with holes through both faces
- asset:flange        → circular disc with center bore + bolt circle holes
- asset:spur_gear     → involute spur gear with configurable teeth + bore
- asset:sg90_servo_arm → SG90 servo horn with 21-spline shaft bore
- asset:lego_brick    → Lego brick with hollow bottom + cylindrical studs
- asset:aeroplane     → simple fuselage + wings + tail fin

COMPOSING EXAMPLE — servo mount using two ready-made parts:
Request: "servo mount with bracket body and shaft holes"
{
  "parts": [
    {"type": "asset:l_bracket", "name": "mount_body", "length": 40, "width": 25, "height": 35, "thickness": 3},
    {"type": "cylinder", "name": "shaft_hole_1", "r": 4, "h": 35.2, "translate": [10, 12, -0.1]},
    {"type": "cylinder", "name": "shaft_hole_2", "r": 4, "h": 35.2, "translate": [30, 12, -0.1]}
  ],
  "operations": [{"type": "cut", "base": "mount_body", "cutters": ["shaft_hole_1", "shaft_hole_2"]}]
}

=== EXAMPLES ===

--- Example 1: hollow cup (teaches: outer body + hollow interior via cut) ---
Request: "Make a cylindrical cup 40mm tall 30mm diameter with 2mm walls"
{
  "parts": [
    {"type": "cylinder", "name": "outer_body", "r": 15, "h": 40},
    {"type": "cylinder", "name": "inner_cavity", "r": 13, "h": 38, "translate": [0, 0, 2]}
  ],
  "operations": [{"type": "cut", "base": "outer_body", "cutters": ["inner_cavity"]}]
}

--- Example 2: motor housing (teaches: multi-part assembly with shaft hole) ---
Request: "Make a simple motor housing cylinder 50mm long 25mm outer diameter with 8mm shaft hole through center"
{
  "parts": [
    {"type": "cylinder", "name": "housing_body", "r": 12.5, "h": 50},
    {"type": "cylinder", "name": "shaft_hole", "r": 4, "h": 50.2, "translate": [0, 0, -0.1]},
    {"type": "cylinder", "name": "front_cap", "r": 14, "h": 3},
    {"type": "cylinder", "name": "rear_cap", "r": 14, "h": 3, "translate": [0, 0, 50]}
  ],
  "operations": [
    {"type": "fuse", "parts": ["housing_body", "front_cap", "rear_cap"]},
    {"type": "cut", "base": "housing_body", "cutters": ["shaft_hole"]}
  ]
}

--- Example 3: T-bracket (teaches: multi-box fuse for L/T shapes) ---
Request: "Make a T-shaped bracket 60mm wide 40mm tall 4mm thick"
{
  "parts": [
    {"type": "box", "name": "horizontal_bar", "l": 60, "w": 4, "h": 8},
    {"type": "box", "name": "vertical_bar", "l": 4, "w": 4, "h": 40, "translate": [28, 0, 8]}
  ],
  "operations": [{"type": "fuse_all"}]
}

--- Example 4: bearing seat (teaches: precise hollow cylinder with bolt holes) ---
Request: "Make a bearing seat 20mm outer diameter 12mm inner bore 10mm thick with 4 bolt holes on a 17mm bolt circle"
{
  "parts": [
    {"type": "flange", "name": "bearing_seat", "outer_diameter": 20, "inner_diameter": 12, "thickness": 10, "bolt_count": 4, "bolt_diameter": 2.5, "bolt_circle_diameter": 17}
  ],
  "operations": [{"type": "assign", "part": "bearing_seat"}]
}

--- Example 5: enclosure box (teaches: hollow rectangular shell via cut) ---
Request: "Make a rectangular electronics enclosure 80x50x30mm with 2mm walls open at bottom"
{
  "parts": [
    {"type": "box", "name": "outer_shell", "l": 80, "w": 50, "h": 30},
    {"type": "box", "name": "inner_cavity", "l": 76, "w": 46, "h": 28, "translate": [2, 2, 2]}
  ],
  "operations": [{"type": "cut", "base": "outer_shell", "cutters": ["inner_cavity"]}]
}
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


def _repair_llm_json(system_prompt: str, user_request: str, bad_output: str, error: Exception) -> dict | None:
    repair_prompt = (
        "Your previous response could not be used as a FreeCAD JSON spec.\n"
        f"Original build request: {user_request}\n\n"
        f"Parser/validation error: {error}\n\n"
        f"Bad response:\n{bad_output[:2000]}\n\n"
        "Return ONLY one corrected raw JSON object with 'parts' and 'operations'."
    )
    try:
        repaired_raw = get_client().chat(
            system=system_prompt,
            user=repair_prompt,
            format_json=True,
        )
        repaired = extract_json(repaired_raw)
        if validate_json_spec(repaired):
            print("[AI Core] LLM JSON repaired successfully.")
            return repaired
    except Exception as repair_exc:
        print(f"[AI Core] LLM repair failed: {repair_exc}")
    return None


def _offline_fallback_enabled() -> bool:
    value = os.getenv("PHIL_ALLOW_OFFLINE_FALLBACK", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _offline_or_none(user_request: str, reason: str) -> dict | None:
    if _offline_fallback_enabled():
        print(f"[AI Core] {reason} — using explicit offline fallback")
        return _offline_spec(user_request)
    print(f"[AI Core] {reason} — offline fallback disabled")
    return None


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


def _count_from_words(text: str, default: int = 2) -> int:
    word_counts = {
        "one": 1,
        "single": 1,
        "two": 2,
        "dual": 2,
        "three": 3,
        "four": 4,
    }
    for word, count in word_counts.items():
        if re.search(rf"\b{word}\b", text):
            return count
    match = re.search(r"\b(\d+)\s+(?:shaft\s+)?holes?\b", text)
    if match:
        return int(match.group(1))
    return default


def _servo_mount_spec(user_request: str) -> dict:
    req = user_request.lower()
    nums = _numbers(req)

    length = nums[0] if len(nums) > 0 else 50
    width = nums[1] if len(nums) > 1 else 28
    height = nums[2] if len(nums) > 2 else 24
    wall = _first_number_near(req, ("wall", "walls", "thick", "thickness"), 3)
    shaft_diameter = _first_number_near(req, ("shaft", "hole", "holes", "bore"), 8)
    hole_count = _count_from_words(req, default=2)

    inner_length = max(length - (2 * wall), 1)
    inner_width = max(width - (2 * wall), 1)
    inner_height = max(height - wall, 1)
    hole_spacing = min(length / (hole_count + 1), 18)

    parts = [
        {"type": "box", "name": "outer_body", "l": length, "w": width, "h": height},
        {
            "type": "box",
            "name": "inner_cavity",
            "l": inner_length,
            "w": inner_width,
            "h": inner_height + 0.2,
            "translate": [wall, wall, wall],
        },
    ]

    start_x = (length - (hole_spacing * (hole_count - 1))) / 2
    for index in range(hole_count):
        x = start_x + index * hole_spacing
        parts.append(
            {
                "type": "cylinder",
                "name": f"shaft_hole_{index + 1}",
                "r": shaft_diameter / 2,
                "h": width + 0.4,
                "rotate": {"axis": [1, 0, 0], "angle": 90},
                "translate": [x, width + 0.2, height / 2],
            }
        )

    return {
        "description": (
            f"Make a hollow rectangular robot servo mount body "
            f"{length:g} x {width:g} x {height:g} mm with {hole_count} "
            f"{shaft_diameter:g} mm shaft holes."
        ),
        "parts": parts,
        "operations": [
            {
                "type": "cut",
                "base": "outer_body",
                "cutters": ["inner_cavity"]
                + [f"shaft_hole_{index + 1}" for index in range(hole_count)],
            }
        ],
    }


def _offline_spec(user_request: str) -> dict:
    req = user_request.lower()

    if (
        "mount" in req
        and any(token in req for token in ("servo", "robot", "motor"))
        and any(token in req for token in ("hollow", "rectangular", "body", "shaft hole", "shaft holes"))
    ):
        return _servo_mount_spec(user_request)

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

    if (
        any(token in req for token in ("shaft", "axle"))
        and "shaft hole" not in req
        and "shaft holes" not in req
        and _is_main_intent(req, ("shaft", "axle"))
    ):
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

    if any(token in req for token in ("lego", "brick", "stud")):
        grid_match = re.search(r"(\d+)\s*[xX×by]+\s*(\d+)", req)
        if grid_match:
            sx, sy = int(grid_match.group(1)), int(grid_match.group(2))
        else:
            sx = int(_first_number_near(req, ("wide", "cols", "columns"), 4))
            sy = int(_first_number_near(req, ("long", "rows", "deep"), 2))
        stud_d = _first_number_near(req, ("stud diameter", "diameter"), 4.8)
        stud_h = _first_number_near(req, ("stud height",), 1.8)
        hollow = "hollow" in req or "open" in req or True
        return {
            "description": f"Make a {sx}x{sy} Lego brick with hollow bottom.",
            "parts": [
                {
                    "type":           "lego_brick",
                    "name":           "lego_brick",
                    "studs_x":        sx,
                    "studs_y":        sy,
                    "stud_diameter":  stud_d,
                    "stud_height":    stud_h,
                    "plate_height":   9.6,
                    "wall_thickness": 1.2,
                    "hollow":         hollow,
                }
            ],
            "operations": [{"type": "assign", "part": "lego_brick"}],
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


def _is_main_intent(req: str, tokens: tuple) -> bool:
    """
    Returns True only if the request is PRIMARILY about one of the tokens —
    not just mentioning it as a feature (e.g. 'shaft holes', 'bracket mount').
    Checks that the token appears near the start or as the dominant noun.
    """
    import re
    for token in tokens:
        if token not in req:
            continue
        # Token must appear in first 40 chars OR be preceded by make/create/a/an/the
        idx = req.find(token)
        if idx < 40:
            return True
        preceding = req[max(0, idx - 15):idx]
        if re.search(r"\b(make|create|build|generate|a|an|the)\s*$", preceding):
            return True
    return False


def translator(user_request):
    """
    LLM-as-router architecture.

    The LLM sees the full request AND the available ready-made parts.
    It decides whether to:
      - Build from scratch using primitives
      - Use a ready-made part directly (type = "l_bracket", "flange", etc.)
      - Combine multiple ready-made parts
      - Use a ready-made part as a base and modify it

    No keyword matching. No bypassing the LLM.
    The LLM is the brain — patterns are optional tools it can reach for.

    Fallback: _offline_spec() only fires if LLM fails completely.
    """
    previous_memory = stage_manager.get_memory()

    error_memory_block = _build_error_memory_prompt()
    asset_library_block = _build_asset_library_prompt()
    system_prompt_with_memory = JSON_SYSTEM_RULE + asset_library_block + error_memory_block

    user_prompt = (
        f"Previous build context:\n{previous_memory}\n\n"
        f"Build request: {user_request}"
    )

    print("Builder Model Active...")
    if error_memory_block:
        print(f"[ErrorMemory] Injecting {min(_MAX_ERRORS_TO_INJECT, len(_load_error_memory()))} past mistakes into prompt")

    raw = ""
    try:
        # format_json=True = constrained decoding in local mode
        # In API mode it's ignored — API models reliably return JSON from the prompt alone
        raw = get_client().chat(
            system=system_prompt_with_memory,
            user=user_prompt,
            format_json=True,
        )
        print("\n[Builder Model]: JSON received.")
        spec = extract_json(raw)

    except (json.JSONDecodeError, ValueError) as exc:
        log_format_error(
            bad_output=raw,
            error_type="invalid_json",
            lesson=(
                "Your response was not valid JSON. "
                "Return ONLY a raw JSON object starting with { and ending with }. "
                "No markdown, no backticks, no explanation."
            ),
        )
        print(f"[AI Core] JSON parse failed: {exc} — trying LLM repair")
        spec = _repair_llm_json(system_prompt_with_memory, user_request, raw, exc)
        if spec is None:
            spec = _offline_or_none(user_request, "LLM JSON parse failed after repair")

    except Exception as exc:
        print(f"[AI Core] LLM failed: {exc}")
        spec = _offline_or_none(user_request, "LLM request failed")

    if spec is None:
        return None

    if not validate_json_spec(spec):
        bad_keys = list(spec.keys()) if isinstance(spec, dict) else []
        log_format_error(
            bad_output=raw,
            error_type="wrong_format",
            lesson=(
                f"You returned keys {bad_keys} instead of 'parts' and 'operations'. "
                'Return ONLY {"parts": [...], "operations": [...]}.'
            ),
        )
        print("[AI Core] Invalid spec — trying LLM repair")
        repaired = _repair_llm_json(system_prompt_with_memory, user_request, raw, ValueError("wrong JSON shape"))
        if repaired is not None:
            spec = repaired
        else:
            spec = _offline_or_none(user_request, "LLM returned invalid spec after repair")

    if spec is None:
        return None

    used_asset_reference = _uses_asset_reference(spec)
    spec = _expand_asset_references(spec)

    _save_json_spec(spec, user_request)

    try:
        filename = build_and_save(spec)
    except Exception as exc:
        print(f"[AI Core] Builder failed: {exc}")
        return None

    if not used_asset_reference:
        _register_generated_asset(user_request, spec)

    print("[AI Core] Build complete.")
    return filename


def _expand_asset_references(spec: dict) -> dict:
    """
    If the LLM used type="asset:name" to reference a ready-made part,
    expand it into the full part spec, letting the LLM override dimensions.

    Example:
        LLM returns: {"type": "asset:flange", "name": "output_flange", "outer_diameter": 50}
        Builder gets: full flange spec with outer_diameter overridden to 50

    This lets the LLM compose and customise patterns without knowing
    every internal parameter — it just says which pattern and what to change.
    """
    if "parts" not in spec:
        return spec

    parts = spec.get("parts", [])
    if len(parts) == 1:
        only_part = parts[0]
        ptype = only_part.get("type", "")
        if isinstance(ptype, str) and (ptype.startswith("asset:") or ptype.startswith("pattern:")):
            asset_name = ptype.split(":", 1)[1]
            asset = _asset_library().get(asset_name, {})
            asset_spec = asset.get("spec")
            if asset_spec and len(asset_spec.get("parts", [])) > 1:
                print(f"[AI Core] Expanded full asset: {asset_name}")
                return _clone_json(asset_spec)

    expanded = []
    for part in parts:
        ptype = part.get("type", "")
        if ptype.startswith("asset:") or ptype.startswith("pattern:"):
            pattern_name = ptype.split(":", 1)[1]
            asset = _asset_library().get(pattern_name, {})
            pattern = asset.get("spec")
            if pattern and pattern.get("parts"):
                # Use first part of pattern as base, override with LLM's values
                base = dict(pattern["parts"][0])
                base.update({k: v for k, v in part.items() if k != "type"})
                expanded.append(base)
                print(f"[AI Core] Expanded asset: {pattern_name}")
            else:
                expanded.append(part)
        else:
            expanded.append(part)

    spec["parts"] = expanded
    return spec

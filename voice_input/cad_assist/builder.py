"""Deterministic JSON to FreeCAD Python converter.

The LLM outputs JSON describing what to build. This module converts that JSON
to a complete FreeCAD script, so core geometry generation stays predictable.
"""

import json
from pathlib import Path

from voice_input.Keys.config import ai_gen_folder, ai_gen_script


def _build_box(p, name):
    l = p.get("l", 10)
    w = p.get("w", 10)
    h = p.get("h", 10)
    return f"{name} = Part.makeBox({l}, {w}, {h})"


def _build_cylinder(p, name):
    r = p.get("r", 5)
    h = p.get("h", 20)
    return f"{name} = Part.makeCylinder({r}, {h})"


def _build_sphere(p, name):
    r = p.get("r", 5)
    return f"{name} = Part.makeSphere({r})"


def _build_cone(p, name):
    r1 = p.get("r1", 5)
    r2 = p.get("r2", 0)
    h = p.get("h", 10)
    return f"{name} = Part.makeCone({r1}, {r2}, {h})"


def _build_torus(p, name):
    r1 = p.get("r1", 10)
    r2 = p.get("r2", 2)
    return f"{name} = Part.makeTorus({r1}, {r2})"


def _build_hex_prism(p, name):
    r = p.get("r", 8)
    h = p.get("h", 8)
    lines = [
        f"_pts_{name} = [App.Vector({r}*math.cos(math.pi/2 + 2*math.pi*i/6), {r}*math.sin(math.pi/2 + 2*math.pi*i/6), 0) for i in range(6)]",
        f"_pts_{name}.append(_pts_{name}[0])",
        f"_wire_{name} = Part.Wire([Part.LineSegment(_pts_{name}[i], _pts_{name}[i+1]).toShape() for i in range(6)])",
        f"{name} = Part.Face(_wire_{name}).extrude(App.Vector(0, 0, {h}))",
    ]
    return "\n".join(lines)


def _build_pipe(p, name):
    r_out = p.get("r_outer", 10)
    r_in = p.get("r_inner", 8)
    h = p.get("h", 60)
    lines = [
        f"_{name}_outer = Part.makeCylinder({r_out}, {h})",
        f"_{name}_inner = Part.makeCylinder({r_in}, {h})",
        f"{name} = _{name}_outer.cut(_{name}_inner)",
    ]
    return "\n".join(lines)


def _build_plate(p, name):
    l = p.get("l", p.get("length", 40))
    w = p.get("w", p.get("width", 20))
    h = p.get("h", p.get("thickness", 3))
    lines = [f"{name} = Part.makeBox({l}, {w}, {h})"]
    for i, hole in enumerate(p.get("holes", [])):
        x = hole.get("x", l / 2)
        y = hole.get("y", w / 2)
        r = hole.get("r", hole.get("diameter", 3) / 2)
        lines.extend(
            [
                f"_{name}_hole_{i} = Part.makeCylinder({r}, {h} + 0.2)",
                f"_{name}_hole_{i}.translate(App.Vector({x}, {y}, -0.1))",
                f"{name} = {name}.cut(_{name}_hole_{i})",
            ]
        )
    return "\n".join(lines)


def _build_l_bracket(p, name):
    l = p.get("l", p.get("length", 30))
    w = p.get("w", p.get("width", 18))
    h = p.get("h", p.get("height", 30))
    t = p.get("t", p.get("thickness", 3))
    hole_r = p.get("hole_r", p.get("hole_diameter", 4) / 2)
    lines = [
        f"{name}_base = Part.makeBox({l}, {w}, {t})",
        f"{name}_wall = Part.makeBox({l}, {t}, {h})",
        f"{name} = {name}_base.fuse({name}_wall)",
        f"_{name}_base_hole = Part.makeCylinder({hole_r}, {t} + 0.2)",
        f"_{name}_base_hole.translate(App.Vector({l} / 2, {w} / 2, -0.1))",
        f"{name} = {name}.cut(_{name}_base_hole)",
        f"_{name}_wall_hole = Part.makeCylinder({hole_r}, {t} + 0.2)",
        f"_{name}_wall_hole.rotate(App.Vector(0,0,0), App.Vector(1,0,0), 90)",
        f"_{name}_wall_hole.translate(App.Vector({l} / 2, -0.1, {h} / 2))",
        f"{name} = {name}.cut(_{name}_wall_hole)",
    ]
    return "\n".join(lines)


def _build_flange(p, name):
    outer_r = p.get("outer_r", p.get("outer_diameter", 30) / 2)
    inner_r = p.get("inner_r", p.get("inner_diameter", 10) / 2)
    h = p.get("h", p.get("thickness", 5))
    bolt_count = p.get("bolt_count", 4)
    bolt_r = p.get("bolt_r", p.get("bolt_diameter", 3) / 2)
    bolt_circle_r = p.get("bolt_circle_r", p.get("bolt_circle_diameter", outer_r * 1.35) / 2)
    lines = [
        f"{name} = Part.makeCylinder({outer_r}, {h})",
        f"_{name}_center = Part.makeCylinder({inner_r}, {h} + 0.2)",
        f"_{name}_center.translate(App.Vector(0, 0, -0.1))",
        f"{name} = {name}.cut(_{name}_center)",
        f"for i in range({bolt_count}):",
        f"    _a = 2 * math.pi * i / {bolt_count}",
        f"    _{name}_bolt = Part.makeCylinder({bolt_r}, {h} + 0.2)",
        f"    _{name}_bolt.translate(App.Vector({bolt_circle_r} * math.cos(_a), {bolt_circle_r} * math.sin(_a), -0.1))",
        f"    {name} = {name}.cut(_{name}_bolt)",
    ]
    return "\n".join(lines)


def _build_shaft(p, name):
    r = p.get("r", p.get("diameter", 8) / 2)
    h = p.get("h", p.get("length", 40))
    keyway = p.get("keyway", False)
    lines = [f"{name} = Part.makeCylinder({r}, {h})"]
    if keyway:
        key_w = p.get("key_width", r * 0.8)
        key_d = p.get("key_depth", r * 0.35)
        lines.extend(
            [
                f"_{name}_keyway = Part.makeBox({key_w}, {key_d}, {h} + 0.2)",
                f"_{name}_keyway.translate(App.Vector(-{key_w} / 2, {r} - {key_d}, -0.1))",
                f"{name} = {name}.cut(_{name}_keyway)",
            ]
        )
    return "\n".join(lines)


def _build_spur_gear(p, name):
    diameter = p.get("diameter", 4)
    teeth = p.get("teeth", 10)
    thickness = p.get("thickness", 3)
    root_diameter = p.get("root_diameter", diameter * 0.78)
    bore_diameter = p.get("bore_diameter", 0.9)
    lines = [
        f"_{name}_outer_r = {diameter} / 2",
        f"_{name}_root_r = {root_diameter} / 2",
        f"_{name}_pitch = 2 * math.pi / {teeth}",
        f"_{name}_pts = []",
        f"for i in range({teeth}):",
        f"    _a = i * _{name}_pitch",
        f"    for _off, _r in [(-0.46, _{name}_root_r), (-0.22, _{name}_outer_r), (0.22, _{name}_outer_r), (0.46, _{name}_root_r)]:",
        f"        _ang = _a + _off * _{name}_pitch",
        f"        _{name}_pts.append(App.Vector(_r * math.cos(_ang), _r * math.sin(_ang), 0))",
        f"_{name}_pts.append(_{name}_pts[0])",
        f"_{name}_wire = Part.Wire([Part.LineSegment(_{name}_pts[i], _{name}_pts[i + 1]).toShape() for i in range(len(_{name}_pts) - 1)])",
        f"{name} = Part.Face(_{name}_wire).extrude(App.Vector(0, 0, {thickness}))",
    ]
    if bore_diameter:
        lines.extend(
            [
                f"_{name}_bore = Part.makeCylinder({bore_diameter} / 2, {thickness} + 0.2)",
                f"_{name}_bore.translate(App.Vector(0, 0, -0.1))",
                f"{name} = {name}.cut(_{name}_bore)",
            ]
        )
    return "\n".join(lines)


def _build_sg90_servo_arm(p, name):
    length = p.get("length", 28)
    width = p.get("width", 5)
    thickness = p.get("thickness", 2)
    hub_diameter = p.get("hub_diameter", 7)
    shaft_bore_diameter = p.get("shaft_bore_diameter", 4.8)
    shaft_minor_diameter = p.get("shaft_minor_diameter", shaft_bore_diameter * 0.9)
    shaft_spline_teeth = p.get("shaft_spline_teeth", 21)
    screw_bore_diameter = p.get("screw_bore_diameter", 1.8)
    mounting_hole_diameter = p.get("mounting_hole_diameter", 1.4)
    mounting_hole_spacing = p.get("mounting_hole_spacing", 5)
    lines = [
        f"{name}_hub = Part.makeCylinder({hub_diameter} / 2, {thickness})",
        f"{name}_arm = Part.makeBox({length}, {width}, {thickness})",
        f"{name}_arm.translate(App.Vector(-{length} / 2, -{width} / 2, 0))",
        f"{name} = {name}_hub.fuse({name}_arm)",
        f"_{name}_spline_pts = []",
        f"for i in range({shaft_spline_teeth}):",
        f"    _a = 2 * math.pi * i / {shaft_spline_teeth}",
        f"    _{name}_spline_pts.append(App.Vector(({shaft_bore_diameter} / 2) * math.cos(_a), ({shaft_bore_diameter} / 2) * math.sin(_a), -0.1))",
        f"    _b = _a + math.pi / {shaft_spline_teeth}",
        f"    _{name}_spline_pts.append(App.Vector(({shaft_minor_diameter} / 2) * math.cos(_b), ({shaft_minor_diameter} / 2) * math.sin(_b), -0.1))",
        f"_{name}_spline_pts.append(_{name}_spline_pts[0])",
        f"_{name}_spline_wire = Part.Wire([Part.LineSegment(_{name}_spline_pts[i], _{name}_spline_pts[i + 1]).toShape() for i in range(len(_{name}_spline_pts) - 1)])",
        f"_{name}_shaft_bore = Part.Face(_{name}_spline_wire).extrude(App.Vector(0, 0, {thickness} + 0.2))",
        f"_{name}_screw_bore = Part.makeCylinder({screw_bore_diameter} / 2, {thickness} + 0.4)",
        f"_{name}_screw_bore.translate(App.Vector(0, 0, -0.2))",
        f"{name} = {name}.cut(_{name}_shaft_bore).cut(_{name}_screw_bore)",
        f"for _x in [{mounting_hole_spacing}, {mounting_hole_spacing} * 2, {mounting_hole_spacing} * 3, -{mounting_hole_spacing}, -{mounting_hole_spacing} * 2, -{mounting_hole_spacing} * 3]:",
        f"    _{name}_mount_hole = Part.makeCylinder({mounting_hole_diameter} / 2, {thickness} + 0.2)",
        f"    _{name}_mount_hole.translate(App.Vector(_x, 0, -0.1))",
        f"    {name} = {name}.cut(_{name}_mount_hole)",
    ]
    return "\n".join(lines)


PRIMITIVE_BUILDERS = {
    "box": _build_box,
    "cylinder": _build_cylinder,
    "sphere": _build_sphere,
    "cone": _build_cone,
    "torus": _build_torus,
    "hex_prism": _build_hex_prism,
    "pipe": _build_pipe,
    "plate": _build_plate,
    "l_bracket": _build_l_bracket,
    "flange": _build_flange,
    "shaft": _build_shaft,
    "spur_gear": _build_spur_gear,
    "sg90_servo_arm": _build_sg90_servo_arm,
}


def _build_transforms(part_spec, name):
    lines = []

    translate = part_spec.get("translate")
    if translate:
        lines.append(
            f"{name}.translate(App.Vector({translate[0]}, {translate[1]}, {translate[2]}))"
        )

    rotate = part_spec.get("rotate")
    if rotate:
        axis = rotate.get("axis", [0, 0, 1])
        angle = rotate.get("angle", 0)
        lines.append(
            f"{name}.rotate(App.Vector(0,0,0), App.Vector({axis[0]},{axis[1]},{axis[2]}), {angle})"
        )

    mirror = part_spec.get("mirror")
    if mirror:
        src = mirror.get("source", name)
        axis = mirror.get("axis", [0, 1, 0])
        lines.extend(
            [
                f"{name} = {src}.copy()",
                f"{name}.mirror(App.Vector(0,0,0), App.Vector({axis[0]},{axis[1]},{axis[2]}))",
            ]
        )

    return lines


def _build_finish_ops(part_spec, name):
    lines = []
    fillet = part_spec.get("fillet")
    if fillet:
        lines.append(f"{name} = {name}.makeFillet({fillet}, {name}.Edges)")
    chamfer = part_spec.get("chamfer")
    if chamfer:
        lines.append(f"{name} = {name}.makeChamfer({chamfer}, {name}.Edges)")
    return lines


def _build_boolean(operations, part_names):
    lines = []
    for op in operations:
        kind = op.get("type", "fuse_all")

        if kind == "fuse_all":
            if not part_names:
                lines.append("final_shape = Part.makeBox(1,1,1)")
            else:
                chain = part_names[0]
                for part_name in part_names[1:]:
                    chain = f"{chain}.fuse({part_name})"
                lines.append(f"final_shape = {chain}")

        elif kind == "fuse":
            parts = op.get("parts", part_names)
            if not parts:
                lines.append("final_shape = Part.makeBox(1,1,1)")
                continue
            chain = parts[0]
            for part_name in parts[1:]:
                chain = f"{chain}.fuse({part_name})"
            lines.append(f"final_shape = {chain}")

        elif kind == "cut":
            base = op.get("base")
            cutters = op.get("cutters", [])
            if not base:
                lines.append("final_shape = Part.makeBox(1,1,1)")
                continue
            chain = base
            for cutter in cutters:
                chain = f"{chain}.cut({cutter})"
            lines.append(f"final_shape = {chain}")

        elif kind == "assign":
            lines.append(f"final_shape = {op.get('part')}")

    if not any(line.startswith("final_shape =") for line in lines):
        lines.append("final_shape = Part.makeBox(1,1,1)")

    return lines


def json_to_freecad(json_spec: dict) -> str:
    """Convert a JSON model spec to a complete FreeCAD Python script."""
    lines = [
        "import FreeCAD as App",
        "import Part",
        "import math",
        "doc = App.newDocument('Model')",
        "",
    ]

    part_names = []
    for part in json_spec.get("parts", []):
        ptype = part.get("type")
        name = part.get("name", f"part_{len(part_names)}")
        part_names.append(name)

        builder = PRIMITIVE_BUILDERS.get(ptype)
        if builder:
            lines.append(builder(part, name))
        else:
            lines.append(f"{name} = Part.makeBox(10,10,10)")

        lines.extend(_build_transforms(part, name))
        lines.extend(_build_finish_ops(part, name))
        lines.append("")

    operations = json_spec.get("operations", [{"type": "fuse_all"}])
    lines.extend(_build_boolean(operations, part_names))

    lines += [
        "",
        "feature = doc.addObject('Part::Feature', 'Shape')",
        "feature.Shape = final_shape",
        "doc.recompute()",
        "from pathlib import Path",
        "_step_out = Path(__file__).resolve().parent / 'model.step'",
        "feature.Shape.exportStep(str(_step_out))",
    ]

    return "\n".join(lines)


def build_from_json_file(json_path: Path) -> str:
    """Load JSON spec from a file and return FreeCAD Python script text."""
    with open(json_path, "r") as file:
        spec = json.load(file)
    return json_to_freecad(spec)


def build_and_save(json_spec: dict) -> str:
    """Convert JSON spec to a script, save it, and return its filename."""
    script = json_to_freecad(json_spec)
    with open(ai_gen_script, "w") as file:
        file.write(script)
    print(f"[Builder] Script saved -> {ai_gen_script}")
    return "ai_gen_script.py"

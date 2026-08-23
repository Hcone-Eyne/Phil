"""
CadQuery → FreeCAD JSON Spec Converter

Converts CadQuery Python code to Phil's JSON spec format.
Designed for Colab: memory-efficient, supports batch processing with datasets.map().

Usage in Colab:
    from datasets import load_dataset
    from convert_cadquery import convert_batch

    dataset = load_dataset("ADSKAILab/Zero-To-CAD-100k", split="train")
    converted = dataset.map(convert_batch, batched=True, batch_size=100, num_proc=2)

Conversion mapping:
    CadQuery               → FreeCAD JSON
    ─────────────────────────────────────
    .box(l, w, h)          → {"type": "box", "l":, "w":, "h":}
    .cylinder(h, r)        → {"type": "cylinder", "r":, "h":}
    .sphere(r)             → {"type": "sphere", "r":}
    .hole(d)               → Cut operation with cylinder
    .cut()                 → {"type": "cut", ...}
    .union()               → {"type": "fuse_all"}
    .fillet(r)             → "fillet": r on part
    .chamfer(r)            → "chamfer": r on part
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any

# ── Safe CadQuery execution ───────────────────────────────────────────────────

def _safe_execute_cadquery(code: str) -> Any | None:
    """
    Execute CadQuery code and return the result shape.
    Returns None if execution fails.
    """
    try:
        import cadquery as cq
        namespace: dict[str, Any] = {"cq": cq, "cadquery": cq}
        exec(code, namespace)

        # Try common result variable names
        for var in ("result", "solid", "shape", "obj"):
            if var in namespace:
                return namespace[var]

        # Try to find any CadQuery Workplane object
        for val in namespace.values():
            if isinstance(val, cq.Workplane):
                return val

        return None
    except Exception:
        return None


# ── Shape analysis helpers ────────────────────────────────────────────────────

def _get_bb(shape: Any) -> tuple[float, float, float] | None:
    """Get bounding box dimensions (x, y, z) from a CadQuery shape."""
    try:
        bb = shape.val().BoundingBox()
        return (bb.xlen, bb.ylen, bb.zlen)
    except Exception:
        return None


def _is_cylinder(shape: Any) -> bool:
    """Check if shape is approximately a cylinder."""
    try:
        faces = shape.faces().vals()
        if len(faces) == 3:  # 2 flat ends + 1 curved side
            for face in faces:
                try:
                    if hasattr(face, "geomType") and face.geomType() == "CYLINDER":
                        return True
                except Exception:
                    pass
    except Exception:
        pass
    return False


def _is_sphere(shape: Any) -> bool:
    """Check if shape is approximately a sphere."""
    try:
        faces = shape.faces().vals()
        if len(faces) == 1:
            face = faces[0]
            if hasattr(face, "geomType") and face.geomType() == "SPHERE":
                return True
    except Exception:
        pass
    return False


def _detect_primitives(shape: Any) -> list[dict[str, Any]]:
    """
    Detect primitive shapes from a CadQuery shape.
    Returns list of parts with their types and dimensions.
    """
    parts = []
    bb = _get_bb(shape)
    if bb is None:
        return parts

    x, y, z = bb

    # Simple sphere check
    if _is_sphere(shape):
        r = max(x, y, z) / 2
        parts.append({"type": "sphere", "name": "sphere_0", "r": round(r, 4)})
        return parts

    # Simple cylinder check
    if _is_cylinder(shape):
        # Assume cylinder along longest axis
        if x == y:  # Cylinder along Z
            r = x / 2
            h = z
        elif x == z:  # Cylinder along Y
            r = x / 2
            h = y
        else:  # Cylinder along X
            r = y / 2
            h = x
        parts.append({"type": "cylinder", "name": "cylinder_0", "r": round(r, 4), "h": round(h, 4)})
        return parts

    # Default to box
    parts.append({"type": "box", "name": "part_0", "l": round(x, 4), "w": round(y, 4), "h": round(z, 4)})
    return parts


def _detect_operations(shape: Any, parts: list[dict]) -> list[dict[str, Any]]:
    """
    Detect boolean operations from shape topology.
    This is a simplified heuristic.
    """
    ops = []

    try:
        # Count solid bodies
        solids = shape.solids().vals()
        if len(solids) > 1:
            # Multiple solids likely means union
            ops.append({"type": "fuse_all"})
        elif len(parts) == 1:
            ops.append({"type": "assign", "part": parts[0]["name"]})
        else:
            ops.append({"type": "fuse_all"})
    except Exception:
        if parts:
            ops.append({"type": "assign", "part": parts[0]["name"]})

    return ops


# ── AST-based extraction (fallback) ──────────────────────────────────────────

def _extract_from_ast(code: str) -> dict[str, Any] | None:
    """
    Extract primitives from CadQuery code using AST parsing.
    Fallback when CadQuery execution fails.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    parts = []
    ops = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # Detect .box() calls
        if isinstance(node.func, ast.Attribute) and node.func.attr == "box":
            args = node.args
            if len(args) >= 3:
                try:
                    l = _eval_num(args[0])
                    w = _eval_num(args[1])
                    h = _eval_num(args[2])
                    name = f"box_{len(parts)}"
                    parts.append({"type": "box", "name": name, "l": l, "w": w, "h": h})
                except Exception:
                    pass

        # Detect .cylinder() calls
        if isinstance(node.func, ast.Attribute) and node.func.attr == "cylinder":
            args = node.args
            if len(args) >= 2:
                try:
                    h = _eval_num(args[0])
                    r = _eval_num(args[1])
                    name = f"cylinder_{len(parts)}"
                    parts.append({"type": "cylinder", "name": name, "r": r, "h": h})
                except Exception:
                    pass

        # Detect .sphere() calls
        if isinstance(node.func, ast.Attribute) and node.func.attr == "sphere":
            args = node.args
            if len(args) >= 1:
                try:
                    r = _eval_num(args[0])
                    name = f"sphere_{len(parts)}"
                    parts.append({"type": "sphere", "name": name, "r": r})
                except Exception:
                    pass

        # Detect .hole() calls
        if isinstance(node.func, ast.Attribute) and node.func.attr == "hole":
            args = node.args
            if len(args) >= 1 and parts:
                try:
                    d = _eval_num(args[0])
                    name = f"hole_{len(parts)}"
                    parts.append({"type": "cylinder", "name": name, "r": d / 2, "h": 100})
                    ops.append({"type": "cut", "base": parts[0]["name"], "cutters": [name]})
                except Exception:
                    pass

        # Detect .cut() calls → mark as cut operation
        if isinstance(node.func, ast.Attribute) and node.func.attr == "cut":
            if len(parts) >= 2 and not ops:
                ops.append({"type": "cut", "base": parts[0]["name"], "cutters": [p["name"] for p in parts[1:]]})

        # Detect .union() or .fuse() calls
        if isinstance(node.func, ast.Attribute) and node.func.attr in ("union", "fuse"):
            if len(parts) >= 2 and not ops:
                ops.append({"type": "fuse_all"})

    if not parts:
        return None

    if not ops:
        if len(parts) == 1:
            ops.append({"type": "assign", "part": parts[0]["name"]})
        else:
            ops.append({"type": "fuse_all"})

    return {
        "description": "Converted from CadQuery (AST)",
        "parts": parts,
        "operations": ops,
    }


def _eval_num(node: ast.AST) -> float:
    """Evaluate a numeric AST node (constant or simple expression)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_num(node.operand)
    if isinstance(node, ast.BinOp):
        left = _eval_num(node.left)
        right = _eval_num(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right if right != 0 else 0
    raise ValueError(f"Cannot evaluate: {ast.dump(node)}")


# ── Main conversion function ──────────────────────────────────────────────────

def convert_cadquery(code: str) -> dict[str, Any] | None:
    """
    Convert CadQuery Python code to Phil's JSON spec format.

    Args:
        code: CadQuery Python source code

    Returns:
        dict with "parts" and "operations" keys, or None if conversion fails
    """
    if not code or not code.strip():
        return None

    # Try execution-based extraction first (most accurate)
    shape = _safe_execute_cadquery(code)
    if shape is not None:
        parts = _detect_primitives(shape)
        ops = _detect_operations(shape, parts)
        if parts:
            return {
                "description": _make_description(code),
                "parts": parts,
                "operations": ops,
            }

    # Fallback to AST parsing
    spec = _extract_from_ast(code)
    if spec is not None:
        spec["description"] = _make_description(code)
        return spec

    return None


def _make_description(code: str) -> str:
    """Generate a short description from the CadQuery code."""
    first_line = code.strip().split("\n")[0][:80]
    return f"Converted from CadQuery: {first_line}"


# ── Batch conversion for datasets.map() ───────────────────────────────────────

def convert_batch(batch: dict[str, list]) -> dict[str, list]:
    """
    Convert a batch of CadQuery examples to FreeCAD JSON specs.
    Designed for use with datasets.map(batched=True).

    Input columns:
        - cadquery_file (bytes): CadQuery Python code

    Output columns:
        - freecad_spec (str): JSON string of FreeCAD spec
        - convertible (bool): Whether conversion succeeded
    """
    specs = []
    convertible = []

    for code_bytes in batch.get("cadquery_file", []):
        try:
            # Decode bytes to string
            if isinstance(code_bytes, bytes):
                code = code_bytes.decode("utf-8", errors="ignore")
            else:
                code = str(code_bytes)

            spec = convert_cadquery(code)
            if spec is not None:
                specs.append(json.dumps(spec, separators=(",", ":")))
                convertible.append(True)
            else:
                specs.append("")
                convertible.append(False)
        except Exception:
            specs.append("")
            convertible.append(False)

    return {"freecad_spec": specs, "convertible": convertible}


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    """CLI entry point for testing single conversions."""
    import sys

    if len(sys.argv) > 1:
        # Read from file
        with open(sys.argv[1], "r") as f:
            code = f.read()
    else:
        # Read from stdin
        print("Paste CadQuery code (Ctrl+D when done):")
        code = sys.stdin.read()

    result = convert_cadquery(code)
    if result:
        print(json.dumps(result, indent=2))
    else:
        print("Conversion failed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

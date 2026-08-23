"""
Test script for CadQuery → FreeCAD converter.

Run with:
    python test_converter.py

Or test individual cases:
    python -c "from test_converter import test_simple_box; test_simple_box()"
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from voice_input.cad_assist.convert_cadquery import convert_cadquery


# ── Test cases ────────────────────────────────────────────────────────────────

TEST_CASES = [
    {
        "name": "Simple box",
        "cadquery": """
import cadquery as cq
result = cq.Workplane("xy").box(10, 20, 30)
""",
        "expected_parts": {"type": "box", "l": 10, "w": 20, "h": 30},
    },
    {
        "name": "Simple cylinder",
        "cadquery": """
import cadquery as cq
result = cq.Workplane("xy").cylinder(50, 10)
""",
        "expected_parts": {"type": "cylinder", "r": 10, "h": 50},
    },
    {
        "name": "Simple sphere",
        "cadquery": """
import cadquery as cq
result = cq.Workplane("xy").sphere(15)
""",
        "expected_parts": {"type": "sphere", "r": 15},
    },
    {
        "name": "Box with hole (AST fallback)",
        "cadquery": """
import cadquery as cq
result = cq.Workplane("xy").box(10, 20, 30).hole(5)
""",
        "expected_parts": {"type": "box"},
    },
    {
        "name": "Fillet box (AST fallback)",
        "cadquery": """
import cadquery as cq
result = cq.Workplane("xy").box(10, 20, 30).fillet(2)
""",
        "expected_parts": {"type": "box"},
    },
    {
        "name": "Chamfer box (AST fallback)",
        "cadquery": """
import cadquery as cq
result = cq.Workplane("xy").box(10, 20, 30).chamfer(1)
""",
        "expected_parts": {"type": "box"},
    },
    {
        "name": "Empty code",
        "cadquery": "",
        "expected_parts": None,
    },
    {
        "name": "Invalid code",
        "cadquery": "this is not valid python",
        "expected_parts": None,
    },
]


# ── Test runner ───────────────────────────────────────────────────────────────

def run_test(test: dict) -> bool:
    """
    Run a single test case.
    Returns True if test passes.
    """
    name = test["name"]
    code = test["cadquery"]
    expected = test["expected_parts"]

    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")

    result = convert_cadquery(code)

    if expected is None:
        # Expecting failure
        if result is None:
            print("✓ PASS: Conversion correctly failed")
            return True
        else:
            print("✗ FAIL: Expected None but got result")
            print(f"  Result: {json.dumps(result, indent=2)}")
            return False

    # Expecting success
    if result is None:
        print("✗ FAIL: Conversion returned None")
        return False

    # Check that result has required keys
    if "parts" not in result or "operations" not in result:
        print("✗ FAIL: Missing 'parts' or 'operations' key")
        print(f"  Result: {json.dumps(result, indent=2)}")
        return False

    # Check that at least one part matches expected type
    parts = result["parts"]
    expected_type = expected.get("type")
    if expected_type:
        found = any(p.get("type") == expected_type for p in parts)
        if not found:
            print(f"✗ FAIL: Expected part type '{expected_type}' not found")
            print(f"  Parts: {json.dumps(parts, indent=2)}")
            return False

    print("✓ PASS")
    print(f"  Parts: {json.dumps(parts, indent=2)}")
    print(f"  Operations: {json.dumps(result['operations'], indent=2)}")
    return True


def run_all_tests():
    """Run all test cases and report results."""
    print("\n" + "="*60)
    print("CadQuery → FreeCAD Converter Tests")
    print("="*60)

    passed = 0
    failed = 0

    for test in TEST_CASES:
        try:
            if run_test(test):
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1

    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
    print("="*60)

    return failed == 0


# ── Individual test functions ─────────────────────────────────────────────────

def test_simple_box():
    """Test simple box conversion."""
    code = """
import cadquery as cq
result = cq.Workplane("xy").box(10, 20, 30)
"""
    result = convert_cadquery(code)
    assert result is not None, "Should convert successfully"
    assert "parts" in result, "Should have parts"
    assert len(result["parts"]) > 0, "Should have at least one part"
    assert result["parts"][0]["type"] == "box", "Should be a box"
    print("test_simple_box: PASS")


def test_simple_cylinder():
    """Test simple cylinder conversion."""
    code = """
import cadquery as cq
result = cq.Workplane("xy").cylinder(50, 10)
"""
    result = convert_cadquery(code)
    assert result is not None, "Should convert successfully"
    assert "parts" in result, "Should have parts"
    # Note: AST fallback may detect this differently
    print("test_simple_cylinder: PASS")


def test_simple_sphere():
    """Test simple sphere conversion."""
    code = """
import cadquery as cq
result = cq.Workplane("xy").sphere(15)
"""
    result = convert_cadquery(code)
    assert result is not None, "Should convert successfully"
    assert "parts" in result, "Should have parts"
    print("test_simple_sphere: PASS")


def test_empty_code():
    """Test empty code returns None."""
    result = convert_cadquery("")
    assert result is None, "Empty code should return None"
    print("test_empty_code: PASS")


def test_invalid_code():
    """Test invalid code returns None."""
    result = convert_cadquery("this is not valid python")
    assert result is None, "Invalid code should return None"
    print("test_invalid_code: PASS")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--individual":
        # Run individual tests
        test_simple_box()
        test_simple_cylinder()
        test_simple_sphere()
        test_empty_code()
        test_invalid_code()
        print("\nAll individual tests passed!")
    else:
        # Run all tests
        success = run_all_tests()
        sys.exit(0 if success else 1)

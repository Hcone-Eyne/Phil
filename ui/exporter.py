"""
FILE: ui/exporter.py

Handles exporting the AI-generated 3D model to FreeCAD or Blender.

MODES for each target:
  - "save"   → file-picker dialog → user chooses where to save the file
  - "import" → directly launches the app and imports the model into it
  - "reveal" → reveals the file in Finder (fallback / drag-and-drop mode)

Junior note:
  tkinter.filedialog.asksaveasfilename() opens the native macOS Save panel.
  subprocess.run() launches external processes (FreeCAD / Blender).
"""

import subprocess
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

from voice_input.Keys.config import ai_gen_folder, blender_cmd, free_cad_cmd, free_cad_gui

# ── Artefact file path definitions ───────────────────────────────────────────
_step_file = ai_gen_folder / "model.step"
_obj_file = ai_gen_folder / "model.obj"


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _pick_save_path(title: str, default_name: str, file_types: list) -> Path | None:
    """
    Opens a native Save dialog.
    Returns a Path if the user picked a location, or None if they cancelled.

    We create + hide a tiny Tk root so the dialog can appear without
    an extra blank window showing up.
    """
    root = tk.Tk()
    root.withdraw()          # hide the blank root window
    root.attributes("-topmost", True)   # dialog appears on top of everything

    chosen = filedialog.asksaveasfilename(
        parent=root,
        title=title,
        initialfile=default_name,
        filetypes=file_types,
        defaultextension=file_types[0][1],
    )
    root.destroy()
    return Path(chosen) if chosen else None


def _show_message(title: str, message: str, kind: str = "info"):
    """Shows a native macOS dialog (info / error)."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    if kind == "error":
        messagebox.showerror(title, message, parent=root)
    else:
        messagebox.showinfo(title, message, parent=root)
    root.destroy()


def _reveal_in_finder(path: Path):
    """Reveals the file in Finder — classic drag-and-drop preparation."""
    subprocess.run(["open", "-R", str(path)])


# =============================================================================
# STEP / FreeCAD EXPORT
# =============================================================================

def export_to_freecad(mode: str = "save"):
    """
    Export the model.step file for FreeCAD.

    mode="save"   → opens Save dialog so user picks where to store the copy
    mode="import" → launches FreeCAD and opens the model directly
    mode="reveal" → reveals model.step in Finder (drag-and-drop)
    """
    if not _step_file.exists():
        _show_message("No Model", "No model.step file found.\nPlease generate a model first.", "error")
        return False

    if mode == "reveal":
        _reveal_in_finder(_step_file)
        print("[Exporter] Revealed model.step in Finder.")
        return True

    if mode == "import":
        try:
            subprocess.Popen([free_cad_gui, str(_step_file)])
            print(f"[Exporter] Launched FreeCAD with: {_step_file}")
            return True
        except FileNotFoundError:
            _show_message(
                "FreeCAD Not Found",
                f"FreeCAD was not found at:\n{free_cad_gui}\n"
                "Set FREECAD_GUI or install FreeCAD.\n"
                "Falling back to Finder reveal.",
                "error",
            )
            _reveal_in_finder(_step_file)
            return False

    # mode == "save" (default)
    dest = _pick_save_path(
        title="Save STEP file for FreeCAD",
        default_name="model.step",
        file_types=[("STEP files", "*.step"), ("All files", "*.*")],
    )
    if dest is None:
        print("[Exporter] User cancelled Save dialog.")
        return False

    shutil.copy2(_step_file, dest)
    print(f"[Exporter] STEP file saved to: {dest}")
    _show_message("Saved!", f"Model saved to:\n{dest}")
    return True


# =============================================================================
# OBJ / Blender EXPORT
# =============================================================================

def _build_obj_conversion_script(step_src: Path, obj_dest: Path) -> str:
    """
    Returns a FreeCAD Python script that:
      1. Reads the STEP file
      2. Tessellates it into a mesh
      3. Exports it as OBJ

    This script is run headlessly by freecadcmd.
    """
    return f"""\
import FreeCAD as App
import Part
import Mesh

shape = Part.read(r'{step_src.as_posix()}')
doc = App.newDocument('Export')
feature = doc.addObject('Part::Feature', 'Shape')
feature.Shape = shape
doc.recompute()

mesh_obj = doc.addObject('Mesh::Feature', 'Mesh')
mesh_obj.Mesh = Mesh.Mesh(shape.tessellate(0.1))
Mesh.export([mesh_obj], r'{obj_dest.as_posix()}')
print("OBJ export done")
"""


def _convert_step_to_obj(obj_dest: Path) -> bool:
    """
    Converts model.step → OBJ at obj_dest using FreeCAD headlessly.
    Returns True on success.
    """
    if not _step_file.exists():
        return False

    temp_script = ai_gen_folder / "_convert_to_obj.py"
    temp_script.write_text(_build_obj_conversion_script(_step_file, obj_dest))

    try:
        result = subprocess.run(
            [free_cad_cmd, str(temp_script)],
            capture_output=True,
            text=True,
            timeout=60,           # OBJ conversion can take a moment on large models
        )
        return obj_dest.exists()
    except subprocess.TimeoutExpired:
        print("[Exporter] OBJ conversion timed out.")
        return False
    finally:
        if temp_script.exists():
            temp_script.unlink()


def export_to_blender(mode: str = "save"):
    """
    Export the model for Blender.

    mode="save"   → converts STEP → OBJ, then opens Save dialog
    mode="import" → converts STEP → OBJ, then launches Blender and imports it
    mode="reveal" → converts STEP → OBJ in the ai_gen_folder, reveals in Finder
    """
    if not _step_file.exists():
        _show_message("No Model", "No model.step file found.\nPlease generate a model first.", "error")
        return False

    if mode == "reveal":
        # Convert into the default ai_gen_folder location, then reveal
        print("[Exporter] Converting to OBJ for Finder reveal…")
        if _convert_step_to_obj(_obj_file):
            _reveal_in_finder(_obj_file)
            print(f"[Exporter] Revealed model.obj in Finder.")
        else:
            _show_message("Conversion Failed",
                          "Could not convert model.step to OBJ.\n"
                          "Make sure FreeCAD is installed at the configured path.", "error")
        return _obj_file.exists()

    if mode == "import":
        # Convert, then launch Blender with an auto-import Python script
        print("[Exporter] Converting to OBJ for Blender import…")
        tmp_obj = ai_gen_folder / "_blender_import.obj"
        if not _convert_step_to_obj(tmp_obj):
            _show_message("Conversion Failed",
                          "Could not convert model.step to OBJ.", "error")
            return False

        # Build a tiny Blender Python script that imports the OBJ
        blender_import_script = ai_gen_folder / "_blender_import.py"
        blender_import_script.write_text("""\
import bpy
from pathlib import Path

_obj = Path(__file__).resolve().parent / "_blender_import.obj"
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.wm.obj_import(filepath=str(_obj))
""")
        try:
            subprocess.Popen([
                blender_cmd,
                "--python", str(blender_import_script),
            ])
            print(f"[Exporter] Launched Blender with: {tmp_obj}")
            return True
        except FileNotFoundError:
            _show_message(
                "Blender Not Found",
                f"Blender was not found at:\n{blender_cmd}\n\n"
                "Set BLENDER_CMD or install Blender.\n"
                "Falling back to Finder reveal.",
                "error",
            )
            _reveal_in_finder(tmp_obj)
            return False

    # mode == "save" (default)
    dest = _pick_save_path(
        title="Save OBJ file for Blender",
        default_name="model.obj",
        file_types=[("OBJ files", "*.obj"), ("All files", "*.*")],
    )
    if dest is None:
        print("[Exporter] User cancelled Save dialog.")
        return False

    print(f"[Exporter] Converting STEP → OBJ at: {dest}")
    if _convert_step_to_obj(dest):
        print(f"[Exporter] OBJ saved to: {dest}")
        _show_message("Saved!", f"Model saved to:\n{dest}")
        return True
    else:
        _show_message("Conversion Failed",
                      "Could not convert model.step to OBJ.\n"
                      "Make sure FreeCAD is installed.", "error")
        return False


# =============================================================================
# LEGACY ALIASES — keep old names working so nothing breaks
# =============================================================================

def step_file_revealer():
    """Legacy: reveals the STEP file in Finder."""
    return export_to_freecad(mode="reveal")


def convetor_expot_obj():
    """Legacy (+ fixed typo): converts STEP → OBJ and reveals in Finder."""
    return export_to_blender(mode="reveal")
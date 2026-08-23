import bpy
from pathlib import Path

_obj = Path(__file__).resolve().parent / "_blender_import.obj"
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.wm.obj_import(filepath=str(_obj))

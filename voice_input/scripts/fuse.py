''' this code is going to fuse 2 indidual 3d/2d objects '''

# importing nessary libraries from freecad
import sys
sys.path.append("/Applications/FreeCAD.app/Contents/Resources/lib")

# importing nessary modules
import FreeCAD # type: ignore
import Part # type: ignore

# 1.create a new document
doc = FreeCAD.newDocument("Fusion 1")

# 2.1 making 3d object which is box
base = Part.makeBox(40,40,5)

# 2.2 making 3d object which is cylinder
# r = 5 , h = 20 positioned at x = 20 y = 20
cylinder = Part.makeCylinder(5,20,FreeCAD.Vector(20,20,0))

# 3. performing fuse operation
fused_shape = base.fuse(cylinder)

# 4. adding this to document
part = doc.addObject("Part::Feature", "Fused_Object")
part.Shape = fused_shape

# saving file in .step extension
from pathlib import Path
_output_dir = Path(__file__).resolve().parent.parent / "output"
_output_dir.mkdir(parents=True, exist_ok=True)
output_path = str(_output_dir / "fused.step")
part.Shape.exportStep(output_path)

print("Sucess!, Saved to", output_path)
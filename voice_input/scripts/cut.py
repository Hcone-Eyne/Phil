''' this code is going to cut 2 indidual 2d/3d object '''

# importing nessary libraries from freecad
import sys
sys.path.append("/Applications/FreeCAD.app/Contents/Resources/lib")

# importing nessary module
import FreeCAD # type: ignore
import Part # type: ignore

# 1.create a new document
doc = FreeCAD.newDocument("Cut 1")

# 2.1 making 3d object which is box
base = Part.makeBox(40,40,5)

# 2.2 making 3d object which is cylinder
# r = 5, h = 20 and vectors x = 20, y = 20 (center) and z = -5(all the way through)
# its acts as driller in box 
cylinder = Part.makeCylinder(5,20,FreeCAD.Vector(20,20,-5))

# 3. performing cut operation (using basic minus tool)
hollow_box = base.cut(cylinder)

# 4. adding this to document
part = doc.addObject("Part::Feature", "Holey_box")
part.Shape = hollow_box

# saving it as .step extension file
from pathlib import Path
_output_dir = Path(__file__).resolve().parent.parent / "output"
_output_dir.mkdir(parents=True, exist_ok=True)
output_path = str(_output_dir / "cut.step")
part.Shape.exportStep(output_path)

print("Sucess!, Saved to", output_path)
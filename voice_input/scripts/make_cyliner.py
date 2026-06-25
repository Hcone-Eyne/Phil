''' This is part is going to be used for making cylinder '''
# accessing library of freecad 
import sys
sys.path.append("/Applications/FreeCAD.app/Contents/Resources/lib")
# again importing nessary library
import FreeCAD # type: ignore
import Part  # type: ignore

# 1. creating document
doc = FreeCAD.newDocument("Version_1")

# 2. making cylinder
cylinder = Part.makeCylinder(20, 40)

# 3, appending the created shape to the document
part = doc.addObject("Part::Feature", "Version_1")
part.Shape = cylinder

# 4. saving it as .step as it is universal
from pathlib import Path
_output_dir = Path(__file__).resolve().parent.parent / "output"
_output_dir.mkdir(parents=True, exist_ok=True)
output_path = str(_output_dir / "cylinder.step")
part.Shape.exportStep(output_path)

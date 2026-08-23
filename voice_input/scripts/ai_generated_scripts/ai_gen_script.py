import FreeCAD as App
import Part
import math
doc = App.newDocument('Model')

cube = Part.makeBox(1, 1, 1)

final_shape = cube

feature = doc.addObject('Part::Feature', 'Shape')
feature.Shape = final_shape
doc.recompute()
from pathlib import Path
_step_out = Path(__file__).resolve().parent / 'model.step'
feature.Shape.exportStep(str(_step_out))
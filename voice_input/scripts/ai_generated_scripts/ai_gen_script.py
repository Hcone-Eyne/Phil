import FreeCAD as App
import Part
import math
doc = App.newDocument('Model')

block = Part.makeBox(6.0, 0.15, 3.0)

final_shape = block

feature = doc.addObject('Part::Feature', 'Shape')
feature.Shape = final_shape
doc.recompute()
from pathlib import Path
_step_out = Path(__file__).resolve().parent / 'model.step'
feature.Shape.exportStep(str(_step_out))
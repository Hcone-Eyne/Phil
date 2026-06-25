import FreeCAD as App
import Part
import math
doc = App.newDocument('Model')

housing_body = Part.makeCylinder(15, 50)
housing_body.translate(App.Vector(0, 0, 0))
housing_body.rotate(App.Vector(0,0,0), App.Vector(0,0,1), 0)

shaft_hole = Part.makeCylinder(5, 50.2)
shaft_hole.translate(App.Vector(0, 0, -0.1))
shaft_hole.rotate(App.Vector(0,0,0), App.Vector(0,0,1), 0)

final_shape = housing_body.cut(shaft_hole)
final_shape = housing_body

feature = doc.addObject('Part::Feature', 'Shape')
feature.Shape = final_shape
doc.recompute()
from pathlib import Path
_step_out = Path(__file__).resolve().parent / 'model.step'
feature.Shape.exportStep(str(_step_out))

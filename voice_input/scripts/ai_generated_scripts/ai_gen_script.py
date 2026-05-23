import FreeCAD as App
import Part
import math
doc = App.newDocument('Model')

shaft = Part.makeCylinder(4.0, 40)

final_shape = shaft

feature = doc.addObject('Part::Feature', 'Shape')
feature.Shape = final_shape
doc.recompute()
feature.Shape.exportStep('/Users/enoch/Desktop/Free_Cad_Extension/voice_input/scripts/ai_generated_scripts/model.step')
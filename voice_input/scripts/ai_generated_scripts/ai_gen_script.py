import FreeCAD as App
import Part
import math
doc = App.newDocument('Model')

_spur_gear_outer_r = 4.0 / 2
_spur_gear_root_r = 3.12 / 2
_spur_gear_pitch = 2 * math.pi / 10
_spur_gear_pts = []
for i in range(10):
    _a = i * _spur_gear_pitch
    for _off, _r in [(-0.46, _spur_gear_root_r), (-0.22, _spur_gear_outer_r), (0.22, _spur_gear_outer_r), (0.46, _spur_gear_root_r)]:
        _ang = _a + _off * _spur_gear_pitch
        _spur_gear_pts.append(App.Vector(_r * math.cos(_ang), _r * math.sin(_ang), 0))
_spur_gear_pts.append(_spur_gear_pts[0])
_spur_gear_wire = Part.Wire([Part.LineSegment(_spur_gear_pts[i], _spur_gear_pts[i + 1]).toShape() for i in range(len(_spur_gear_pts) - 1)])
spur_gear = Part.Face(_spur_gear_wire).extrude(App.Vector(0, 0, 3.0))
_spur_gear_bore = Part.makeCylinder(0.88 / 2, 3.0 + 0.2)
_spur_gear_bore.translate(App.Vector(0, 0, -0.1))
spur_gear = spur_gear.cut(_spur_gear_bore)

final_shape = spur_gear

feature = doc.addObject('Part::Feature', 'Shape')
feature.Shape = final_shape
doc.recompute()
feature.Shape.exportStep('/Users/enoch/Desktop/Free_Cad_Extension/voice_input/scripts/ai_generated_scripts/model.step')
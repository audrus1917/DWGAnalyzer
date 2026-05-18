import ezdxf
from ezdxf import colors, math
from ezdxf.render import ARROWS
from ezdxf.render import forms, mleader
from ezdxf.math import Vec2

DXFVERSION = "R2018"

doc = ezdxf.new(DXFVERSION, setup=True)
msp = doc.modelspace()
ml_builder = msp.add_multileader_mtext("Standard")
ml_builder.set_content("Line1\nLine2", style="OpenSans")

ml_builder.add_leader_line(mleader.ConnectionSide.right, [Vec2(40, 15)])
ml_builder.add_leader_line(mleader.ConnectionSide.right, [Vec2(40, -15)])
ml_builder.add_leader_line(mleader.ConnectionSide.left, [Vec2(-20, -15)])

# The insert point (in UCS coordinates= is the alignment point for MTEXT
# content and the insert location for BLOCK content:
ml_builder.build(insert=Vec2(10, 10))

doc.set_modelspace_vport(100, center=(0, 0))

doc.saveas("mleader_example.dxf")

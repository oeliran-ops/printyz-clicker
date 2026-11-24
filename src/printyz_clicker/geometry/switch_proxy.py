"""Visual stand-in for an MX switch (preview / exploded view only - never printed)."""

from __future__ import annotations

from build123d import Align, Box, Cylinder, Plane, Pos, Rectangle, loft

from ..config.mechanical import MechanicalProfile

_MIN = (Align.CENTER, Align.CENTER, Align.MIN)


def switch_proxy(mech: MechanicalProfile, stem_top_z: float):
    """Housing (z from under-plate to housing top) + stem cross up to stem_top_z. World frame, at origin."""
    sw = mech.switch
    pt = mech.plate_top_z
    pb = pt - sw.plate_thickness
    lower = Pos(0, 0, pt - sw.below_plate_depth) * Box(13.8, 13.8, sw.below_plate_depth, align=_MIN)
    upper = loft([Plane.XY.offset(pt) * Rectangle(14.6, 14.6),
                  Plane.XY.offset(pt + sw.housing_top_above_plate) * Rectangle(11.0, 9.5)])
    housing = lower + upper
    pin = Pos(-3.8, 2.5, pt - sw.below_plate_depth - sw.pin_length) * Cylinder(0.5, sw.pin_length, align=_MIN)
    pin2 = Pos(2.5, 5.0, pt - sw.below_plate_depth - sw.pin_length) * Cylinder(0.5, sw.pin_length, align=_MIN)
    z0 = pt + sw.housing_top_above_plate - 1.0
    h = stem_top_z - z0
    stem = Pos(0, 0, z0) * (Box(4.0, 1.2, h, align=_MIN) + Box(1.2, 4.0, h, align=_MIN))
    _ = pb
    return housing + pin + pin2, stem

"""Body engine: one solid holding all switches. Closed bottom, rounded outside,
per-cell recess + MX plate hole + under-plate pocket, optional grooves and keychain tab."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from build123d import (
    Align, Axis, Box, Circle, Cylinder, Kind, Plane, Polygon, Pos, Rectangle, RectangleRounded,
    Rot, Solid, extrude, fillet, loft, offset,
)

from ..config.mechanical import MechanicalProfile
from ..layout.engine import LayoutResult
from ..model.project import BodyDesign, KeychainSpec


@dataclass
class BodyResult:
    solid: Solid
    outline_bbox: tuple[float, float, float, float]   # xmin, ymin, xmax, ymax
    keychain_hole: tuple[float, float] | None = None
    warnings: list[str] = field(default_factory=list)


def _rounded_square(w: float, r: float, z: float = 0.0):
    return Plane.XY.offset(z) * RectangleRounded(w, w, min(r, w / 2 - 0.05))


def body_outline(layout: LayoutResult, mech: MechanicalProfile):
    b = mech.body
    p = layout.pitch
    sk = None
    for k in layout.keys:
        sq = Pos(k.x, k.y) * Rectangle(p, p)
        sk = sq if sk is None else sk + sq
    grow = b.outer_wall - b.partition / 2.0
    sk = offset(sk, grow, kind=Kind.INTERSECTION)
    # round concave corners (closing), then convex corners (opening)
    rc, rv = b.concave_corner_radius, b.outer_corner_radius
    sk = offset(offset(sk, rc, kind=Kind.ARC), -rc, kind=Kind.ARC)
    sk = offset(offset(sk, -rv, kind=Kind.ARC), rv, kind=Kind.ARC)
    return sk


def _groove_cutters(layout: LayoutResult, mech: MechanicalProfile, depth: float):
    b = mech.body
    p = layout.pitch
    surf = b.outer_wall - b.partition / 2.0
    w = b.groove_width
    ext = 0.4                          # how far the cutter starts outside the surface
    wb = w * (depth + ext) / depth     # base width keeping the V angle
    H = b.height
    cells = layout.cells
    pos = {(k.row, k.col): (k.x, k.y) for k in layout.keys}
    cutters = []

    def notch(px, py, nx, ny):
        # (px,py) point on the outer surface, (nx,ny) outward normal
        tx, ty = -ny, nx
        pts = [
            (px + nx * ext + tx * wb / 2, py + ny * ext + ty * wb / 2),
            (px + nx * ext - tx * wb / 2, py + ny * ext - ty * wb / 2),
            (px - nx * depth, py - ny * depth),
        ]
        return Pos(0, 0, -1) * extrude(Polygon(*pts, align=None), H + 2, dir=(0, 0, 1))

    for (r, c) in cells:
        x, y = pos[(r, c)]
        # vertical boundary with the right neighbour
        if (r, c + 1) in cells:
            xb = x + p / 2
            if (r - 1, c) not in cells and (r - 1, c + 1) not in cells:
                cutters.append(notch(xb, y + p / 2 + surf, 0, 1))
            if (r + 1, c) not in cells and (r + 1, c + 1) not in cells:
                cutters.append(notch(xb, y - p / 2 - surf, 0, -1))
        # horizontal boundary with the neighbour below
        if (r + 1, c) in cells:
            yb = y - p / 2
            if (r, c - 1) not in cells and (r + 1, c - 1) not in cells:
                cutters.append(notch(x - p / 2 - surf, yb, -1, 0))
            if (r, c + 1) not in cells and (r + 1, c + 1) not in cells:
                cutters.append(notch(x + p / 2 + surf, yb, 1, 0))
    return cutters


_SIDE_ANGLE = {"top": 0.0, "left": 90.0, "bottom": 180.0, "right": -90.0}


def _keychain(outline, spec: KeychainSpec, mech: MechanicalProfile, warnings: list[str]):
    """Return (tab_solid, hole_cutter, hole_xy) built in a 'top' frame then rotated to the side."""
    bb = outline.bounding_box()
    angle = _SIDE_ANGLE[spec.side]
    # distance from origin to the body surface along the side normal
    surface = {"top": bb.max.Y, "bottom": -bb.min.Y, "right": bb.max.X, "left": -bb.min.X}[spec.side]
    half_span = {"top": bb.size.X, "bottom": bb.size.X, "left": bb.size.Y, "right": bb.size.Y}[spec.side] / 2
    r_hole = spec.hole_diameter / 2
    end_wall = 2.0
    root = 2.0
    lim = max(0.0, half_span - spec.width / 2 - 1.0)
    off = min(max(spec.offset, -lim), lim)
    if off != spec.offset:
        warnings.append("מיקום מחזיק המפתחות הוגבל לאורך הצלע. / keychain offset clamped.")
    if spec.side in ("bottom", "right"):
        off = -off  # keep +offset = +X / +Y after rotation
    hole_d = spec.length - r_hole - end_wall
    if hole_d - r_hole < 1.2:
        warnings.append("החור קרוב מדי לגוף — הלשונית הוארכה. / tab lengthened to keep 1.2 mm wall.")
        hole_d = r_hole + 1.2
    length = max(spec.length, hole_d + r_hole + end_wall)
    if spec.width < spec.hole_diameter + 2 * 1.6:
        warnings.append("לשונית צרה מדי לקוטר החור. / tab too narrow for hole.")

    tab2d = Pos(off, surface + (length - root) / 2) * RectangleRounded(
        spec.width, length + root, min(spec.corner_radius, spec.width / 2 - 0.05))
    rot = Rot(0, 0, angle)
    merged = outline + rot * tab2d
    rr = spec.root_radius
    merged = offset(offset(merged, rr, kind=Kind.ARC), -rr, kind=Kind.ARC)
    window = rot * (Pos(off, surface + (length - 3 * root) / 2) * Rectangle(
        spec.width + 2 * rr + 2.0, length + 3 * root))
    region = merged & window
    tab = extrude(region, spec.thickness)
    hx, hy = off, surface + hole_d
    a = math.radians(angle)
    wx, wy = hx * math.cos(a) - hy * math.sin(a), hx * math.sin(a) + hy * math.cos(a)
    hole = Pos(wx, wy, -1) * Cylinder(r_hole, spec.thickness + 2, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return tab, hole, (wx, wy)


def build_body(layout: LayoutResult, mech: MechanicalProfile, design: BodyDesign,
               keychain: KeychainSpec) -> BodyResult:
    b = mech.body
    sw = mech.switch
    warnings: list[str] = []
    outline = body_outline(layout, mech)
    solid = extrude(outline, b.height)
    zgroups = solid.edges().group_by(Axis.Z)
    try:
        solid = fillet(zgroups[0] + zgroups[-1], b.edge_fillet)
    except Exception:  # noqa: BLE001 - OCC fillet failure is reported, not hidden
        warnings.append("עיגול שולי הגוף נכשל — הגוף נוצר ללא עיגול. / body edge fillet failed.")

    if design.joint == "grooved" and len(layout.keys) > 1:
        depth = min(design.groove_depth, b.outer_wall - 0.5)
        for cutter in _groove_cutters(layout, mech, depth):
            solid = solid - cutter

    hole_xy = None
    hole_cutter = None
    if keychain.enabled:
        tab, hole_cutter, hole_xy = _keychain(outline, keychain, mech, warnings)
        solid = solid + tab

    # cavities per cell
    plate_bot = b.plate_bottom_z
    plate_top = plate_bot + sw.plate_thickness
    ch = (b.lower_pocket - b.plate_chamfer_to) / 2.0   # 45 degree transition
    cutters = []
    for k in layout.keys:
        at = Pos(k.x, k.y)
        cutters.append(at * extrude(_rounded_square(b.upper_recess, b.recess_corner_radius, plate_top),
                                    b.height - plate_top + 1.0))
        cutters.append(at * Pos(0, 0, plate_bot - 0.1) * Box(
            sw.plate_hole, sw.plate_hole, sw.plate_thickness + 0.2, align=(Align.CENTER, Align.CENTER, Align.MIN)))
        cutters.append(at * extrude(_rounded_square(b.lower_pocket, b.pocket_corner_radius, b.floor),
                                    b.lower_pocket_depth - ch))
        cutters.append(at * loft([
            _rounded_square(b.lower_pocket, b.pocket_corner_radius, plate_bot - ch),
            _rounded_square(b.plate_chamfer_to, b.pocket_corner_radius, plate_bot),
        ]))
    for c in cutters:
        solid = solid - c
    if hole_cutter is not None:
        solid = solid - hole_cutter

    solids = solid.solids()
    if len(solids) != 1:
        raise ValueError(f"Body produced {len(solids)} separate solids (expected 1)")
    bb = outline.bounding_box()
    return BodyResult(solids[0], (bb.min.X, bb.min.Y, bb.max.X, bb.max.Y), hole_xy, warnings)

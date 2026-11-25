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
    mesh: object = None        # textured mesh (None = use the B-rep)
    outline: object = None
    texture_exclude: list = field(default_factory=list)


def texture_body(body: "BodyResult", mech: MechanicalProfile, design: BodyDesign):
    """Textured mesh of an already built body (outer wall only). Returns (mesh, warnings)."""
    from .texture import MIN_WALL_LEFT, TextureParams, apply_texture

    b = mech.body
    warnings = []
    depth = min(design.texture_depth, b.outer_wall - MIN_WALL_LEFT)
    if depth < design.texture_depth:
        warnings.append(f"עומק הטקסטורה הוגבל ל-{depth:.2f} מ\"מ כדי לשמור על חוזק הדופן. / "
                        f"texture depth limited to {depth:.2f} mm.")
    z0, z1 = b.edge_fillet + 0.6, b.height - b.edge_fillet - 0.6
    mesh = apply_texture(body.solid, body.outline, TextureParams(design.texture, depth, design.texture_unit),
                         z0, z1, body.texture_exclude)
    return mesh, warnings


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
    root = 2.0
    MIN_RING, MIN_BODY, MIN_THICK = 2.0, 1.5, 4.0      # strength rules for every shape
    g = max(0.0, spec.gusset)
    width = spec.width
    off = -spec.offset if spec.side in ("bottom", "right") else spec.offset   # +offset = +X / +Y after rotation
    # the tab must sit on ONE straight stretch of the outer wall (e.g. WASD: not over the empty corner)
    a = math.radians(-angle)
    wire = outline.faces()[0].outer_wire()
    pts = [(q.X * math.cos(a) - q.Y * math.sin(a), q.X * math.sin(a) + q.Y * math.cos(a))
           for q in wire.positions([i / 400 for i in range(400)])]
    edge = [x for x, y in pts if y > surface - 0.02]
    margin = width / 2 + spec.root_radius
    lo_t, hi_t = (min(edge) + margin, max(edge) - margin) if edge else (-half_span, half_span)
    if lo_t > hi_t:
        lo_t = hi_t = (min(edge) + max(edge)) / 2 if edge else 0.0
        warnings.append("הצלע קצרה מרוחב המחזיק — מומלץ צד אחר או מחזיק צר יותר. / side too short for the tab.")
    clamped = min(max(off, lo_t), hi_t)
    if abs(clamped - off) > 1e-6:
        warnings.append("מחזיק המפתחות הוזז כדי לשבת על דופן רציפה. / keychain moved onto a continuous wall.")
    off = clamped
    if width < spec.hole_diameter + 2 * MIN_RING:
        width = spec.hole_diameter + 2 * MIN_RING
        warnings.append(f"הלשונית הורחבה ל-{width:.1f} מ\"מ כדי להשאיר 2 מ\"מ סביב החור. / tab widened for a 2 mm ring.")
    if spec.thickness < MIN_THICK:
        warnings.append(f"עובי המחזיק הוגדל ל-{MIN_THICK} מ\"מ לחוזק. / tab thickness raised to {MIN_THICK} mm.")
    thickness = max(spec.thickness, MIN_THICK)
    # the hole must start beyond the gusset so a key ring passes freely
    min_hole_d = r_hole + max(MIN_BODY, g + 0.8)
    if spec.shape == "round":
        corner = width / 2 - 0.05                      # full semicircle end, hole concentric with it
        hole_d = max(spec.length - width / 2, min_hole_d)
        length = hole_d + width / 2
    else:
        corner = min(spec.corner_radius if spec.shape == "rounded" else 1.0, width / 2 - 0.05)
        hole_d = max(spec.length - r_hole - MIN_RING, min_hole_d)
        length = hole_d + r_hole + MIN_RING
    if length > spec.length + 1e-6:
        warnings.append(f"הלשונית הוארכה ל-{length:.1f} מ\"מ לשמירת חוזק. / tab lengthened to {length:.1f} mm.")
    tab2d = Pos(off, surface + (length - root) / 2) * RectangleRounded(width, length + root, corner)
    rot = Rot(0, 0, angle)
    merged = outline + rot * tab2d
    rr = spec.root_radius
    merged = offset(offset(merged, rr, kind=Kind.ARC), -rr, kind=Kind.ARC)
    window = rot * (Pos(off, surface + (length - 3 * root) / 2) * Rectangle(
        width + 2 * rr + 2.0, length + 3 * root))
    region = merged & window
    tab = extrude(region, thickness)
    if g > 0:
        # 45 degree gusset across the whole root: no sharp inside corner where the tab meets the wall
        prof = Plane.YZ * Polygon((surface - 1.0, thickness - 0.01), (surface + g, thickness - 0.01),
                                  (surface - 1.0, thickness + g + 1.0), align=None)
        wedge = Pos(off, 0, 0) * extrude(prof, width / 2 + rr * 0.5, both=True)
        tab = tab + rot * wedge
    hx, hy = off, surface + hole_d
    a = math.radians(angle)
    wx, wy = hx * math.cos(a) - hy * math.sin(a), hx * math.sin(a) + hy * math.cos(a)
    hole = Pos(wx, wy, -1) * Cylinder(r_hole, thickness + 2, align=(Align.CENTER, Align.CENTER, Align.MIN))
    rx, ry = off * math.cos(a) - surface * math.sin(a), off * math.sin(a) + surface * math.cos(a)
    # texture exclusion: around the tab root, up to the gusset top (+1.5 mm) - no notch over the joint
    return tab, hole, (wx, wy), (rx, ry, width / 2 + spec.root_radius + 1.5, thickness + g + 2.0)


def _clip_notches(b, sw, plate_bot: float) -> list:
    """Small recesses under the plate where the MX clips spring out. Ceiling = plate underside
    (short bridge), floor = 45 degree slope, so nothing is printed in the air."""
    half = sw.plate_hole / 2
    y0, y1 = half - 0.6, half + b.clip_notch_depth           # start inside the pocket for a clean cut
    top, mid = plate_bot, plate_bot - b.clip_notch_height
    low = mid - (y1 - y0)                                     # 45 degree floor down into the pocket
    prof = Plane.YZ * Polygon((y0, top), (y1, top), (y1, mid), (y0, low), align=None)
    notch = extrude(prof, b.clip_notch_width / 2, both=True)
    sides = {"ns": (0, 180), "ew": (90, 270), "all": (0, 90, 180, 270)}.get(b.clip_notch_sides, (0, 180))
    return [Rot(0, 0, a) * notch for a in sides]


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
    exclude = []
    if keychain.enabled:
        tab, hole_cutter, hole_xy, root = _keychain(outline, keychain, mech, warnings)
        exclude.append(root)
        solid = solid + tab

    # cavities per cell
    plate_bot = b.plate_bottom_z
    plate_top = plate_bot + sw.plate_thickness
    cutters = []
    for k in layout.keys:
        at = Pos(k.x, k.y)
        cutters.append(at * extrude(_rounded_square(b.upper_recess, b.recess_corner_radius, plate_top),
                                    b.height - plate_top + 1.0))
        cutters.append(at * Pos(0, 0, plate_bot - 0.1) * Box(
            sw.plate_hole, sw.plate_hole, sw.plate_thickness + 0.2, align=(Align.CENTER, Align.CENTER, Align.MIN)))
        # pocket under the plate: straight walls from the floor up to the plate (plate prints on material)
        cutters.append(at * extrude(_rounded_square(b.lower_pocket, b.pocket_corner_radius, b.floor),
                                    b.lower_pocket_depth))
        for notch in _clip_notches(b, sw, plate_bot):
            cutters.append(at * notch)
    for c in cutters:
        solid = solid - c
    if hole_cutter is not None:
        solid = solid - hole_cutter

    solids = solid.solids()
    if len(solids) != 1:
        raise ValueError(f"Body produced {len(solids)} separate solids (expected 1)")
    bb = outline.bounding_box()
    res = BodyResult(solids[0], (bb.min.X, bb.min.Y, bb.max.X, bb.max.Y), hole_xy, warnings, outline=outline)
    res.texture_exclude = exclude
    if design.texture != "smooth":
        res.mesh, w = texture_body(res, mech, design)
        warnings += w
    return res

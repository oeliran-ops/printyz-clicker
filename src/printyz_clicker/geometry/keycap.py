"""Keycap engine. Local frame: skirt bottom at z=0, centred on XY origin, top face at z=height."""

from __future__ import annotations

from build123d import (
    Align, Axis, Box, Cylinder, Kind, Plane, Pos, RectangleRounded, Solid, extrude, fillet, loft,
)

from ..config.mechanical import KeycapStyle


def _rounded_square(width: float, radius: float, z: float = 0.0):
    r = min(radius, width / 2.0 - 0.05)
    return Plane.XY.offset(z) * RectangleRounded(width, width, r)


def keycap_body(style: KeycapStyle) -> Solid:
    h = style.height
    ratio = style.top_width / style.bottom_width
    outer = loft([
        _rounded_square(style.bottom_width, style.corner_radius, 0.0),
        _rounded_square(style.top_width, style.corner_radius * ratio, h),
    ])
    if style.top_edge_fillet > 0:
        outer = fillet(outer.edges().group_by(Axis.Z)[-1], style.top_edge_fillet)

    # inner cavity: follows the outer taper with constant horizontal wall
    z_in_top = h - style.top_thickness
    z0 = -0.5
    inner = loft([
        _rounded_square(style.width_at(z0) - 2 * style.wall, max(0.3, style.corner_radius - style.wall), z0),
        _rounded_square(style.width_at(z_in_top) - 2 * style.wall,
                        max(0.3, style.corner_radius * ratio - style.wall), z_in_top),
    ])
    cap = outer - inner

    # MX stem with cross socket
    stem_h = z_in_top - style.stem_offset + 0.05  # small overlap into the top plate
    stem = Pos(0, 0, style.stem_offset) * Cylinder(
        style.stem_diameter / 2, stem_h, align=(Align.CENTER, Align.CENTER, Align.MIN))
    sock_h = style.socket_depth + 0.1
    cross = (
        Pos(0, 0, style.stem_offset - 0.1) * Box(style.cross_length, style.cross_width, sock_h,
                                                 align=(Align.CENTER, Align.CENTER, Align.MIN))
        + Pos(0, 0, style.stem_offset - 0.1) * Box(style.cross_width, style.cross_length, sock_h,
                                                   align=(Align.CENTER, Align.CENTER, Align.MIN))
    )
    cap = cap + (stem - cross)
    return _single_solid(cap)


def _single_solid(shape) -> Solid:
    solids = shape.solids()
    if len(solids) != 1:
        raise ValueError(f"Keycap produced {len(solids)} solids (expected 1)")
    return solids[0]


def apply_legend(cap: Solid, style: KeycapStyle, legend_sketch, mode: str, depth: float, raise_h: float):
    """Return (cap_solid, legend_solid_or_None) in the keycap local frame.

    flush    -> pocket cut into cap + inlay solid whose top is exactly the cap top (z=h)
    engraved -> pocket only
    raised   -> legend solid standing on the top face
    """
    h = style.height
    if legend_sketch is None:
        return cap, None
    if mode in ("flush", "engraved"):
        if depth >= style.top_thickness - 0.4:
            raise ValueError("Legend depth leaves less than 0.4 mm of keycap top")
        inlay = extrude(Plane.XY.offset(h - depth) * legend_sketch, depth)
        # cutter extends above the top so the pocket opens cleanly through the face
        cutter = extrude(Plane.XY.offset(h - depth) * legend_sketch, depth + 0.5)
        new_cap = _single_solid(cap - cutter)
        return new_cap, (inlay if mode == "flush" else None)
    if mode == "raised":
        legend = extrude(Plane.XY.offset(h) * legend_sketch, raise_h)
        return cap, legend
    raise ValueError(f"Unknown legend mode {mode!r}")

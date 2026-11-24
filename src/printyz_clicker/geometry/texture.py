"""Texture engine: outside-wall textures applied as exact mesh booleans (manifold3d).

The body stays a B-rep (mechanics, STEP). Textures are cut into its tessellated
mesh, which is what the viewer, STL and 3MF use, so preview == print file.
Textures never touch the inside (switch pockets, recesses) - cutters only reach
`depth` mm into the outer wall inside a vertical band clear of the edge fillets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from manifold3d import CrossSection, JoinType, Manifold, OpType
from manifold3d import Mesh as MMesh

from ..export.mesh import Mesh, tessellate

TEXTURES = ("smooth", "diamond", "ribs", "fluted", "dots", "chevron")
MIN_WALL_LEFT = 0.9   # mm of outer wall that must remain under the deepest texture point


@dataclass
class TextureParams:
    kind: str = "smooth"
    depth: float = 0.5     # mm into the wall
    unit: float = 2.4      # pattern pitch, mm


def _perimeter(outline, step: float):
    """Evenly spaced points + outward normals along the outer wire (closed loop)."""
    wire = outline.faces()[0].outer_wire()
    length = wire.length
    n = max(8, int(round(length / step)))
    ts = [i / n for i in range(n)]
    pts = np.array([[p.X, p.Y] for p in (wire.position_at(t) for t in ts)])
    tan = np.array([[v.X, v.Y] for v in (wire.tangent_at(t) for t in ts)])
    tan /= np.linalg.norm(tan, axis=1, keepdims=True)
    area = 0.5 * np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - np.roll(pts[:, 0], -1) * pts[:, 1])
    normals = np.stack([tan[:, 1], -tan[:, 0]], 1) if area > 0 else np.stack([-tan[:, 1], tan[:, 0]], 1)
    return pts, normals, length / n


def _to_manifold(mesh: Mesh) -> Manifold:
    return Manifold(MMesh(vert_properties=mesh.vertices.astype(np.float32),
                          tri_verts=mesh.faces.astype(np.uint32)))


def _from_manifold(m: Manifold) -> Mesh:
    mm = m.to_mesh()
    return Mesh(np.asarray(mm.vert_properties, dtype=np.float64)[:, :3], np.asarray(mm.tri_verts, dtype=np.int64))


def _sphere(c, r) -> Manifold:
    return Manifold.sphere(r, 12).translate(tuple(float(x) for x in c))


def build_cutters(outline, params: TextureParams, z0: float, z1: float, exclude: list[tuple[float, float, float]]):
    k, d, u = params.kind, params.depth, params.unit
    if k == "smooth" or d <= 0:
        return None

    def keep(p, z: float | None = None) -> bool:
        """False only inside a keychain-tab zone (in plan AND below the tab top)."""
        for ex, ey, er, ez in exclude:
            if math.hypot(p[0] - ex, p[1] - ey) <= er and (z is None or z <= ez):
                return False
        return True

    cutters: list[Manifold] = []
    if k == "ribs":
        # rounded (half-round) grooves built from stacked ring slices: they read from every angle
        pts, _, _ = _perimeter(outline, 0.4)
        cs = CrossSection([pts.tolist()])
        if cs.area() <= 0:                      # clockwise loop: the default fill rule drops it
            cs = CrossSection([pts[::-1].tolist()])
        outside = cs.offset(0.3, JoinType.Round)   # start outside: coincident faces could leave a skin
        groove = u * 0.5
        slices = 7
        z = z0
        while z + groove <= z1 + 1e-6:
            for i in range(slices):
                t = (i + 0.5) / slices * 2 - 1              # -1 .. 1 across the groove height
                dd = d * math.sqrt(max(0.0, 1 - t * t))
                if dd < 0.05:
                    continue
                ring = outside - cs.offset(-dd, JoinType.Round)
                cutters.append(ring.extrude(groove / slices + 0.002).translate((0, 0, z + i * groove / slices)))
            z += u
        rings = Manifold.batch_boolean(cutters, OpType.Add)
        for ex, ey, er, ez in exclude:            # keep the tab root solid, texture continues above it
            rings = rings - Manifold.cylinder(ez + 1, er, er, 48).translate((ex, ey, -1))
        return rings

    if k == "fluted":
        pts, nrm, _ = _perimeter(outline, u)
        r = u * 0.38
        for p, n in zip(pts, nrm):
            c = p + n * (r - d)
            start = z0
            for ex, ey, er, ez in exclude:          # flute starts above the keychain tab
                if math.hypot(p[0] - ex, p[1] - ey) <= er:
                    start = max(start, ez)
            if z1 - start > 1.0:
                cutters.append(Manifold.cylinder(z1 - start, r, r, 16).translate((float(c[0]), float(c[1]), start)))
    elif k == "dots":
        pts, nrm, _ = _perimeter(outline, u / 2)
        r = u * 0.34
        row, z = 0, z0 + r
        while z <= z1 - r + 1e-6:
            for i in range(row % 2, len(pts), 2):
                p, n = pts[i], nrm[i]
                if keep(p, z - r):
                    c = p + n * (r - d)
                    cutters.append(_sphere((c[0], c[1], z), r))
            z += u * 0.866          # hexagonal row spacing
            row += 1
    elif k == "diamond":
        pts, nrm, ds = _perimeter(outline, u / 2)
        a = u / 2 * 0.97            # half-diagonal along the wall and along z
        row, z = 0, z0 + a
        while z <= z1 - a + 1e-6:
            for i in range(row % 2, len(pts), 2):
                p, n = pts[i], nrm[i]
                if not keep(p, z - a):
                    continue
                t = np.array([-n[1], n[0]])
                out = p + n * 0.3
                corners = [
                    (*(out + t * a), z), (*(out - t * a), z),
                    (*out, z + a), (*out, z - a), (*(p - n * d), z),
                ]
                cutters.append(Manifold.hull_points([tuple(float(x) for x in c) for c in corners]))
            z += a
            row += 1
    elif k == "chevron":
        pts, nrm, _ = _perimeter(outline, u / 2)
        r = u * 0.22
        amp = u * 0.35
        z = z0 + amp + r
        while z <= z1 - amp - r + 1e-6:
            prev = None
            for i in range(len(pts) + 1):
                j = i % len(pts)
                p, n = pts[j], nrm[j]
                zz = z + (amp if i % 2 else -amp)
                c = (*(p + n * (r - d)), zz)
                if prev is not None and keep(p, zz - amp - r) and keep(prev[1], zz - amp - r):
                    cutters.append(Manifold.batch_hull([_sphere(prev[0], r), _sphere(c, r)]))
                prev = (c, p)
            z += u * 1.1
    else:
        raise ValueError(f"Unknown texture {k!r}")
    if not cutters:
        return None
    return Manifold.batch_boolean(cutters, OpType.Add)


def apply_texture(body_solid, outline, params: TextureParams, z0: float, z1: float,
                  exclude: list[tuple[float, float, float]] | None = None) -> Mesh | None:
    """Return the textured body mesh, or None for 'smooth'."""
    cut = build_cutters(outline, params, z0, z1, exclude or [])
    if cut is None:
        return None
    base = _to_manifold(tessellate(body_solid))
    if base.status().name != "NoError":
        raise ValueError(f"Body mesh is not manifold ({base.status().name}); cannot apply texture")
    out = base - cut
    return _from_manifold(out)

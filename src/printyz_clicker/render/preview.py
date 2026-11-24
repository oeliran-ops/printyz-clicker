"""Static preview renders (PNG) of the real generated geometry.

Used for reports, thumbnails and automated visual checks. The interactive Qt
viewer (phase 3) will consume the same tessellated meshes.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import to_rgb  # noqa: E402


from ..geometry.builder import BuildResult, part_mesh  # noqa: E402

VIEWS = {
    "iso": (32, -60),
    "top": (90, -90),
    "side": (0, -90),
    "bottom": (-60, -60),
}


def _gather(res: BuildResult, exploded: bool, show_switches: bool):
    polys, cols = [], []
    for p in res.parts:
        if p.role in ("switch", "stem") and not show_switches:
            continue
        m = part_mesh(p, tol=0.05, ang=0.3)
        tri = m.triangles
        if exploded:
            tri = tri + np.array([0, 0, {"cap": 22.0, "legend": 22.0, "switch": 8.0, "stem": 8.0}.get(p.role, 0.0)])
        polys.append(tri)
        cols.append(np.repeat([to_rgb(p.color)], len(m.faces), axis=0))
    return np.concatenate(polys), np.concatenate(cols)


def _camera(elev: float, azim: float):
    e, a = np.radians(elev), np.radians(azim)
    fwd = -np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])  # view direction
    up0 = np.array([0.0, 0.0, 1.0]) if abs(elev) < 89 else np.array([0.0, 1.0, 0.0])
    right = np.cross(fwd, up0)
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    return right, up, fwd


def rasterize(tri: np.ndarray, colors: np.ndarray, elev: float, azim: float,
              width: int = 1200, height: int = 900, bg=(0.957, 0.961, 0.969), ss: int = 2) -> np.ndarray:
    """Orthographic z-buffer renderer (no painter-sorting artefacts). Returns HxWx3 floats."""
    right, up, fwd = _camera(elev, azim)
    pts = tri.reshape(-1, 3)
    sx, sy, sz = pts @ right, pts @ up, pts @ fwd
    W, H = width * ss, height * ss
    lo = np.array([sx.min(), sy.min()])
    hi = np.array([sx.max(), sy.max()])
    scale = 0.86 * min(W / max(hi[0] - lo[0], 1e-6), H / max(hi[1] - lo[1], 1e-6))
    cx, cy = (lo + hi) / 2
    px = (sx - cx) * scale + W / 2
    py = H / 2 - (sy - cy) * scale
    P = np.stack([px, py, sz], 1).reshape(-1, 3, 3)

    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    key = -fwd + 0.6 * up + 0.3 * right
    key /= np.linalg.norm(key)
    fill = -fwd - 0.4 * right
    fill /= np.linalg.norm(fill)
    ndl = np.abs(n @ key)          # two-sided: robust to any winding
    shade = 0.30 + 0.55 * ndl + 0.15 * np.abs(n @ fill)
    fc = np.clip(colors * shade[:, None], 0, 1)

    img = np.empty((H, W, 3))
    img[:] = bg
    zbuf = np.full((H, W), np.inf)
    for t in range(len(P)):
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = P[t]
        xmin, xmax = int(max(min(x0, x1, x2), 0)), int(min(max(x0, x1, x2) + 1, W))
        ymin, ymax = int(max(min(y0, y1, y2), 0)), int(min(max(y0, y1, y2) + 1, H))
        if xmin >= xmax or ymin >= ymax:
            continue
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue
        gx, gy = np.meshgrid(np.arange(xmin, xmax) + 0.5, np.arange(ymin, ymax) + 0.5)
        w0 = ((x1 - gx) * (y2 - gy) - (x2 - gx) * (y1 - gy)) / area
        w1 = ((x2 - gx) * (y0 - gy) - (x0 - gx) * (y2 - gy)) / area
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        z = w0 * z0 + w1 * z1 + w2 * z2
        sub = zbuf[ymin:ymax, xmin:xmax]
        m = inside & (z < sub)
        sub[m] = z[m]
        img[ymin:ymax, xmin:xmax][m] = fc[t]
    # silhouette darkening for crisp edges
    depth = np.where(np.isinf(zbuf), np.nan, zbuf)
    dzx = np.abs(np.diff(depth, axis=1, prepend=depth[:, :1]))
    dzy = np.abs(np.diff(depth, axis=0, prepend=depth[:1, :]))
    edge = np.nan_to_num(np.maximum(dzx, dzy), nan=10.0) > 0.8  # mm depth jump
    img[edge & np.isfinite(zbuf)] *= 0.55
    return img.reshape(height, ss, width, ss, 3).mean(axis=(1, 3))


def render(res: BuildResult, path: Path, view: str = "iso", exploded: bool = False,
           show_switches: bool | None = None, size: tuple[int, int] = (1200, 900)) -> Path:
    if show_switches is None:
        show_switches = exploded
    tri, col = _gather(res, exploded, show_switches)
    elev, azim = VIEWS[view]
    img = rasterize(tri, col, elev, azim, *size)
    plt.imsave(path, np.clip(img, 0, 1))
    return Path(path)


def render_set(res: BuildResult, folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    return [
        render(res, folder / "preview_iso.png", "iso"),
        render(res, folder / "preview_top.png", "top"),
        render(res, folder / "preview_side.png", "side"),
        render(res, folder / "preview_exploded.png", "iso", exploded=True),
    ]

"""Interactive 3D viewer (VTK via pyvistaqt) showing the REAL tessellated BuildResult."""

from __future__ import annotations

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtWidgets import QWidget

from ..geometry.builder import BuildResult, part_mesh

EXPLODE_DZ = {"cap": 24.0, "legend": 24.0, "switch": 9.0, "stem": 9.0}


def to_polydata(mesh) -> pv.PolyData:
    faces = np.hstack([np.full((len(mesh.faces), 1), 3), mesh.faces]).astype(np.int64).ravel()
    return pv.PolyData(mesh.vertices, faces)


class Viewer3D(QtInteractor):
    def __init__(self, parent: QWidget | None = None, on_pick=None):
        super().__init__(parent)
        self.on_pick = on_pick
        self._parts: dict[str, tuple[str, str | None]] = {}   # name -> (role, key_id)
        self.set_background("#FBFBFC", top="#E9EDF3")
        self.enable_anti_aliasing("ssaa")
        self.enable_lightkit()
        self._meshes: dict[str, tuple[pv.PolyData, str, str]] = {}   # name -> (mesh, color, role)
        self.exploded = False
        self.cutaway = False
        self.show_switches = False
        self.hidden_roles: set[str] = set()
        self.body_opacity = 1.0
        self._view = "iso"
        self._has_camera = False

    # ---- data ---------------------------------------------------------------
    def show_result(self, res: BuildResult) -> None:
        cache = getattr(self, "_poly_cache", {})
        new_cache, meshes = {}, {}
        for p in res.parts:
            src = p.mesh if p.mesh is not None else p.solid
            hit = cache.get(id(src))
            poly = hit[1] if hit is not None and hit[0] is src else to_polydata(part_mesh(p, tol=0.03, ang=0.25))
            new_cache[id(src)] = (src, poly)
            meshes[p.name] = (poly, p.color, p.role)
        self._poly_cache = new_cache
        self._meshes = meshes
        self._parts = {p.name: (p.role, p.key_id) for p in res.parts}
        self.redraw()
        if self.on_pick and not getattr(self, "_picking", False):
            try:
                self.enable_mesh_picking(self._picked, use_actor=True, show=False, show_message=False,
                                         left_clicking=True)
                self._picking = True
            except Exception:  # noqa: BLE001 - picking is a convenience; the colour page still works
                self._picking = False

    def _picked(self, actor) -> None:
        for name, a in self.actors.items():
            if a is actor and name in self._parts:
                role, key_id = self._parts[name]
                self.on_pick(role, key_id)
                return

    def clear_model(self) -> None:
        self._meshes = {}
        self.clear()
        self.render()

    def redraw(self) -> None:
        self.clear_actors()
        for name, (mesh, color, role) in self._meshes.items():
            if role in self.hidden_roles:
                continue
            if role in ("switch", "stem") and not (self.show_switches or self.exploded):
                continue
            m = mesh
            if self.exploded:
                m = m.translate((0, 0, EXPLODE_DZ.get(role, 0.0)), inplace=False)
            if self.cutaway:
                m = m.clip(normal=(0, -1, 0), origin=(0, 0, 0), invert=False)
                if m.n_points == 0:
                    continue
            self.add_mesh(
                m, color=color, smooth_shading=True, split_sharp_edges=True, feature_angle=35,
                specular=0.25, specular_power=20, ambient=0.15, diffuse=0.85,
                opacity=self.body_opacity if role == "body" else 1.0, name=name,
            )
        if not self._has_camera and self._meshes:
            self.set_view(self._view)
            self._has_camera = True
        self.render()

    # ---- camera ---------------------------------------------------------------
    def set_view(self, view: str) -> None:
        self._view = view
        if view == "top":
            self.view_xy()
        elif view == "side":
            self.view_xz()
        elif view == "bottom":
            self.view_xy(negative=True)
        else:
            # front-right, from above: legends read upright like in a product photo
            b = self.bounds
            c = ((b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2)
            self.camera_position = [(c[0] + 0.45, c[1] - 1.0, c[2] + 0.95), c, (0, 0, 1)]
        self.reset_camera()
        self.camera.zoom(1.05 if view == "iso" else 1.25)
        self.render()

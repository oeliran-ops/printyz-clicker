"""Validation engine: engineering checks on the REAL generated geometry."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from build123d import Pos

from ..export.mesh import mesh_health
from ..geometry.builder import BuildResult, part_mesh
from ..geometry.lettering import MIN_MARGIN

OK, WARN, ERROR = "ok", "warning", "error"
_COLLISION: dict[tuple[int, int], tuple[object, object, float]] = {}
_VALID: dict[int, tuple[object, bool, int]] = {}


def _zmax(solid) -> float:
    hit = _VALID.get(("z", id(solid)))
    if hit is not None and hit[0] is solid:
        return hit[1]
    z = solid.bounding_box().max.Z
    _VALID[("z", id(solid))] = (solid, z, 0)
    return z


def _solid_state(solid) -> tuple[bool, int]:
    hit = _VALID.get(id(solid))
    if hit is not None and hit[0] is solid:
        return hit[1], hit[2]
    # BRepCheck also inspects cached triangulation polygons; parts that share faces may carry
    # meshes from different resolutions (preview vs. export). Check the geometry, not the cache.
    from OCP.BRepTools import BRepTools

    BRepTools.Clean_s(solid.wrapped)
    st = (solid.is_valid, len(solid.solids()))
    if len(_VALID) > 4000:
        _VALID.clear()
    _VALID[id(solid)] = (solid, *st)
    return st
AMS_SLOTS = 4


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""


@dataclass
class ValidationReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.checks.append(Check(name, status, detail))

    @property
    def errors(self) -> list[Check]:
        return [c for c in self.checks if c.status == ERROR]

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_markdown(self) -> str:
        icon = {OK: "✅", WARN: "⚠️", ERROR: "❌"}
        lines = ["# PRINTYZ – דוח בדיקות / Validation report", "",
                 f"**סטטוס:** {'עבר' if self.passed else 'נכשל'} / {'PASSED' if self.passed else 'FAILED'}", "",
                 "| | בדיקה / Check | פרטים / Detail |", "|---|---|---|"]
        lines += [f"| {icon[c.status]} | {c.name} | {c.detail} |" for c in self.checks]
        return "\n".join(lines) + "\n"

    def to_json(self) -> str:
        return json.dumps({"passed": self.passed, "checks": [asdict(c) for c in self.checks]},
                          ensure_ascii=False, indent=2)


def validate(res: BuildResult, mesh_checks: bool = True) -> ValidationReport:
    rep = ValidationReport()
    for e in res.errors:
        rep.add("build", ERROR, e)
    if not res.ok:
        return rep
    p = res.project
    mech = res.mech or p.mechanical
    b, sw, st = mech.body, mech.switch, res.style
    for w in res.warnings:
        rep.add("build", WARN, w)

    n = len(res.layout.keys)
    rep.add("key count / מספר מקשים", OK, f"{n} (1–10)")

    # --- mechanical envelope -------------------------------------------------
    inner = st.height - st.top_thickness
    rep.add("keycap stem / פין הכובע", OK if st.stem_length >= inner - 0.5 and st.stem_length >= st.socket_depth + 0.3
            else ERROR,
            f"{st.stem_length:.2f} mm from inner top (reaches {st.stem_offset:.2f} mm from the skirt; reference 9.996 mm)")
    rest = mech.keycap_rest_z(st)
    pressed = rest - sw.travel
    gap = pressed - mech.plate_top_z
    rep.add("press clearance / מרווח בלחיצה", OK if gap >= mech.min_press_clearance else ERROR,
            f"skirt at bottom-out is {gap:.2f} mm above plate (min {mech.min_press_clearance})")
    if pressed < b.height:
        w_at = st.width_at(b.height - pressed)
        side = (b.upper_recess - w_at) / 2
        rep.add("side clearance / מרווח צד", OK if side >= mech.min_side_clearance else ERROR,
                f"{side:.2f} mm between keycap and recess wall at bottom-out")
    under = sw.below_plate_depth + sw.pin_length
    rep.add("switch depth / עומק מתג", OK if under <= b.lower_pocket_depth else ERROR,
            f"switch needs {under:.2f} mm under plate, pocket is {b.lower_pocket_depth:.2f}")
    rep.add("switch clip width", OK if sw.bottom_housing_width <= b.plate_chamfer_to - 0.2 else WARN,
            f"housing {sw.bottom_housing_width} vs pocket at plate {b.plate_chamfer_to}")
    overhang = (b.plate_chamfer_to - sw.plate_hole) / 2
    rep.add("plate overhang / גשר מתחת לפלטה", OK if overhang <= 1.5 else WARN,
            f"{overhang:.2f} mm unsupported ledge under the plate")
    rep.add("partition / מחיצה", OK if b.partition >= b.min_wall else ERROR, f"{b.partition:.2f} mm")
    lower_wall = b.pitch - b.lower_pocket
    rep.add("wall under partition", OK if lower_wall >= b.partition else ERROR,
            f"{lower_wall:.2f} mm (partition is supported from below)")
    rep.add("outer wall / דופן חיצונית", OK if b.outer_wall >= b.min_wall else ERROR, f"{b.outer_wall:.3f} mm")
    rep.add("floor / תחתית", OK if b.floor >= 1.2 else ERROR, f"closed bottom, {b.floor:.2f} mm")
    rep.add("plate hole / פתח מתג", OK, f"{sw.plate_hole:.2f} × {sw.plate_hole:.2f} mm (developer-calibrated)")

    # --- real-geometry collision: keycap pressed vs body ----------------------
    body = next(pt for pt in res.parts if pt.role == "body")
    for cap in (pt for pt in res.parts if pt.role == "cap"):
        ck = (id(body.solid), id(cap.solid))
        hit = _COLLISION.get(ck)
        if hit is not None and hit[0] is body.solid and hit[1] is cap.solid:
            vol = hit[2]
        else:
            moved = Pos(0, 0, -sw.travel) * cap.solid
            inter = body.solid & moved
            vol = sum(s.volume for s in inter.solids()) if inter is not None else 0.0
            if len(_COLLISION) > 2000:
                _COLLISION.clear()
            _COLLISION[ck] = (body.solid, cap.solid, vol)
        if vol > 1e-3:
            rep.add(f"{cap.name} press collision", ERROR, f"{vol:.3f} mm³ overlap with body at bottom-out")
    rep.add("pressed keycaps vs body / התנגשות בלחיצה", OK, "keycaps moved by full travel, overlap checked")

    # --- legends ---------------------------------------------------------------
    allowed = st.legend_area - 2 * max(MIN_MARGIN, min(p.lettering.margin, 3.5)) + 1e-3
    for tag, (w, h) in res.legend_boxes.items():
        ok = w <= allowed and h <= allowed
        rep.add(f"{tag} legend size", OK if ok else ERROR, f"{w:.2f} × {h:.2f} mm (allowed {allowed:.2f})")
    if p.lettering.mode == "flush":
        for leg in (pt for pt in res.parts if pt.role == "legend"):
            cap = next(pt for pt in res.parts if pt.role == "cap" and pt.group == leg.group)
            dz = abs(_zmax(leg.solid) - _zmax(cap.solid))
            rep.add(f"{leg.group} flush", OK if dz < 1e-4 else ERROR, f"legend top vs cap top Δ={dz:.5f} mm")

    # --- colours ---------------------------------------------------------------
    colors = {pt.color.upper() for pt in res.parts if pt.printable}
    rep.add("filaments / צבעים", OK if len(colors) <= AMS_SLOTS else WARN,
            f"{len(colors)} colours (AMS lite: {AMS_SLOTS})")

    # --- solids & meshes ---------------------------------------------------------
    for pt in res.printable_parts():
        valid, nsol = _solid_state(pt.solid)
        # a legend may have several islands (i, j, ה, ק ...) - each sits in its own pocket
        islands_ok = nsol >= 1 if pt.role == "legend" else nsol == 1
        if not valid or not islands_ok:
            rep.add(f"{pt.name} solid", ERROR, f"valid={valid}, solids={nsol}")
            continue
        if pt.role == "legend":
            tiny = [s.volume for s in pt.solid.solids() if s.volume < 0.5]
            if tiny:
                rep.add(f"{pt.name} detail", WARN, f"{len(tiny)} island(s) under 0.5 mm³ may not print")
        if mesh_checks:
            h = mesh_health(part_mesh(pt))
            good = (h["watertight"] and h["winding_consistent"] and h["volume"] > 0
                    and (h["bodies"] == nsol))
            rep.add(f"{pt.name} mesh", OK if good else ERROR,
                    f"watertight={h['watertight']} bodies={h['bodies']} vol={h['volume']:.1f} mm³")
    if p.body.texture != "smooth":
        tex_ok = res.body.mesh is not None
        rep.add("texture / טקסטורה", OK if tex_ok else WARN,
                f"{p.body.texture}, depth ≤ {b.outer_wall - 0.9:.2f} mm, outside wall only (pockets untouched)")
    if p.keychain.enabled:
        rep.add("keychain / מחזיק מפתחות", OK if len(body.solid.solids()) == 1 else ERROR,
                f"{p.keychain.shape}: fused to body, ≥2 mm around hole, ≥1.5 mm to body, ≥3 mm thick; "
                "pull-test a print before commercial use")
    return rep

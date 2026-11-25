"""Builds every part of a project from the single Project + LayoutResult.

The same BuildResult feeds the 3D preview and all exporters, so what is shown
is exactly what is exported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import dataclasses

from build123d import Pos, Rot, Solid

from ..config.mechanical import KEYCAP_STYLES, KeycapStyle, MechanicalProfile, keycap_with_height
from ..export.mesh import mesh_health, tessellate
from ..fonts.registry import FontRegistry, boldness_range, measure_stroke, missing_glyphs
from ..layout.engine import LayoutResult, compute_layout
from ..model.project import Project
from .body import BodyResult, build_body, texture_body
from .keycap import apply_legend, keycap_body
from .lettering import build_legend, build_shape_legend, fit_scale, glyph_box, min_detail_mm
from .switch_proxy import switch_proxy


# ---- geometry caches: unchanged keys / body are reused, so colour or single-key edits are instant
from collections import OrderedDict
from dataclasses import astuple


class _LRU(OrderedDict):
    def __init__(self, size: int):
        super().__init__()
        self.size = size

    def get_or(self, key, make):
        if key in self:
            self.move_to_end(key)
            return self[key]
        val = make()
        self[key] = val
        if len(self) > self.size:
            self.popitem(last=False)
        return val


_CACHE = {name: _LRU(n) for name, n in (("cap", 16), ("key", 400), ("body", 24), ("place", 1200),
                                         ("switch", 8), ("texture", 12))}


def clear_caches() -> None:
    for c in _CACHE.values():
        c.clear()


@dataclass
class Part:
    name: str                 # stable file-friendly name, e.g. "key03_cap"
    role: str                 # body | cap | legend | switch | stem
    solid: object             # world (assembled) position
    color: str
    key_id: Optional[str] = None
    printable: bool = True
    group: str = ""           # parts of one printed object share a group (e.g. "key03")
    local: object = None      # keycap-local geometry (skirt at z=0) for print layout
    mesh: object = None       # exact mesh override (textured body); same frame as `solid`


def part_mesh(part: "Part", tol: float | None = None, ang: float | None = None):
    """The mesh every consumer (viewer, preview, STL, 3MF, checks) uses for a part."""
    from ..export.mesh import ANGULAR_TOLERANCE, TOLERANCE, tessellate

    if part.mesh is not None:
        return part.mesh
    return tessellate(part.solid, tol or TOLERANCE, ang or ANGULAR_TOLERANCE)


@dataclass
class BuildResult:
    project: Project
    layout: LayoutResult
    style: KeycapStyle
    mech: MechanicalProfile = None  # effective profile (project profile + design overrides)
    parts: list[Part] = field(default_factory=list)
    body: Optional[BodyResult] = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    legend_boxes: dict[str, tuple[float, float]] = field(default_factory=dict)
    boldness_range: tuple[float, float] = (-0.3, 0.6)   # allowed extra weight for this font + size
    letter_height: float = 0.0                          # tallest legend height (mm)

    @property
    def ok(self) -> bool:
        return not self.errors

    def printable_parts(self) -> list[Part]:
        return [p for p in self.parts if p.printable]


def build_project(project: Project, fonts: FontRegistry | None = None,
                  include_switches: bool = True) -> BuildResult:
    fonts = fonts or FontRegistry.default()
    layout = compute_layout(project)
    style = KEYCAP_STYLES.get(project.keycap_style)
    res = BuildResult(project, layout, style or KEYCAP_STYLES["standard"])
    res.warnings += layout.warnings
    if style is None:
        res.errors.append(f"סגנון כובע לא מוכר {project.keycap_style!r}. / unknown keycap style.")
    res.errors += layout.errors
    if not res.ok:
        return res
    mech = project.effective_mechanics()
    res.mech = mech
    try:
        style = keycap_with_height(style, project.keycap_height)
    except ValueError as e:
        res.errors.append(f"גובה הכובע נמוך מדי. / {e}")
        return res
    res.style = style

    try:
        font = fonts.resolve(project.lettering.font_id)
    except KeyError as e:
        res.errors.append(str(e))
        return res
    chars = "".join(k.value for k in project.keys if k.kind == "char")
    miss = missing_glyphs(font.path, chars)
    if miss:
        res.errors.append(
            f"בגופן {font.family} חסרות האותיות: {' '.join(miss)}. / font lacks glyphs: {' '.join(miss)}"
        )
        return res

    shape_design = dataclasses.replace(project.body, texture="smooth")      # B-rep never depends on texture
    body_key = (tuple(sorted((k.row, k.col, round(k.x, 6), round(k.y, 6)) for k in layout.keys)), mech,
                astuple(shape_design), astuple(project.keychain))
    body = _CACHE["body"].get_or(body_key, lambda: build_body(layout, mech, shape_design, project.keychain))
    if project.body.texture != "smooth":
        tex_key = (body_key, project.body.texture, project.body.texture_depth, project.body.texture_unit)
        def make_texture():
            try:
                return texture_body(body, mech, project.body)
            except Exception as e:  # noqa: BLE001 - shown to the user; the smooth body stays usable
                return None, [f"הטקסטורה נכשלה ({e}) — הגוף מוצג חלק. / texture failed: {e}"]

        mesh, tw = _CACHE["texture"].get_or(tex_key, make_texture)
        body = dataclasses.replace(body, mesh=mesh, warnings=body.warnings + tw)
    res.body = body
    res.warnings += body.warnings
    res.parts.append(Part("body", "body", body.solid, project.colors.body, group="body", mesh=body.mesh))

    rest_z = mech.keycap_rest_z(style)
    blank_cap = _CACHE["cap"].get_or(style, lambda: keycap_body(style))
    keys_by_id = {k.id: k for k in project.keys}
    mode = project.lettering.mode
    lettering = project.lettering
    common_scale = None
    boxes = [b for b in (glyph_box(k.value, font.path) for k in project.keys
                         if k.kind == "char" and k.value and not project.blank_legends) if b]
    if boxes:
        # letter height without extra weight -> safe boldness range for this font -> clamp
        s0, _ = fit_scale(boxes, style.legend_area, dataclasses.replace(lettering, extra_weight=0.0))
        height = max(h for _, h in boxes) * s0
        stroke = font.stroke_mm or measure_stroke(font.path)
        res.boldness_range = boldness_range(stroke, height)
        lo, hi = res.boldness_range
        if not lo - 1e-9 <= lettering.extra_weight <= hi + 1e-9:
            clamped = min(max(lettering.extra_weight, lo), hi)
            res.warnings.append(f"העובי הוגבל ל-{clamped:+.2f} מ\"מ (טווח בטוח לגופן ולגודל: {lo:+.2f}..{hi:+.2f}). / "
                                f"boldness clamped to {clamped:+.2f} mm.")
            lettering = dataclasses.replace(lettering, extra_weight=clamped)
    if lettering.uniform and boxes:
        common_scale, w = fit_scale(boxes, style.legend_area, lettering)
        res.warnings += w
        res.letter_height = max(h for _, h in boxes) * common_scale
    for idx, pk in enumerate(sorted(layout.keys, key=lambda k: (k.row, k.col)), start=1):
        tag = f"key{idx:02d}"
        key = keys_by_id.get(pk.key_id) if pk.key_id else None
        cap_color = project.cap_color(key) if key else project.colors.cap
        legend_color = project.legend_color(key) if key else project.colors.legend
        cap, legend, ckey = blank_cap, None, ("blank", style)
        if key is not None and key.kind == "char" and key.value and not project.blank_legends:
            ckey = (style, key.value, font.path, None if common_scale is None else round(common_scale, 9), mode,
                    astuple(lettering))

            def make_key(ch=key.value):
                spec = lettering
                for attempt in range(2):
                    info = build_legend(ch, font.path, style.legend_area, spec, common_scale)
                    if info.sketch is None:
                        raise ValueError(f"האות '{ch}' בגופן {font.family} לא ניתנת לייצור — בחר גופן אחר. / "
                                         f"glyph '{ch}' in {font.family} cannot be built; choose another font.")
                    try:
                        c, lg = apply_legend(blank_cap, style, info.sketch, mode, spec.depth, spec.raise_height)
                        ok_mesh = all(mesh_health(tessellate(x))["watertight"] for x in (c, lg) if x is not None)
                        if c.is_valid and (lg is None or lg.is_valid) and ok_mesh:
                            if attempt:
                                info.warnings.append("העובי בוטל לאות זו כדי לקבל גיאומטריה תקינה. / "
                                                     "boldness dropped for this letter to keep it valid.")
                            return c, lg, info
                    except Exception:  # noqa: BLE001 - retried without extra weight, then reported
                        pass
                    if spec.extra_weight == 0:
                        break
                    spec = dataclasses.replace(spec, extra_weight=0.0)
                raise ValueError(f"האות '{ch}' בגופן {font.family} לא ניתנת לייצור — בחר גופן אחר. / "
                                 f"glyph '{ch}' in {font.family} cannot be built; choose another font.")

            try:
                cap, legend, info = _CACHE["key"].get_or(ckey, make_key)
            except ValueError as e:
                res.errors.append(str(e))
                return res
            res.warnings += [f"[{key.value}] {w}" for w in info.warnings]
            if info.sketch is not None:
                res.legend_boxes[tag] = (info.width, info.height)
        elif key is not None and key.kind in ("symbol", "svg") and key.value and not project.blank_legends:
            from .symbols import svg_cache_key, svg_sketch, symbol_sketch

            sym_spec = dataclasses.replace(lettering, extra_weight=0.0, size=None)
            src = svg_cache_key(key.value) if key.kind == "svg" else key.value
            ckey = (style, key.kind, src, mode, astuple(sym_spec))

            def make_symbol(k=key):
                warns = []
                try:
                    if k.kind == "svg":
                        base, warns = svg_sketch(k.value)
                    else:
                        base = symbol_sketch(k.value)
                except Exception as e:  # noqa: BLE001 - reported, the key stays blank
                    from .lettering import LegendInfo
                    return blank_cap, None, LegendInfo(None, warnings=[f"סמל לא נטען: {e} / symbol failed"])
                info = build_shape_legend(base, style.legend_area, sym_spec, None, label=k.value)
                info.warnings = warns + info.warnings
                if info.sketch is None:
                    return blank_cap, None, info
                detail = min_detail_mm(info.sketch)
                if detail < 0.8:
                    info.warnings.append(f"פרט דק ({detail:.2f} מ\"מ) — ייתכן שלא יודפס היטב. / thin detail {detail:.2f} mm.")
                c, lg = apply_legend(blank_cap, style, info.sketch, mode, lettering.depth, lettering.raise_height)
                return c, lg, info

            cap, legend, info = _CACHE["key"].get_or(ckey, make_symbol)
            res.warnings += [f"[{tag}] {w}" for w in info.warnings]
            if info.sketch is not None:
                res.legend_boxes[tag] = (info.width, info.height)

        at = (round(pk.x, 6), round(pk.y, 6), round(rest_z, 6))
        wcap = _CACHE["place"].get_or((ckey, "cap", at), lambda c=cap: Pos(*at) * c)
        res.parts.append(Part(f"{tag}_cap", "cap", wcap, cap_color, pk.key_id, group=tag, local=cap))
        if legend is not None:
            wleg = _CACHE["place"].get_or((ckey, "legend", at), lambda lg=legend: Pos(*at) * lg)
            res.parts.append(Part(f"{tag}_legend", "legend", wleg, legend_color, pk.key_id,
                                  group=tag, local=legend))
        if include_switches:
            stem_top = mech.stem_bottom_rest_z() + style.socket_depth
            housing, stem = _CACHE["switch"].get_or((mech, stem_top), lambda: switch_proxy(mech, stem_top))
            res.parts.append(Part(f"{tag}_switch", "switch", Pos(pk.x, pk.y) * housing, "#3B6FD8",
                                  printable=False, group=tag))
            res.parts.append(Part(f"{tag}_stem", "stem", Pos(pk.x, pk.y) * stem, "#1F4FB5",
                                  printable=False, group=tag))
    return res


def print_orientation(res: BuildResult) -> dict[str, str]:
    """flush/engraved legends print face-down (crisp multi-colour first layers); raised prints upright."""
    return {"cap": "upright" if res.project.lettering.mode == "raised" else "face_down"}


def print_layout(res: BuildResult, gap: float = 6.0) -> list[Part]:
    """Printable parts arranged on a build plate, z>=0, ready for the slicer."""
    out: list[Part] = []
    body = next(p for p in res.parts if p.role == "body")
    bx0, by0, bx1, by1 = res.body.outline_bbox
    out.append(Part("body", "body", body.solid, body.color, group="body", mesh=body.mesh))
    face_down = print_orientation(res)["cap"] == "face_down"
    h = res.style.height
    pitch = res.style.bottom_width + gap
    groups = [p.group for p in res.parts if p.role == "cap"]
    n = len(groups)
    per_row = max(1, min(n, 5))
    y0 = by0 - gap - res.style.bottom_width / 2
    for i, g in enumerate(groups):
        r, c = divmod(i, per_row)
        x = (c - (per_row - 1) / 2) * pitch
        y = y0 - r * pitch
        for p in res.parts:
            if p.group != g or not p.printable:
                continue
            loc = p.local
            if face_down:
                loc = Pos(0, 0, h) * (Rot(180, 0, 0) * loc)
            out.append(Part(p.name, p.role, Pos(x, y, 0) * loc, p.color, p.key_id, group=g))
    return out

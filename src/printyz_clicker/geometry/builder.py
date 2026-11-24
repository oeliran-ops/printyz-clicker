"""Builds every part of a project from the single Project + LayoutResult.

The same BuildResult feeds the 3D preview and all exporters, so what is shown
is exactly what is exported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from build123d import Pos, Rot, Solid

from ..config.mechanical import KEYCAP_STYLES, KeycapStyle
from ..fonts.registry import FontRegistry, missing_glyphs
from ..layout.engine import LayoutResult, compute_layout
from ..model.project import Project
from .body import BodyResult, build_body
from .keycap import apply_legend, keycap_body
from .lettering import build_legend
from .switch_proxy import switch_proxy


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


@dataclass
class BuildResult:
    project: Project
    layout: LayoutResult
    style: KeycapStyle
    parts: list[Part] = field(default_factory=list)
    body: Optional[BodyResult] = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    legend_boxes: dict[str, tuple[float, float]] = field(default_factory=dict)

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
    mech = project.mechanical

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

    body = build_body(layout, mech, project.body, project.keychain)
    res.body = body
    res.warnings += body.warnings
    res.parts.append(Part("body", "body", body.solid, project.colors.body, group="body"))

    rest_z = mech.keycap_rest_z(style)
    blank_cap = keycap_body(style)
    keys_by_id = {k.id: k for k in project.keys}
    mode = project.lettering.mode

    for idx, pk in enumerate(sorted(layout.keys, key=lambda k: (k.row, k.col)), start=1):
        tag = f"key{idx:02d}"
        key = keys_by_id.get(pk.key_id) if pk.key_id else None
        cap_color = project.cap_color(key) if key else project.colors.cap
        legend_color = project.legend_color(key) if key else project.colors.legend
        cap, legend = blank_cap, None
        if key is not None and key.kind == "char" and key.value:
            info = build_legend(key.value, font.path, style.legend_area, project.lettering)
            res.warnings += [f"[{key.value}] {w}" for w in info.warnings]
            if info.sketch is not None:
                cap, legend = apply_legend(blank_cap, style, info.sketch, mode,
                                           project.lettering.depth, project.lettering.raise_height)
                res.legend_boxes[tag] = (info.width, info.height)
        elif key is not None and key.kind in ("symbol", "svg"):
            res.warnings.append(f"{tag}: סמלים/SVG עדיין לא ממומשים — המקש נוצר ריק. / symbols not implemented yet.")

        place = Pos(pk.x, pk.y, rest_z)
        res.parts.append(Part(f"{tag}_cap", "cap", place * cap, cap_color, pk.key_id, group=tag, local=cap))
        if legend is not None:
            res.parts.append(Part(f"{tag}_legend", "legend", place * legend, legend_color, pk.key_id,
                                  group=tag, local=legend))
        if include_switches:
            stem_top = mech.stem_bottom_rest_z() + style.socket_depth
            housing, stem = switch_proxy(mech, stem_top)
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
    out.append(Part("body", "body", body.solid, body.color, group="body"))
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

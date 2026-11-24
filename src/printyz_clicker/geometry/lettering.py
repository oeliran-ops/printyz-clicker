"""Lettering engine: real 2-D glyph geometry, sized against the keycap's true top area."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from build123d import Align, Kind, Pos, Sketch, Text, offset

from ..model.project import LetteringSpec

MIN_MARGIN, MAX_MARGIN = 1.0, 3.5


@dataclass
class LegendInfo:
    sketch: Optional[Sketch]
    width: float = 0.0
    height: float = 0.0
    scale: float = 1.0
    warnings: list[str] = field(default_factory=list)


def _merge_faces(sk) -> Sketch | None:
    faces = sk.faces()
    if not faces:
        return None
    out = faces[0]
    for f in faces[1:]:
        out = out.fuse(f)
    return Sketch(out.clean().faces())


def glyph_outline(char: str, font_path: str) -> Sketch | None:
    """Merged outline of one glyph at font size 10, or None if the font's outline is unusable."""
    try:
        return merged_outline(Text(char, font_size=10.0, font_path=font_path, align=(Align.CENTER, Align.CENTER)))
    except Exception:  # noqa: BLE001 - OCC rejects degenerate outlines in some font files
        return None


def merged_outline(text_shape) -> Sketch | None:
    """Union of all glyph contours: fonts may overlap contours (variable instances, pixel fonts)."""
    faces = text_shape.faces()
    if not faces:
        return None
    out = faces[0]
    for f in faces[1:]:
        out = out.fuse(f)
    out = out.clean()
    return Sketch(out.faces())


def safe_offset(sk, amount: float):
    """2-D offset that never raises: ARC, then INTERSECTION joins; None if the outline can't be offset
    or the result is not a valid region."""
    for kind in (Kind.ARC, Kind.INTERSECTION):
        try:
            out = offset(sk, amount=amount, kind=kind)
            if out.faces():
                out = _merge_faces(out)        # grown islands may now touch / overlap: one clean region
            if out is not None and out.faces() and all(f.is_valid for f in out.faces()):
                return out
        except Exception:  # noqa: BLE001 - OCC offset failures on complex outlines
            continue
    return None


def _counters(sk) -> int:
    return sum(len(f.inner_wires()) for f in sk.faces())


@lru_cache(maxsize=2048)
def glyph_box(char: str, font_path: str) -> tuple[float, float] | None:
    """Glyph outline size at font_size 10 (used to derive one common scale)."""
    t = glyph_outline(char, font_path)
    if t is None:
        return None
    bb = t.bounding_box()
    return bb.size.X, bb.size.Y


def fit_scale(boxes: list[tuple[float, float]], legend_area: float, spec: LetteringSpec) -> tuple[float, list[str]]:
    """One scale for a set of glyphs: every glyph fits; the tallest reaches spec.size if requested."""
    warnings: list[str] = []
    margin = min(max(spec.margin, MIN_MARGIN), MAX_MARGIN)
    avail = legend_area - 2 * margin - 2 * max(0.0, spec.extra_weight)
    if not boxes or avail <= 0:
        return 0.0, warnings
    fit = min(min(avail / w, avail / h) for w, h in boxes)
    if spec.size is None:
        pct = min(max(spec.size_pct, 10.0), 100.0)
        return fit * pct / 100.0, warnings
    want = spec.size / max(h for _, h in boxes)
    if want > fit:
        tallest = max(h for _, h in boxes) * fit
        warnings.append(f"גודל {spec.size:.1f} מ\"מ גדול מהשטח המותר — הוקטן ל-{tallest:.1f}. / "
                        f"size reduced to {tallest:.1f} mm to fit.")
    return min(want, fit), warnings


def build_legend(char: str, font_path: str, legend_area: float, spec: LetteringSpec,
                 scale: Optional[float] = None) -> LegendInfo:
    base = glyph_outline(char, font_path)
    if base is None:
        return LegendInfo(None, warnings=[f"לא ניתן לבנות את '{char}' בגופן הזה. / glyph '{char}' unusable in this font."])
    return build_shape_legend(base, legend_area, spec, scale, label=char)


def build_shape_legend(base: Sketch, legend_area: float, spec: LetteringSpec,
                       scale: Optional[float] = None, label: str = "") -> LegendInfo:
    """Build the glyph sketch, centred on (0,0) + offsets, guaranteed inside the allowed area.

    `scale` (from fit_scale over all keys) gives every key the same letter size; without it
    the glyph is fitted on its own.
    """
    warnings: list[str] = []
    margin = spec.margin
    if not (MIN_MARGIN <= margin <= MAX_MARGIN):
        clamped = min(max(margin, MIN_MARGIN), MAX_MARGIN)
        warnings.append(f"שוליים {margin} מחוץ לטווח 1–3.5 — הוגדר {clamped}. / margin clamped to {clamped}.")
        margin = clamped
    avail = legend_area - 2 * margin
    ew = max(-0.3, spec.extra_weight)
    if abs(ew) < 0.03:
        ew = 0.0

    char = label
    bb = base.bounding_box()
    if scale is None:
        scale, w2 = fit_scale([(bb.size.X, bb.size.Y)], legend_area, spec)
        warnings += w2
    if scale <= 0:
        return LegendInfo(None, warnings=warnings + ["אין מקום לאות עם העיבוי והשוליים שנבחרו. / No room for legend."])
    s = scale
    sk = base.scale(s)
    if ew > 0:
        before = _counters(sk)
        grown = safe_offset(sk, ew)
        while ew > 0.05 and (grown is None or _counters(grown) < before):
            ew = round(ew / 2, 3)                      # never fill an "o" / "ם", never fail: back off
            grown = safe_offset(sk, ew)
        if grown is not None and _counters(grown) >= before:
            sk = grown
            if ew < spec.extra_weight:
                warnings.append(f"העיבוי הוקטן ל-{ew:.2f} מ\"מ עבור '{char}'. / boldness reduced for '{char}'.")
        else:
            warnings.append(f"לא ניתן לעבות את '{char}' — נשאר המשקל המקורי. / '{char}' kept at original weight.")
    elif ew < 0:
        area0 = sum(f.area for f in sk.faces())
        thin = safe_offset(sk, ew)
        if thin is None or sum(f.area for f in thin.faces()) < 0.4 * area0:
            warnings.append("הדילול מוחק חלקים מהאות — נשאר המשקל המקורי. / thinning would erase strokes; ignored.")
        else:
            sk = thin
    # exact centring on the glyph bounding box (fonts carry side bearings)
    bb = sk.bounding_box()
    sk = Pos(-bb.center().X, -bb.center().Y) * sk
    w, h = bb.size.X, bb.size.Y

    # offsets: clamp so the glyph never leaves the allowed square
    lim_x = max(0.0, (avail - w) / 2)
    lim_y = max(0.0, (avail - h) / 2)
    ox = min(max(spec.offset_x, -lim_x), lim_x)
    oy = min(max(spec.offset_y, -lim_y), lim_y)
    if (ox, oy) != (spec.offset_x, spec.offset_y):
        warnings.append("ההזזה הוגבלה לגבולות השטח המותר. / offset clamped to allowed area.")
    sk = Pos(ox, oy) * sk
    if not isinstance(sk, Sketch):
        sk = Sketch(sk.faces())
    return LegendInfo(sk, w, h, s, warnings)


def min_detail_mm(sk: Sketch) -> float:
    """Typical feature width of a placed legend (2*area/perimeter, per island; smallest island)."""
    vals = []
    for f in sk.faces():
        per = sum(e.length for e in f.edges())
        if per > 0:
            vals.append(2 * f.area / per)
    return min(vals) if vals else 0.0

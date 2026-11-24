"""Lettering engine: real 2-D glyph geometry, sized against the keycap's true top area."""

from __future__ import annotations

from dataclasses import dataclass, field
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


def _counters(sk) -> int:
    return sum(len(f.inner_wires()) for f in sk.faces())


def glyph_box(char: str, font_path: str) -> tuple[float, float] | None:
    """Glyph outline size at font_size 10 (used to derive one common scale)."""
    t = Text(char, font_size=10.0, font_path=font_path, align=(Align.CENTER, Align.CENTER))
    if not t.faces():
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
        return fit, warnings
    want = spec.size / max(h for _, h in boxes)
    if want > fit:
        tallest = max(h for _, h in boxes) * fit
        warnings.append(f"גודל {spec.size:.1f} מ\"מ גדול מהשטח המותר — הוקטן ל-{tallest:.1f}. / "
                        f"size reduced to {tallest:.1f} mm to fit.")
    return min(want, fit), warnings


def build_legend(char: str, font_path: str, legend_area: float, spec: LetteringSpec,
                 scale: Optional[float] = None) -> LegendInfo:
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
    ew = max(0.0, spec.extra_weight)

    base = Text(char, font_size=10.0, font_path=font_path, align=(Align.CENTER, Align.CENTER))
    if not base.faces():
        return LegendInfo(None, warnings=warnings + [f"לגליף '{char}' אין גיאומטריה. / glyph has no outline."])
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
        sk = offset(sk, amount=ew, kind=Kind.ARC)
        if _counters(sk) < before:
            warnings.append("העיבוי סגר חלל פנימי באות. / extra weight closed a counter.")
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

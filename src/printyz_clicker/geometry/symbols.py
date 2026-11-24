"""Symbol engine: built-in symbol library (original, print-friendly shapes) and SVG import.

Every symbol is a 2-D Sketch in a ~10 x 10 unit box centred on the origin. The lettering
pipeline scales it to the keycap's real legend area, so symbols get the same flush /
raised / engraved modes and colours as letters. UI icons are generated from the same
sketch (sketch_to_svg), so the picker shows exactly what is printed.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from build123d import (
    Circle, Ellipse, Face, Polygon, Pos, Rectangle, RectangleRounded, Rot, Sketch, Wire,
)


def _poly(*pts) -> Sketch:
    """Polygon with consistent (counter-clockwise) winding, so booleans always merge."""
    area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))
    if area < 0:
        pts = pts[::-1]
    return Sketch() + Polygon(*pts, align=None)


def _star_pts(n: int, r_out: float, r_in: float, start: float = 90.0):
    pts = []
    for i in range(2 * n):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(start + i * 180.0 / n)
        pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


def _tri(r: float, rot: float = 90.0):
    return [(r * math.cos(math.radians(rot + k * 120)), r * math.sin(math.radians(rot + k * 120))) for k in range(3)]


def heart():
    return (Sketch() + Rot(0, 0, 45) * Rectangle(5.4, 5.4) + Pos(-1.91, 1.91) * Circle(2.7)
            + Pos(1.91, 1.91) * Circle(2.7))


def star():
    return _poly(*_star_pts(5, 5.2, 2.2))


def crown():
    body = _poly((-5, -2.0), (-5, 3.0), (-2.4, 0.6), (0, 4.2), (2.4, 0.6), (5, 3.0), (5, -2.0))
    tips = Pos(-5, 3.0) * Circle(0.85) + Pos(0, 4.2) * Circle(0.85) + Pos(5, 3.0) * Circle(0.85)
    band = Pos(0, -3.5) * RectangleRounded(10, 1.9, 0.5)
    return body + tips + band


def crown_queen():
    """Tiara: an arched band with a tall central peak, a jewel and two side peaks (one piece)."""
    arc = (Sketch() + Pos(0, -9.2) * Circle(8.6)) - Pos(0, -9.2) * Circle(7.0)
    arc = arc & (Pos(0, -1.5) * Rectangle(11.0, 5.0))
    peaks = _poly((-4.7, -2.4), (-3.7, 2.0), (-2.2, 0.7), (0, 3.6), (2.2, 0.7), (3.7, 2.0), (4.7, -2.4), (0, -0.9))
    pearls = Pos(-3.7, 2.5) * Circle(0.8) + Pos(3.7, 2.5) * Circle(0.8) + Pos(0, 4.3) * Circle(1.0)
    jewel = Pos(0, 1.2) * Rot(0, 0, 45) * Rectangle(1.4, 1.4)
    return (arc + peaks + pearls) - jewel


def moon():
    return Sketch() + Circle(5) - Pos(2.3, 1.4) * Circle(4.1)


def sun():
    s = Sketch() + Circle(2.6)
    for k in range(8):
        s += Rot(0, 0, k * 45) * Pos(0, 4.2) * RectangleRounded(1.4, 1.9, 0.5)
    return s


def bolt():
    return _poly((1.2, 5.2), (-3.4, -0.4), (-0.4, -0.4), (-1.6, -5.2), (3.4, 1.0), (0.4, 1.0), (2.2, 5.2))


def music():
    head = Pos(-1.6, -3.2) * Rot(0, 0, -20) * Ellipse(2.2, 1.6)
    stem = Pos(0.0, 0.7) * Rectangle(1.2, 8.0)
    flag = _poly((-0.6, 4.7), (3.6, 2.6), (3.6, 0.6), (-0.6, 2.4))
    return Sketch() + head + stem + flag


def paw():
    s = Sketch() + Pos(0, -1.8) * Ellipse(2.8, 2.3)
    for x, y, a in ((-3.3, 1.1, 20), (-1.2, 3.2, 5), (1.2, 3.2, -5), (3.3, 1.1, -20)):
        s += Pos(x, y) * Rot(0, 0, a) * Ellipse(1.15, 1.5)
    return s


def smile():
    face = Sketch() + Circle(5)
    eyes = Pos(-1.8, 1.6) * Circle(0.75) + Pos(1.8, 1.6) * Circle(0.75)
    band = (Sketch() + Pos(0, 0.4) * Circle(3.3)) - Pos(0, 0.4) * Circle(2.2)
    mouth = band & (Pos(0, -3.0) * Rectangle(8, 4.2))
    return face - eyes - mouth


def arrow(deg: float = 0.0):
    s = _poly((-1.4, -5), (1.4, -5), (1.4, 0.4), (4.6, 0.4), (0, 5), (-4.6, 0.4), (-1.4, 0.4))
    return Rot(0, 0, deg) * s


def gamepad():
    body = Sketch() + RectangleRounded(10.4, 6.0, 2.8)
    dpad = Pos(-2.7, 0) * (Rectangle(2.8, 0.95) + Rectangle(0.95, 2.8))
    btn = Pos(2.4, 0.7) * Circle(0.62) + Pos(3.4, -0.5) * Circle(0.62)
    return body - dpad - btn


def flame():
    outer = Sketch() + Pos(0, -1.6) * Circle(3.4) + _poly((-3.1, -0.8), (3.1, -0.8), (0.4, 5.2))
    inner = Sketch() + Pos(0, -2.4) * Circle(1.5) + _poly((-1.35, -2.0), (1.35, -2.0), (0.1, 1.2))
    return outer - inner


def leaf():
    lens = (Sketch() + Pos(-2.6, 0) * Circle(4.6)) & (Pos(2.6, 0) * Circle(4.6))
    return Rot(0, 0, 45) * lens


def gem():
    return (_poly((-5, 1.6), (-3, 4.2), (3, 4.2), (5, 1.6), (0, -4.8))
            - _poly((-2.6, 1.2), (2.6, 1.2), (0, -2.4)))


def check():
    return _poly((-5, 0.4), (-3.3, 2.1), (-1.3, 0.1), (3.6, 5.0), (5.3, 3.3), (-1.3, -3.3))


def plus():
    return Sketch() + RectangleRounded(9.4, 3.0, 0.6) + RectangleRounded(3.0, 9.4, 0.6)


def magen_david():
    t1 = _poly(*_tri(5.4, 90)) - _poly(*_tri(3.8, 90))
    t2 = _poly(*_tri(5.4, -90)) - _poly(*_tri(3.8, -90))
    return t1 + t2


def cloud():
    return (Sketch() + Pos(-2.4, -0.6) * Circle(2.4) + Pos(0.6, 1.2) * Circle(3.0) + Pos(3.2, -0.8) * Circle(2.0)
            + Pos(0.4, -1.8) * RectangleRounded(9.6, 3.0, 1.4))


def home():
    house = _poly((-5, 0.6), (0, 5.2), (5, 0.6), (3.6, 0.6), (3.6, -4.8), (-3.6, -4.8), (-3.6, 0.6))
    door = Pos(0, -2.8) * Rectangle(2.0, 4.2)
    return house - door


def infinity():
    ring = (Sketch() + Circle(2.6)) - Circle(1.35)
    return Pos(-2.3, 0) * ring + Pos(2.3, 0) * ring


def play():
    return _poly((-3.6, -4.6), (-3.6, 4.6), (4.8, 0))


def clover():
    s = Sketch()
    for x, y in ((-1.7, 1.7), (1.7, 1.7), (-1.7, -1.4), (1.7, -1.4)):
        s += Pos(x, y + 0.4) * Circle(2.1)
    s += Pos(0, 0.4) * Circle(1.4)                 # fill the tiny gap between the leaves
    s += _poly((-0.5, -2.0), (0.5, -2.0), (1.6, -5.2), (0.6, -5.2))
    return s


def snowflake():
    s = Sketch() + RectangleRounded(1.3, 10.2, 0.5)
    s += Rot(0, 0, 60) * RectangleRounded(1.3, 10.2, 0.5)
    s += Rot(0, 0, 120) * RectangleRounded(1.3, 10.2, 0.5)
    return s


def dice():
    s = Sketch() + RectangleRounded(10, 10, 2.0)
    for x, y in ((-2.7, 2.7), (2.7, -2.7), (0, 0), (2.7, 2.7), (-2.7, -2.7)):
        s -= Pos(x, y) * Circle(0.95)
    return s


def trophy():
    cup = _poly((-3.4, 4.8), (3.4, 4.8), (3.0, 1.0), (0.9, -0.8), (-0.9, -0.8), (-3.0, 1.0))
    handles = ((Sketch() + Pos(-3.4, 2.8) * Circle(1.7)) - Pos(-3.4, 2.8) * Circle(0.85)) + \
              ((Sketch() + Pos(3.4, 2.8) * Circle(1.7)) - Pos(3.4, 2.8) * Circle(0.85))
    stem = Pos(0, -2.2) * Rectangle(1.4, 3.0)
    base = Pos(0, -4.2) * RectangleRounded(6.0, 1.6, 0.5)
    return cup + handles + stem + base


def cat():
    head = Sketch() + Pos(0, -0.8) * Ellipse(4.8, 4.0)
    ears = _poly((-4.4, -0.8), (-4.2, 5.0), (-0.8, 2.2), (-1.6, -0.8)) + _poly((4.4, -0.8), (4.2, 5.0), (0.8, 2.2),
                                                                           (1.6, -0.8))
    eyes = Pos(-1.8, -0.2) * Ellipse(0.75, 1.1) + Pos(1.8, -0.2) * Ellipse(0.75, 1.1)
    nose = _poly((-0.7, -2.0), (0.7, -2.0), (0, -2.9))
    return head + ears - eyes - nose


SYMBOLS: dict[str, tuple[str, str, object]] = {
    # id: (Hebrew name, English name, builder)
    "heart": ("לב", "Heart", heart), "star": ("כוכב", "Star", star), "crown": ("כתר מלך", "King crown", crown),
    "crown_queen": ("כתר מלכה", "Queen crown", crown_queen),
    "magen_david": ("מגן דוד", "Star of David", magen_david), "moon": ("ירח", "Moon", moon),
    "sun": ("שמש", "Sun", sun), "bolt": ("ברק", "Lightning", bolt), "drop": ("טיפה", "Drop", flame),
    "music": ("תו", "Music", music), "paw": ("כף רגל", "Paw", paw), "cat": ("חתול", "Cat", cat),
    "smile": ("סמיילי", "Smiley", smile), "gamepad": ("שלט משחק", "Gamepad", gamepad),
    "dice": ("קובייה", "Dice", dice), "trophy": ("גביע", "Trophy", trophy), "gem": ("יהלום", "Gem", gem),
    "leaf": ("עלה", "Leaf", leaf), "clover": ("תלתן", "Clover", clover), "snowflake": ("פתית שלג", "Snowflake", snowflake),
    "cloud": ("ענן", "Cloud", cloud), "home": ("בית", "Home", home), "infinity": ("אינסוף", "Infinity", infinity),
    "check": ("וי", "Check", check), "plus": ("פלוס", "Plus", plus), "play": ("הפעלה", "Play", play),
    "arrow_up": ("חץ למעלה", "Arrow up", lambda: arrow(0)), "arrow_down": ("חץ למטה", "Arrow down", lambda: arrow(180)),
    "arrow_left": ("חץ שמאלה", "Arrow left", lambda: arrow(90)), "arrow_right": ("חץ ימינה", "Arrow right", lambda: arrow(-90)),
}


@lru_cache(maxsize=64)
def symbol_sketch(sid: str) -> Sketch:
    if sid not in SYMBOLS:
        raise KeyError(f"Unknown symbol {sid!r}")
    sk = SYMBOLS[sid][2]()
    if not isinstance(sk, Sketch):
        sk = Sketch(sk.faces())
    return Sketch(sk.clean().faces())


# ---------------------------------------------------------------------------------------------
def _sample_wire(w, step: float = 0.15) -> np.ndarray:
    n = max(16, int(w.length / step))
    return np.array([(p.X, p.Y) for p in w.positions([i / n for i in range(n)])])


def sketch_to_svg(sk: Sketch, color: str = "#2B2F36", size: int = 64) -> str:
    """SVG icon of a sketch (exactly the printed outline) for the UI."""
    bb = sk.bounding_box()
    span = max(bb.size.X, bb.size.Y) * 1.1
    cx, cy = bb.center().X, bb.center().Y
    d = []
    for f in sk.faces():
        for w in [f.outer_wire(), *f.inner_wires()]:
            pts = _sample_wire(w)
            pts = (pts - (cx, cy)) / span * size + size / 2
            d.append("M" + " L".join(f"{x:.2f},{size - y:.2f}" for x, y in pts) + " Z")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">'
            f'<path fill="{color}" fill-rule="evenodd" d="{" ".join(d)}"/></svg>')


# ---------------------------------------------------------------------------------------------
class SvgImportError(ValueError):
    pass


def svg_sketch(path: str) -> tuple[Sketch, list[str]]:
    """Import filled shapes from an SVG file. Returns (sketch, warnings). Raises SvgImportError
    for files that cannot become printable geometry (spec 20)."""
    from matplotlib.path import Path as MPath
    from svgpathtools import svg2paths2

    warnings: list[str] = []
    try:
        paths, attrs, _ = svg2paths2(str(path), convert_circles_to_paths=True, convert_ellipses_to_paths=True,
                                     convert_lines_to_paths=False, convert_polylines_to_paths=True,
                                     convert_polygons_to_paths=True, convert_rectangles_to_paths=True)
    except Exception as e:  # noqa: BLE001
        raise SvgImportError(f"קובץ SVG לא תקין: {e} / invalid SVG") from e
    loops: list[np.ndarray] = []
    for p, a in zip(paths, attrs):
        style = (a.get("style", "") + ";" + a.get("fill", "")).replace(" ", "")
        if "fill:none" in style or a.get("fill") == "none":
            warnings.append("נמצא קו ללא מילוי (stroke) — הוא לא יודפס. המר אותו לצורה ב־Illustrator. / "
                            "stroke-only path ignored (convert strokes to outlines).")
            continue
        if "transform" in a:
            warnings.append("לנתיב יש transform — ייתכן שהמיקום לא מדויק. / path transform ignored.")
        for sub in p.continuous_subpaths():
            if len(sub) == 0:
                continue
            if abs(sub.start - sub.end) > 1e-3 * max(1.0, sub.length()):
                warnings.append("נמצא מסלול פתוח — נסגר אוטומטית. / open path closed automatically.")
            n = max(24, int(sub.length() / 0.5))
            pts = np.array([sub.point(t) for t in np.linspace(0, 1, n, endpoint=False)])
            loops.append(np.stack([pts.real, -pts.imag], 1))        # SVG y points down
    if not loops:
        raise SvgImportError("לא נמצאו צורות מלאות בקובץ. / no filled shapes found.")
    # even-odd nesting: depth parity decides material vs hole
    mp = [MPath(lp) for lp in loops]
    faces = []
    for i, lp in enumerate(loops):
        depth = sum(1 for j, other in enumerate(mp) if j != i and other.contains_point(lp[0]))
        f = Face(Wire.make_polygon([(x, y, 0) for x, y in lp], close=True))
        faces.append((depth, f))
    sk = Sketch()
    for depth, f in sorted(faces, key=lambda t: t[0]):
        sk = sk + f if depth % 2 == 0 else sk - f
    sk = Sketch(sk.clean().faces())
    if not sk.faces():
        raise SvgImportError("הצורות בקובץ מבטלות זו את זו. / shapes cancel out.")
    bb = sk.bounding_box()
    s = 10.0 / max(bb.size.X, bb.size.Y)           # normalise into the 10-unit box
    sk = Sketch(sk.scale(s).faces())
    bb = sk.bounding_box()
    sk = Sketch((Pos(-bb.center().X, -bb.center().Y) * sk).faces())
    tiny = [f for f in sk.faces() if f.area < 0.6]
    if tiny:
        warnings.append(f"{len(tiny)} חלקים קטנים מאוד — ייתכן שלא יודפסו. / {len(tiny)} tiny parts may not print.")
    return sk, warnings


def svg_cache_key(path: str) -> tuple[str, float]:
    p = Path(path)
    return str(p), p.stat().st_mtime if p.exists() else 0.0


# ---------------------------------------------------------------------------------------------
class SymbolLibrary:
    """Which built-in symbols customers may use (developer setting, stored as JSON)."""

    def __init__(self, path: Path | None = None):
        import json

        self.path = path
        self.hidden: set[str] = set()
        if path and path.exists():
            try:
                self.hidden = set(json.loads(path.read_text("utf-8")).get("hidden", []))
            except Exception:  # noqa: BLE001 - a broken settings file must not block the app
                self.hidden = set()

    def visible(self, sid: str) -> bool:
        return sid not in self.hidden

    def set_visible(self, sid: str, on: bool) -> None:
        import json

        (self.hidden.discard if on else self.hidden.add)(sid)
        if self.path:
            self.path.write_text(json.dumps({"hidden": sorted(self.hidden)}, indent=1), "utf-8")

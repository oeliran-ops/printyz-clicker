"""Screen downloaded fonts for 3D printing and remove look-alikes.

Metric: average stroke width = 2*area/perimeter of real glyph outlines at a 9 mm
cap height (what a legend looks like on a keycap). Thin or rough/textured fonts
score low. Look-alikes are found by comparing rasterised samples (IoU).
Writes assets/fonts/catalog.json and deletes rejected files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from build123d import Align, Text

FONTS = Path(__file__).resolve().parent.parent / "src/printyz_clicker/assets/fonts"
MIN_STROKE = 0.85        # mm at 9 mm letter height (>= 2 extrusion lines with a 0.4 nozzle)
MAX_ISLANDS = 3
MANUAL_REJECT = {"permanentmarker": "rough brush edges"}          # a single glyph made of more pieces than this = texture / distressed
DUP_IOU = 0.45     # outline-band overlap; calibrated on known pairs (Open Sans ~ Noto Sans)
HEB = "אבגדהוזחטיכלמנסעפצקרשתךםןףץ"
LAT = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
SAMPLE_LAT = "RgaSB5"
SAMPLE_HEB = "שלאםג"


def cmap(path):
    from fontTools.ttLib import TTFont
    return set(TTFont(path, lazy=True).getBestCmap())


def stroke_and_islands(path: str, chars: str) -> tuple[float, int]:
    strokes, islands = [], 0
    for ch in chars:
        t = Text(ch, font_size=10, font_path=path, align=(Align.CENTER, Align.CENTER))
        if not t.faces():
            continue
        h = t.bounding_box().size.Y
        s = 9.0 / max(h, 1e-6) if ch.isupper() or ch in SAMPLE_HEB else 9.0 / 10 * 0.75
        area = sum(f.area for f in t.faces()) * s * s
        per = sum(e.length for f in t.faces() for e in f.edges()) * s
        strokes.append(2 * area / per)
        islands = max(islands, len(t.faces()))
    return float(np.percentile(strokes, 25)) if strokes else 0.0, islands


def raster(path: str, text: str, n: int = 96) -> np.ndarray:
    """Outline-band bitmap of each glyph normalised to its own box (compares shapes, not ink)."""
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextPath
    from scipy.ndimage import binary_erosion

    prop = FontProperties(fname=path)
    tiles = []
    for ch in text:
        tp = TextPath((0, 0), ch, size=100, prop=prop)
        (x0, y0), (x1, y1) = tp.get_extents().get_points()
        xs, ys = np.meshgrid(np.linspace(x0, x1, n), np.linspace(y0, y1, n))
        ink = tp.contains_points(np.stack([xs.ravel(), ys.ravel()], 1)).reshape(n, n)
        band = ink & ~binary_erosion(ink, iterations=3)
        tiles.append(band.ravel())
    return np.concatenate(tiles)


def main() -> int:
    raw = json.loads((FONTS / "_downloaded.json").read_text("utf-8"))
    rows = []
    for e in raw:
        p = str(FONTS / e["file"])
        cm = cmap(p)
        e["hebrew"] = all(ord(c) in cm for c in HEB)
        e["latin"] = all(ord(c) in cm for c in LAT)
        sample = (SAMPLE_HEB if e["hebrew"] else "") + SAMPLE_LAT
        e["stroke_mm"], e["islands"] = stroke_and_islands(p, sample)
        ok = e["dir"] not in MANUAL_REJECT and e["latin"] and e["stroke_mm"] >= MIN_STROKE and e["islands"] <= MAX_ISLANDS
        e["status"] = "ok" if ok else ("thin" if e["stroke_mm"] < MIN_STROKE else
                                       "texture" if e["islands"] > MAX_ISLANDS else "coverage")
        rows.append(e)
        print(f'{e["family"]:22s} {e["weight"]:4d} heb={int(e["hebrew"])} stroke={e["stroke_mm"]:.2f} '
              f'isl={e["islands"]} -> {e["status"]}')

    # look-alikes: compare the bold-most passing instance of each family
    fams: dict[str, dict] = {}
    for e in rows:
        if e["status"] == "ok" and (e["dir"] not in fams or e["weight"] > fams[e["dir"]]["weight"]):
            fams[e["dir"]] = e
    order = [d for d, _, _ in __import__("fetch_fonts").CANDIDATES if d in fams]   # preference order
    kept: list[str] = []
    bitmaps: dict[str, np.ndarray] = {}
    for d in order:
        e = fams[d]
        text = (SAMPLE_HEB if e["hebrew"] else "") + SAMPLE_LAT
        bitmaps[d] = raster(str(FONTS / e["file"]), SAMPLE_LAT + (SAMPLE_HEB if e["hebrew"] else ""))
        dup = None
        for k in kept:
            a, b = bitmaps[d], bitmaps[k]
            if fams[k]["hebrew"] != e["hebrew"] or len(a) != len(b):
                continue      # only compare fonts covering the same scripts
            iou = (a & b).sum() / max((a | b).sum(), 1)
            print(f"   iou {e['family']:20s} vs {fams[k]['family']:20s} {iou:.2f}")
            if iou > DUP_IOU:
                dup = (k, iou)
                break
        if dup:
            print(f"duplicate: {e['family']} ~ {fams[dup[0]]['family']} (IoU {dup[1]:.2f})")
            for r in rows:
                if r["dir"] == d:
                    r["status"] = f"duplicate of {fams[dup[0]]['family']}"
        else:
            kept.append(d)
        _ = text

    catalog = [r for r in rows if r["status"] == "ok"]
    for r in rows:
        if r["status"] != "ok":
            (FONTS / r["file"]).unlink(missing_ok=True)
    keep_dirs = {r["dir"] for r in catalog}
    for lic in FONTS.glob("*.LICENSE.txt"):
        if lic.name.split(".")[0] not in keep_dirs:
            lic.unlink()
    (FONTS / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=1), "utf-8")
    (FONTS / "screening_report.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
    print(f"\nkept {len(catalog)} font files from {len(keep_dirs)} families "
          f"({sum(1 for d in keep_dirs if any(r['hebrew'] for r in catalog if r['dir'] == d))} with Hebrew)")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    sys.exit(main())

"""Download free (OFL / Apache) fonts from the Google Fonts repository, make static
Regular/Bold instances, and keep only print-friendly, non-duplicate families.

Run:  python tools/fetch_fonts.py      (developer tool; output goes to assets/fonts)
"""
from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.removeOverlaps import removeOverlaps
from fontTools.varLib import instancer

RAW = "https://raw.githubusercontent.com/google/fonts/main/{lic}/{d}/{f}"
OUT = Path(__file__).resolve().parent.parent / "src/printyz_clicker/assets/fonts"

# family dir, licence dir, category
CANDIDATES = [
    # Hebrew + Latin
    ("rubik", "ofl", "sans"), ("heebo", "ofl", "sans"), ("assistant", "ofl", "sans"),
    ("secularone", "ofl", "display"), ("varelaround", "ofl", "rounded"), ("suezone", "ofl", "serif"),
    ("frankruhllibre", "ofl", "serif"), ("davidlibre", "ofl", "serif"), ("karantina", "ofl", "display"),
    ("fredoka", "ofl", "rounded"), ("ibmplexsanshebrew", "ofl", "sans"), ("playpensanshebrew", "ofl", "hand"),
    ("notosanshebrew", "ofl", "sans"), ("opensans", "ofl", "sans"), ("alef", "ofl", "sans"),
    ("miriamlibre", "ofl", "sans"), ("notoserifhebrew", "ofl", "serif"), ("bonanova", "ofl", "serif"),
    ("arimo", "apache", "sans"), ("tinos", "apache", "serif"), ("cousine", "apache", "mono"),
    # Latin display / text
    ("anton", "ofl", "display"), ("bebasneue", "ofl", "display"), ("bungee", "ofl", "display"),
    ("archivoblack", "ofl", "display"), ("bangers", "ofl", "display"), ("lilitaone", "ofl", "display"),
    ("luckiestguy", "apache", "display"), ("righteous", "ofl", "display"), ("russoone", "ofl", "display"),
    ("titanone", "ofl", "display"), ("chakrapetch", "ofl", "tech"), ("audiowide", "ofl", "tech"),
    ("orbitron", "ofl", "tech"), ("pressstart2p", "ofl", "pixel"), ("pacifico", "ofl", "script"),
    ("lobster", "ofl", "script"), ("oswald", "ofl", "sans"), ("montserrat", "ofl", "sans"),
    ("poppins", "ofl", "sans"), ("robotoslab", "apache", "serif"), ("arvo", "ofl", "serif"),
    ("alfaslabone", "ofl", "serif"), ("bowlbyone", "ofl", "display"), ("passionone", "ofl", "display"),
    ("concertone", "ofl", "rounded"), ("kanit", "ofl", "sans"), ("exo2", "ofl", "tech"),
    ("teko", "ofl", "display"), ("staatliches", "ofl", "display"), ("rammettoone", "ofl", "display"),
    ("racingsansone", "ofl", "display"), ("rubikmonoone", "ofl", "display"), ("blackopsone", "ofl", "display"),
    ("changaone", "ofl", "display"), ("fjallaone", "ofl", "display"), ("paytoneone", "ofl", "display"),
    ("squadaone", "ofl", "display"), ("carterone", "ofl", "display"), ("nunito", "ofl", "rounded"),
    ("comfortaa", "ofl", "rounded"), ("quicksand", "ofl", "rounded"), ("baloo2", "ofl", "rounded"),
    ("sigmar", "ofl", "display"), ("bagelfatone", "ofl", "display"), ("shrikhand", "ofl", "script"),
    ("caveatbrush", "ofl", "hand"), ("permanentmarker", "apache", "hand"), ("specialelite", "apache", "texture"),
]


def get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def files_for(d: str, lic: str) -> tuple[str, list[str]]:
    meta = get(RAW.format(lic=lic, d=d, f="METADATA.pb")).decode()
    name = re.search(r'^name: "(.+)"', meta, re.M).group(1)
    files, cur_style = [], None
    for block in meta.split("fonts {")[1:]:
        style = re.search(r'style: "(\w+)"', block).group(1)
        fn = re.search(r'filename: "(.+?)"', block).group(1)
        if style == "normal":
            files.append(fn)
    _ = cur_style
    return name, files


def static_instances(data: bytes) -> dict[int, TTFont]:
    """{weight: font} for 400 and 700 (or the nearest the family has)."""
    f = TTFont(io.BytesIO(data))
    if "fvar" not in f:
        return {int(f["OS/2"].usWeightClass): f}
    axis = next(a for a in f["fvar"].axes if a.axisTag == "wght") if any(
        a.axisTag == "wght" for a in f["fvar"].axes) else None
    out = {}
    for w in (400, 700):
        loc = {}
        for a in f["fvar"].axes:
            loc[a.axisTag] = min(max(w, a.minValue), a.maxValue) if a.axisTag == "wght" else a.defaultValue
        inst = instancer.instantiateVariableFont(TTFont(io.BytesIO(data)), loc, updateFontNames=True)
        inst["OS/2"].usWeightClass = int(loc.get("wght", w))
        out[int(loc.get("wght", w))] = inst
    _ = axis
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = []
    for d, lic, cat in CANDIDATES:
        try:
            name, files = files_for(d, lic)
        except Exception as e:  # noqa: BLE001
            print(f"skip {d}: {e}", file=sys.stderr)
            continue
        got: dict[int, TTFont] = {}
        for fn in files:
            data = get(RAW.format(lic=lic, d=d, f=urllib.request.quote(fn)))
            for w, font in static_instances(data).items():
                got.setdefault(w, font)
        if not got:
            continue
        lic_text = get(RAW.format(lic=lic, d=d, f="OFL.txt" if lic == "ofl" else "LICENSE.txt"))
        (OUT / f"{d}.LICENSE.txt").write_bytes(lic_text)
        wanted = sorted(got)
        pick = {min(wanted, key=lambda w: abs(w - 400)), min(wanted, key=lambda w: abs(w - 700))}
        for w in sorted(pick):
            path = OUT / f"{d}-{w}.ttf"
            try:
                removeOverlaps(got[w])   # instances/pixel fonts overlap contours -> open meshes
            except Exception as e:  # noqa: BLE001
                print(f"  overlap removal failed for {d}-{w}: {e}", file=sys.stderr)
            got[w].save(path)
            catalog.append({"dir": d, "family": name, "weight": w, "file": path.name, "category": cat,
                            "license": "OFL-1.1" if lic == "ofl" else "Apache-2.0"})
        print("ok", name, sorted(pick))
    (OUT / "_downloaded.json").write_text(json.dumps(catalog, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

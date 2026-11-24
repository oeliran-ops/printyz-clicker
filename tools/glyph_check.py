"""Build every required glyph of every bundled font as a real flush legend on a keycap.
Fonts with any glyph that fails (invalid solid / open mesh / exception) are removed from the
catalog. Developer QA tool; run after tools/screen_fonts.py."""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

FONTS = Path(__file__).resolve().parent.parent / "src/printyz_clicker/assets/fonts"
HEB = "אבגדהוזחטיכלמנסעפצקרשתךםןףץ"
LAT = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def check_font(entry: dict) -> tuple[str, list[str]]:
    from printyz_clicker.config.mechanical import KEYCAP_STYLES
    from printyz_clicker.export.mesh import mesh_health, tessellate
    from printyz_clicker.geometry.keycap import apply_legend, keycap_body
    from printyz_clicker.geometry.lettering import build_legend, fit_scale, glyph_box
    from printyz_clicker.model.project import LetteringSpec

    path = str(FONTS / entry["file"])
    st = KEYCAP_STYLES["standard"]
    cap = keycap_body(st)
    chars = (HEB if entry["hebrew"] else "") + LAT
    spec = LetteringSpec()
    bad = []
    boxes = [b for b in (glyph_box(c, path) for c in chars) if b]
    scale, _ = fit_scale(boxes, st.legend_area, spec)
    for ch in chars:
        try:
            info = build_legend(ch, path, st.legend_area, spec, scale)
            if info.sketch is None:
                bad.append(ch)
                continue
            c, lg = apply_legend(cap, st, info.sketch, "flush", spec.depth, spec.raise_height)
            ok = c.is_valid and lg.is_valid and mesh_health(tessellate(lg))["watertight"] \
                and mesh_health(tessellate(c))["watertight"]
            if not ok:
                bad.append(ch)
        except Exception:  # noqa: BLE001
            bad.append(ch)
    return entry["file"], bad


def main() -> int:
    cat = json.loads((FONTS / "catalog.json").read_text("utf-8"))
    with ProcessPoolExecutor(max_workers=4) as ex:
        results = dict(ex.map(check_font, cat))
    keep, drop = [], []
    for e in cat:
        bad = results[e["file"]]
        (drop if bad else keep).append(e)
        print(f"{e['family']:22s} {e['weight']}: {'OK' if not bad else 'FAIL ' + ''.join(bad)}")
    for e in drop:
        (FONTS / e["file"]).unlink(missing_ok=True)
    dirs = {e["dir"] for e in keep}
    for lic in FONTS.glob("*.LICENSE.txt"):
        if lic.name.split(".")[0] not in dirs:
            lic.unlink()
    (FONTS / "catalog.json").write_text(json.dumps(keep, ensure_ascii=False, indent=1), "utf-8")
    print(f"\nkept {len(keep)} / {len(cat)} font files")
    return 0


if __name__ == "__main__":
    sys.exit(main())

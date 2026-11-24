"""End-to-end QA: build + full validation (watertight meshes) + export + reload for a matrix
of feature combinations. Developer tool; prints a summary and exits non-zero on any failure."""
import itertools
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from printyz_clicker.export.exporter import export_all
from printyz_clicker.fonts.registry import FontRegistry
from printyz_clicker.geometry.builder import build_project
from printyz_clicker.model.project import Project
from printyz_clicker.text.engine import insert_key_visual, sync_keys_from_text
from printyz_clicker.validation.checks import validate

reg = FontRegistry.default()
CASES = []
names = {"row": "שלום", "column": "Dan", "grid": "Daniel", "wasd": "WASD", "arrows": "abcd", "custom": "abc"}
for layout, mode, cap, tex, kc in itertools.product(
        ["row", "column", "grid", "wasd", "custom"], ["flush", "raised", "engraved"],
        ["standard", "low_profile", "thocky"], ["smooth", "diamond", "ribs", "fluted", "dots", "chevron"],
        [None, "top", "right"]):
    CASES.append(dict(layout=layout, mode=mode, cap=cap, tex=tex, kc=kc))
# keep it affordable: every value of every option appears, combined pseudo-randomly
import random
random.seed(7)
CASES = random.sample(CASES, 60)
CASES += [dict(layout="row", mode="flush", cap="standard", tex="smooth", kc=None, extra="symbols"),
          dict(layout="row", mode="raised", cap="standard", tex="dots", kc="left", extra="mixed"),
          dict(layout="grid", mode="flush", cap="thocky", tex="ribs", kc="bottom", extra="fillblank"),
          dict(layout="row", mode="flush", cap="standard", tex="smooth", kc=None, extra="rim+height")]

fails = []
t0 = time.time()
tmp = Path(tempfile.mkdtemp())
for i, c in enumerate(CASES):
    p = Project(name=f"qa{i:02d}")
    sync_keys_from_text(p, "דני 12" if c.get("extra") == "mixed" else names[c["layout"]])
    p.layout.style = c["layout"]
    if c["layout"] == "grid":
        p.layout.rows, p.layout.cols = 2, 3
    if c["layout"] == "custom":
        p.layout.custom_cells = {p.keys[0].id: [0, 0], p.keys[1].id: [1, 0], p.keys[2].id: [1, 1]}
    p.lettering.mode, p.keycap_style, p.body.texture = c["mode"], c["cap"], c["tex"]
    if c["kc"]:
        p.keychain.enabled, p.keychain.side = True, c["kc"]
    if c.get("extra") == "symbols":
        for sid in ("crown", "heart", "magen_david"):
            insert_key_visual(p, "left", None, "symbol", sid)
    if c.get("extra") == "fillblank":
        p.layout.fill_empty_with_blank = True
    if c.get("extra") == "rim+height":
        p.body.rim_height, p.keycap_height = 19.0, 10.0
    try:
        r = build_project(p, reg, include_switches=False)
        v = validate(r)
        if not (r.ok and v.passed):
            fails.append((c, r.errors + [x.name + ": " + x.detail for x in v.errors]))
            continue
        if i % 6 == 0:                                   # full export bundle for a subset
            out = export_all(r, v, tmp)
            with zipfile.ZipFile(next((out / "Exports").glob("*_print.3mf"))) as z:
                assert "Metadata/Slic3r_PE_model.config" in z.namelist()
            back = Project.load(next(out.glob("*.printyz.json")))
            assert [k.value for k in back.keys] == [k.value for k in p.keys]
    except Exception as e:  # noqa: BLE001
        fails.append((c, [f"EXCEPTION {type(e).__name__}: {e}"]))
print(f"cases {len(CASES)}, fails {len(fails)}, {time.time() - t0:.0f}s")
for c, why in fails:
    print(c, why[:3])
sys.exit(1 if fails else 0)

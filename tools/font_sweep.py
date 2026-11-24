"""Build + validate every approved font at regular / max / min boldness. Developer QA tool."""
import sys
import time

from printyz_clicker.fonts.registry import FontRegistry
from printyz_clicker.geometry.builder import build_project
from printyz_clicker.model.project import Project
from printyz_clicker.text.engine import sync_keys_from_text
from printyz_clicker.validation.checks import validate

reg = FontRegistry.default()
fails, n, t0 = [], 0, time.time()
for fid, e in reg.fonts.items():
    if not e.approved:
        continue
    txt = "שלום אבג" if e.supports_hebrew else "Rg8k@i"
    for ew in (0.0, 0.6, -0.3):
        p = Project()
        sync_keys_from_text(p, txt)
        p.lettering.font_id, p.lettering.extra_weight = fid, ew
        try:
            r = build_project(p, reg, include_switches=False)
            v = validate(r)
        except Exception as ex:  # noqa: BLE001
            fails.append((fid, ew, [f"EXCEPTION {ex}"]))
            continue
        n += 1
        if not (r.ok and v.passed):
            fails.append((fid, ew, [c.detail for c in v.errors][:2]))
print(f"builds {n}, fails {len(fails)}, {time.time() - t0:.0f}s")
for f in fails:
    print(f)
sys.exit(1 if fails else 0)

"""Customer order file (*.printyz-order): what the customer edition produces.

A zip with the project (exact design), preview images, and a readable summary. It contains no
print files; the developer opens it in the developer edition and exports for printing.
"""

from __future__ import annotations

import datetime
import json
import tempfile
import zipfile
from pathlib import Path

from ..model.project import Project

ORDER_EXT = ".printyz-order"


def order_summary(project: Project, policy=None) -> dict:
    name = (lambda h: policy.color_name(h)) if policy else (lambda h: h.upper())
    keys = []
    for k in project.keys:
        keys.append({"kind": k.kind, "value": k.value,
                     "cap": name(project.cap_color(k)), "legend": name(project.legend_color(k))})
    return {
        "created": datetime.datetime.now().isoformat(timespec="minutes"),
        "text": project.text,
        "keys": keys,
        "key_count": len(project.keys),
        "layout": project.layout.style,
        "keycap_style": project.keycap_style,
        "lettering": project.lettering.mode,
        "font": project.lettering.font_id,
        "texture": project.body.texture,
        "keychain": project.keychain.enabled,
        "colors": {"body": name(project.colors.body), "cap": name(project.colors.cap),
                   "legend": name(project.colors.legend)},
    }


def summary_text(s: dict) -> str:
    lines = [f"הזמנת קליקר — {s['created']}", f"טקסט: {s['text']}", f"מספר מקשים: {s['key_count']}",
             f"פריסה: {s['layout']} · כובע: {s['keycap_style']} · כיתוב: {s['lettering']} · טקסטורה: {s['texture']}",
             f"מחזיק מפתחות: {'כן' if s['keychain'] else 'לא'}",
             f"צבעים — גוף: {s['colors']['body']} · כובעים: {s['colors']['cap']} · אותיות: {s['colors']['legend']}"]
    return "\n".join(lines) + "\n"


def write_order(path: Path, project: Project, result=None, policy=None, customer: dict | None = None) -> Path:
    path = Path(path)
    if path.suffix != ORDER_EXT:
        path = path.with_name(path.name + ORDER_EXT)
    summary = order_summary(project, policy)
    if customer:
        summary["customer"] = customer
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.printyz.json", json.dumps(project.to_dict(), ensure_ascii=False, indent=2))
        z.writestr("summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
        z.writestr("summary.txt", summary_text(summary))
        if result is not None and result.ok:
            from ..render.preview import render

            with tempfile.TemporaryDirectory() as td:
                for view in ("iso", "top"):
                    f = Path(td) / f"preview_{view}.png"
                    render(result, f, view, size=(900, 600))
                    z.write(f, f.name)
    return path


def read_order(path: Path) -> tuple[Project, dict]:
    with zipfile.ZipFile(path) as z:
        project = Project.from_dict(json.loads(z.read("project.printyz.json")))
        summary = json.loads(z.read("summary.json")) if "summary.json" in z.namelist() else {}
    return project, summary

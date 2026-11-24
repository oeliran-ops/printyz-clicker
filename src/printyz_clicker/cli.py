"""Command line entry point (the PySide6 UI will call the same functions).

Examples:
  printyz build --text "שלום" --mode flush --out Projects
  printyz build --text Daniel --layout grid --rows 2 --cols 3 --keychain top
  printyz build --project Projects/Shalom/Shalom.printyz.json
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .fonts.registry import FontRegistry
from .geometry.builder import build_project
from .model.project import Project
from .text.engine import insert_extra_key, sync_keys_from_text


def _project_from_args(a) -> Project:
    if a.project:
        p = Project.load(a.project)
        if a.text is not None:
            sync_keys_from_text(p, a.text)
        return p
    p = Project(name=a.name or (a.text or "Untitled"))
    p.layout.style = a.layout
    p.layout.rows, p.layout.cols = a.rows, a.cols
    p.layout.fill_empty_with_blank = a.fill_blank
    p.lettering.mode = a.mode
    p.lettering.extra_weight = a.extra_weight
    p.lettering.size = a.size
    p.lettering.margin = a.margin
    if a.font:
        p.lettering.font_id = a.font
    p.keycap_style = a.keycap
    p.body.joint = a.joint
    if a.keychain:
        p.keychain.enabled = True
        p.keychain.side = a.keychain
    p.colors.body, p.colors.cap, p.colors.legend = a.body_color, a.cap_color, a.legend_color
    res = sync_keys_from_text(p, a.text or "")
    for m in res.messages:
        print("!", m)
    for _ in range(a.extra_blank):
        insert_extra_key(p, len(p.keys))
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="printyz")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build, validate and export a clicker")
    b.add_argument("--text")
    b.add_argument("--project")
    b.add_argument("--name")
    b.add_argument("--layout", default="row", choices=["row", "column", "grid", "wasd", "arrows", "custom"])
    b.add_argument("--rows", type=int, default=2)
    b.add_argument("--cols", type=int, default=3)
    b.add_argument("--fill-blank", action="store_true")
    b.add_argument("--extra-blank", type=int, default=0, help="add N blank keys at the end")
    b.add_argument("--mode", default="flush", choices=["flush", "raised", "engraved"])
    b.add_argument("--font")
    b.add_argument("--size", type=float)
    b.add_argument("--margin", type=float, default=1.25)
    b.add_argument("--extra-weight", type=float, default=0.0)
    b.add_argument("--keycap", default="standard", choices=["standard", "low_profile", "thocky"])
    b.add_argument("--joint", default="grooved", choices=["smooth", "grooved"])
    b.add_argument("--keychain", choices=["top", "bottom", "left", "right"])
    b.add_argument("--body-color", default="#F2F2F2")
    b.add_argument("--cap-color", default="#2B2B2B")
    b.add_argument("--legend-color", default="#FFFFFF")
    b.add_argument("--out", default="Projects")
    b.add_argument("--no-preview", action="store_true")
    a = ap.parse_args(argv)

    from .export.exporter import export_all
    from .validation.checks import validate

    t0 = time.time()
    proj = _project_from_args(a)
    res = build_project(proj, FontRegistry.default())
    report = validate(res)
    if not res.ok:
        print(report.to_markdown())
        return 2
    folder = export_all(res, report, Path(a.out))
    if not a.no_preview:
        from .render.preview import render_set
        render_set(res, folder / "Exports" / "Preview")
    print(report.to_markdown())
    print(f"→ {folder}  ({time.time() - t0:.1f}s)")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())

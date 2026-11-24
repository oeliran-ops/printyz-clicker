"""Export engine: Projects/<name>/Exports with STL, STEP, 3MF, JSON, report."""

from __future__ import annotations

import json
import re
from pathlib import Path

from build123d import Color, Compound, export_step

from ..geometry.builder import BuildResult, part_mesh, print_layout, print_orientation
from ..validation.checks import ValidationReport
from .mesh import write_stl
from .threemf import Object3MF, Volume, write_3mf


def safe_name(name: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return s or "project"


def filament_map(res: BuildResult) -> dict[str, int]:
    """Colour -> extruder (AMS slot) in order body, caps, legends."""
    order: dict[str, int] = {}
    for role in ("body", "cap", "legend"):
        for p in res.parts:
            if p.printable and p.role == role and p.color.upper() not in order:
                order[p.color.upper()] = len(order) + 1
    return order


def export_all(res: BuildResult, report: ValidationReport, root: Path,
               formats: tuple[str, ...] = ("stl", "step", "3mf")) -> Path:
    proj = res.project
    folder = Path(root) / safe_name(proj.name)
    exp = folder / "Exports"
    exp.mkdir(parents=True, exist_ok=True)
    base = safe_name(proj.name)
    proj.save(folder / f"{base}.printyz.json")
    (exp / "validation_report.md").write_text(report.to_markdown(), "utf-8")
    (exp / "validation_report.json").write_text(report.to_json(), "utf-8")

    plate = print_layout(res)
    fmap = filament_map(res)
    meshes = {p.name: part_mesh(p) for p in plate}

    if "stl" in formats:
        stl_dir = exp / "STL"
        stl_dir.mkdir(exist_ok=True)
        for p in plate:
            write_stl(meshes[p.name], stl_dir / f"{base}_{p.name}.stl", p.name)

    if "step" in formats:
        children = []
        for p in res.parts:
            s = p.solid
            s.label = p.name
            s.color = Color(p.color)
            children.append(s)
        export_step(Compound(children=children, label=base), str(exp / f"{base}_assembly.step"))

    if "3mf" in formats:
        objects: dict[str, Object3MF] = {}
        for p in plate:
            obj = objects.setdefault(p.group, Object3MF(f"{base}_{p.group}", []))
            obj.volumes.append(Volume(p.name, meshes[p.name], fmap[p.color.upper()], p.color))
        write_3mf(exp / f"{base}_print.3mf", list(objects.values()), list(fmap.keys()), title=proj.name)

    summary = {
        "project": proj.name,
        "text": proj.text,
        "keys": len(res.layout.keys),
        "layout": proj.layout.style,
        "keycap_style": proj.keycap_style,
        "legend_mode": proj.lettering.mode,
        "print_orientation": print_orientation(res),
        "filaments": [{"slot": i, "color": c} for c, i in fmap.items()],
        "texture": proj.body.texture,
        "step_note": "STEP holds the untextured B-rep body; textures are in STL/3MF" if proj.body.texture != "smooth" else "",
        "validation_passed": report.passed,
    }
    (exp / "export_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
    return folder

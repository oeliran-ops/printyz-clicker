"""Export engine: Projects/<name>/Exports with STL, STEP, 3MF, JSON, report."""

from __future__ import annotations

import json
import re
from pathlib import Path

from build123d import Color, Compound, export_step

from ..geometry.builder import BuildResult, part_mesh, print_layout, print_orientation
from ..validation.checks import ValidationReport
from .mesh import write_stl
from ..config import print_profile
from .bambu3mf import BObject, BPart, write_bambu_3mf
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


def unique_name(root: Path, name: str) -> str:
    """`name` if root/name does not exist yet, else name_2, name_3 ... (never overwrite by accident)."""
    base = safe_name(name)
    if not (Path(root) / base).exists():
        return base
    i = 2
    while (Path(root) / f"{base}_{i}").exists():
        i += 1
    return f"{base}_{i}"


def export_all(res: BuildResult, report: ValidationReport, root: Path,
               formats: tuple[str, ...] = ("stl", "step", "3mf"), settings: dict | None = None,
               name: str | None = None, overwrite: bool = False, plates: int = 2) -> Path:
    """Write the export bundle to root/<name>/. Unless overwrite=True an existing folder is never
    replaced: a free name (name_2, name_3 ...) is used instead."""
    proj = res.project
    base = safe_name(name or proj.name)
    if not overwrite:
        base = unique_name(Path(root), base)
    folder = Path(root) / base
    if overwrite and folder.exists():
        import shutil

        shutil.rmtree(folder / "Exports", ignore_errors=True)     # no stale files from the old export
    exp = folder / "Exports"
    exp.mkdir(parents=True, exist_ok=True)
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
        # Bambu Studio project, per-object print settings. Plates: the user's choice
        #   2 plates (default): plate 1 = body, plate 2 = keycaps
        #   1 plate           : body at the back, keycaps in rows in front, all on plate 1
        bobjs: list[BObject] = []
        cap_groups = [g for g in objects if g != "body"]
        cols = max(1, min(5, len(cap_groups)))
        rows = (len(cap_groups) + cols - 1) // cols
        pitch = res.style.bottom_width + 8.0
        bed_w, bed_h = print_profile.BED_SIZE
        cxp, cyp = bed_w / 2, bed_h / 2
        bx0, by0, bx1, by1 = res.body.outline_bbox
        body_h = (by1 - by0) + (2 * proj.keychain.length if proj.keychain.enabled else 0)
        caps_h = rows * pitch
        gap = 12.0
        one_plate = plates == 1 and (body_h + gap + caps_h) <= bed_h - 16 and max(bx1 - bx0, cols * pitch) <= bed_w - 16
        if plates == 1 and not one_plate:
            report.add("plates / פלטות", "warning", "the model does not fit on one plate - exported on two plates")
        total = body_h + gap + caps_h
        for g, obj in objects.items():
            parts = [BPart(v.name, v.mesh, v.extruder) for v in obj.volumes]
            if g == "body":
                y = cyp + total / 2 - body_h / 2 if one_plate else cyp
                bobjs.append(BObject(obj.name, parts, 1, cxp, y))
            else:
                i = cap_groups.index(g)
                r, c = divmod(i, cols)
                y_caps = (cyp - total / 2 + caps_h / 2) if one_plate else cyp
                bobjs.append(BObject(obj.name, parts, 1 if one_plate else 2, cxp + (c - (cols - 1) / 2) * pitch,
                                     y_caps + ((rows - 1) / 2 - r) * pitch))
        write_bambu_3mf(exp / f"{base}_bambu.3mf", bobjs, settings or print_profile.load(None), title=proj.name,
                        colors=list(fmap.keys()))

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
        "bambu_plates": plates,
        "files": {"_bambu.3mf": "Bambu Studio project: plate 1 body, plate 2 keycaps, print settings per object",
                  "_print.3mf": "generic multi-material 3MF (geometry + colours)"},
        "step_note": "STEP holds the untextured B-rep body; textures are in STL/3MF" if proj.body.texture != "smooth" else "",
        "validation_passed": report.passed,
    }
    (exp / "export_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
    return folder

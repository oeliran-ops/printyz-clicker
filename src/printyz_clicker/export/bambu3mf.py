"""Bambu Studio project 3MF: objects with parts (per-part filament), two plates
(plate 1 = body, plate 2 = keycaps) and per-object print settings.

Format follows Bambu Studio's project layout (3D/3dmodel.model with components pointing to
3D/Objects/*.model, Metadata/model_settings.config with <object>/<part>/<plate>).
The project settings (printer, process preset, filaments) come from a project the user saved
in their own Bambu Studio (assets/bambu/project_settings.config), so the file opens with
exactly their A1 setup. Filament colours are replaced with the project's colours, and the
per-object print settings are written as well (both, like Bambu Studio does).
"""

from __future__ import annotations

import json
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import quoteattr

import numpy as np

from ..config.print_profile import BED_SIZE, PLATE_GAP_RATIO
from .mesh import Mesh

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "assets" / "bambu"


def _template() -> tuple[str, dict]:
    meta = json.loads((TEMPLATE_DIR / "template.json").read_text("utf-8"))
    settings = json.loads((TEMPLATE_DIR / "project_settings.config").read_text("utf-8"))
    return meta["application"], settings


def project_settings_for(colors: list[str], overrides: dict[str, str]) -> dict:
    """The user's saved Bambu project settings with this project's filament colours and print overrides."""
    _, ps = _template()
    ps = json.loads(json.dumps(ps))                      # deep copy
    n_tpl = len(ps["filament_colour"])
    n = max(len(colors), 1)
    if n > n_tpl:
        # more filaments than the template: extend every per-filament list by repeating the last entry
        for k, v in ps.items():
            if isinstance(v, list) and len(v) == n_tpl and (k.startswith("filament") or k in PER_FILAMENT):
                ps[k] = v + [v[-1]] * (n - n_tpl)
    ps["filament_colour"] = [c.upper() for c in colors] + ps["filament_colour"][len(colors):]
    for k, v in overrides.items():                       # keep the per-object values in the project too
        if k in ps:
            ps[k] = [v] if isinstance(ps[k], list) else v
    return ps


# per-filament keys that do not start with "filament"
PER_FILAMENT = {"nozzle_temperature", "nozzle_temperature_initial_layer", "hot_plate_temp", "cool_plate_temp",
                "eng_plate_temp", "textured_plate_temp", "hot_plate_temp_initial_layer",
                "cool_plate_temp_initial_layer", "eng_plate_temp_initial_layer",
                "textured_plate_temp_initial_layer", "fan_max_speed", "fan_min_speed", "default_filament_colour",
                "temperature_vitrification", "required_nozzle_HRC", "slow_down_layer_time", "slow_down_min_speed"}

APP, _ = _template()
NS = ('xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
      'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
      'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p"')
IDENTITY = "1 0 0 0 1 0 0 0 1 0 0 0"

# Bambu Studio's deterministic UUID scheme (as written by Bambu Studio 2.9 itself). Random UUIDs make
# Bambu treat the file as coming from an old version and load geometry only.
OBJECT_SUFFIX = "-61cb-4c03-9d28-80fed5dfa1dc"
SUB_OBJECT_SUFFIX = "-81cb-4c03-9d28-80fed5dfa1dc"
COMPONENT_SUFFIX = "-b206-40ff-9872-83e8017abed1"
BUILD_ITEM_SUFFIX = "-b1ec-4553-aec9-835e5b724bb4"
BUILD_UUID = "2c7c17d8-22b5-4d84-8835-1976022ea369"


def _today() -> str:
    import datetime

    return datetime.date.today().isoformat()


def _uid(n: int, suffix: str) -> str:
    return f"{n:08x}{suffix}"


@dataclass
class BPart:
    name: str
    mesh: Mesh
    extruder: int


@dataclass
class BObject:
    name: str
    parts: list[BPart]
    plate: int            # 1-based
    x: float              # centre position on its plate (mm, plate-local)
    y: float


def _f(a: float) -> str:
    s = f"{a:.5f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def plate_origin(plate: int) -> tuple[float, float]:
    """Bambu lays plates out left-to-right in a grid; 2 plates -> one row."""
    stride = BED_SIZE[0] * (1 + PLATE_GAP_RATIO)
    return (plate - 1) * stride, 0.0


def write_bambu_3mf(path, objects: list[BObject], settings: dict[str, str], title: str = "PRINTYZ",
                    colors: list[str] | None = None) -> None:
    files: dict[str, str] = {}
    rels = []
    root_objs, build_items, cfg = [], [], ['<?xml version="1.0" encoding="UTF-8"?>', "<config>"]
    plates: dict[int, list[tuple[int, int]]] = {}
    assemble: list[tuple[int, float, float]] = []
    next_id = 1
    identify = 100
    for oi, obj in enumerate(objects, start=1):
        sub = f"/3D/Objects/object_{oi}.model"
        sub_lines = ['<?xml version="1.0" encoding="UTF-8"?>', f"<model unit=\"millimeter\" xml:lang=\"en-US\" {NS}>",
                     ' <metadata name="BambuStudio:3mfVersion">1</metadata>', " <resources>"]
        comps, part_ids = [], []
        # centre the object's parts on its own origin (XY) and keep z >= 0
        allv = np.vstack([p.mesh.vertices for p in obj.parts])
        cx, cy = (allv[:, 0].min() + allv[:, 0].max()) / 2, (allv[:, 1].min() + allv[:, 1].max()) / 2
        zmin = allv[:, 2].min()
        for part in obj.parts:
            pid = next_id
            next_id += 1
            part_ids.append(pid)
            v = part.mesh.vertices - (cx, cy, zmin)
            sub_lines.append(f'  <object id="{pid}" p:UUID="{_uid((oi << 16) | (len(part_ids) - 1), SUB_OBJECT_SUFFIX)}" '
                             'type="model">')
            sub_lines.append("   <mesh>\n    <vertices>")
            sub_lines.extend(f'     <vertex x="{_f(x)}" y="{_f(y)}" z="{_f(z)}"/>' for x, y, z in v)
            sub_lines.append("    </vertices>\n    <triangles>")
            sub_lines.extend(f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in part.mesh.faces)
            sub_lines.append("    </triangles>\n   </mesh>\n  </object>")
            comps.append(f'    <component p:path="{sub}" objectid="{pid}" '
                         f'p:UUID="{_uid((oi << 16) | (len(part_ids) - 1), COMPONENT_SUFFIX)}" transform="{IDENTITY}"/>')
        sub_lines.append(" </resources>\n <build/>\n</model>")
        files[sub.lstrip("/")] = "\n".join(sub_lines)
        rels.append(sub)

        oid = next_id
        next_id += 1
        root_objs.append(f'  <object id="{oid}" p:UUID="{_uid(oi, OBJECT_SUFFIX)}" type="model">\n   <components>\n'
                         + "\n".join(comps) + "\n   </components>\n  </object>")
        ox, oy = plate_origin(obj.plate)
        tx, ty = ox + obj.x, oy + obj.y
        build_items.append(f'  <item objectid="{oid}" p:UUID="{_uid(oid, BUILD_ITEM_SUFFIX)}" '
                           f'transform="1 0 0 0 1 0 0 0 1 {_f(tx)} {_f(ty)} 0" printable="1"/>')
        plates.setdefault(obj.plate, []).append((oid, identify))
        assemble.append((oid, tx, ty))
        identify += 1

        cfg.append(f' <object id="{oid}">')
        cfg.append(f'  <metadata key="name" value={quoteattr(obj.name)}/>')
        cfg.append(f'  <metadata key="extruder" value="{obj.parts[0].extruder}"/>')
        for k, val in sorted(settings.items()):
            cfg.append(f'  <metadata key="{k}" value={quoteattr(str(val))}/>')
        cfg.append(f'  <metadata face_count="{sum(len(p.mesh.faces) for p in obj.parts)}"/>')
        for pid, part in zip(part_ids, obj.parts):
            cfg.append(f'  <part id="{pid}" subtype="normal_part" uuid="{uuid.uuid4()}">')
            cfg.append(f'   <metadata key="name" value={quoteattr(part.name)}/>')
            cfg.append('   <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>')
            cfg.append(f'   <metadata key="extruder" value="{part.extruder}"/>')
            cfg.append(f'   <mesh_stat face_count="{len(part.mesh.faces)}" edges_fixed="0" degenerate_facets="0" '
                       'facets_removed="0" facets_reversed="0" backwards_edges="0"/>')
            cfg.append("  </part>")
        cfg.append(" </object>")

    names = {1: "Body / גוף", 2: "Keycaps / כובעים"}
    for plate in sorted(plates):
        cfg.append(" <plate>")
        cfg.append(f'  <metadata key="plater_id" value="{plate}"/>')
        cfg.append(f'  <metadata key="plater_name" value={quoteattr(names.get(plate, ""))}/>')
        cfg.append('  <metadata key="locked" value="false"/>')
        cfg.append('  <metadata key="filament_map_mode" value="Auto For Flush"/>')
        for oid, ident in plates[plate]:
            cfg.append("  <model_instance>")
            cfg.append(f'   <metadata key="object_id" value="{oid}"/>')
            cfg.append('   <metadata key="instance_id" value="0"/>')
            cfg.append(f'   <metadata key="identify_id" value="{ident}"/>')
            cfg.append("  </model_instance>")
        cfg.append(" </plate>")
    cfg.append(" <assemble>")
    for (oid, tx, ty) in assemble:
        cfg.append(f'  <assemble_item object_id="{oid}" instance_id="0" '
                   f'transform="1 0 0 0 1 0 0 0 1 {_f(tx)} {_f(ty)} 0" offset="0 0 0" />')
    cfg.append(" </assemble>")
    cfg.append("</config>")

    cut_info = ['<?xml version="1.0" encoding="utf-8"?>', "<objects>"]
    for i in range(1, len(objects) + 1):
        cut_info += [f' <object id="{i}">', '  <cut_id id="0" check_sum="1" connectors_cnt="0"/>', " </object>"]
    cut_info.append("</objects>")

    model = ['<?xml version="1.0" encoding="UTF-8"?>', f'<model unit="millimeter" xml:lang="en-US" {NS}>',
             f' <metadata name="Application">{APP}</metadata>',
             ' <metadata name="BambuStudio:3mfVersion">1</metadata>',
             ' <metadata name="Copyright"></metadata>',
             f' <metadata name="CreationDate">{_today()}</metadata>',
             ' <metadata name="Description"></metadata>',
             ' <metadata name="Designer"></metadata>',
             ' <metadata name="DesignerCover"></metadata>',
             ' <metadata name="DesignerUserId"></metadata>',
             ' <metadata name="License"></metadata>',
             f' <metadata name="ModificationDate">{_today()}</metadata>',
             ' <metadata name="Origin"></metadata>',
             ' <metadata name="ProfileCover"></metadata>',
             ' <metadata name="ProfileDescription"></metadata>',
             ' <metadata name="ProfileTitle"></metadata>',
             f' <metadata name="Title">{title}</metadata>',
             " <resources>", *root_objs, " </resources>",
             f' <build p:UUID="{BUILD_UUID}">', *build_items, " </build>", "</model>"]

    content_types = ('<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/'
                     'package/2006/content-types">\n <Default Extension="rels" ContentType="application/'
                     'vnd.openxmlformats-package.relationships+xml"/>\n <Default Extension="model" ContentType='
                     '"application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n <Default Extension="config" '
                     'ContentType="text/xml"/>\n</Types>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/'
                 'package/2006/relationships">\n <Relationship Target="/3D/3dmodel.model" Id="rel-1" '
                 'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n</Relationships>')
    model_rels = ['<?xml version="1.0" encoding="UTF-8"?>',
                  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    model_rels += [f' <Relationship Target="{r}" Id="rel-{i}" '
                   f'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
                   for i, r in enumerate(rels, start=1)]
    model_rels.append("</Relationships>")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("3D/3dmodel.model", "\n".join(model))
        z.writestr("3D/_rels/3dmodel.model.rels", "\n".join(model_rels))
        for name, text in files.items():
            z.writestr(name, text)
        z.writestr("Metadata/model_settings.config", "\n".join(cfg))
        z.writestr("Metadata/cut_information.xml", "\n".join(cut_info))
        ps = project_settings_for(colors or [], settings)
        z.writestr("Metadata/project_settings.config", json.dumps(ps, indent=4, ensure_ascii=False))
        ver = APP.split("-", 1)[1]
        z.writestr("Metadata/slice_info.config",
                   '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <header>\n'
                   '    <header_item key="X-BBL-Client-Type" value="slicer"/>\n'
                   f'    <header_item key="X-BBL-Client-Version" value="{ver}"/>\n  </header>\n</config>\n')
        z.writestr("Metadata/filament_sequence.json",
                   json.dumps({f"plate_{p}": {"nozzle_sequence": [], "optimal_assignment": [], "sequence": []}
                               for p in sorted(plates)}))

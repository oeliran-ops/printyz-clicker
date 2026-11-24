"""3MF writer aimed at Bambu Studio multi-material workflow.

Each printed object (body, each keycap) is ONE 3MF object. A keycap with a flush
or raised legend contains two volumes (cap + legend) stored as triangle ranges and
described in Metadata/Slic3r_PE_model.config with a per-volume extruder number -
the PrusaSlicer project convention, which Bambu Studio imports as an object with
parts. Extruder numbers map 1:1 to AMS slots (see the export report).

VERIFY: Bambu-Studio import of this file must be confirmed on the target machine.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from xml.sax.saxutils import escape, quoteattr

import numpy as np

from .mesh import Mesh

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="config" ContentType="text/xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""


@dataclass
class Volume:
    name: str
    mesh: Mesh
    extruder: int
    color: str


@dataclass
class Object3MF:
    name: str
    volumes: list[Volume]


def _fmt(a: float) -> str:
    s = f"{a:.5f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def write_3mf(path, objects: list[Object3MF], filament_colors: list[str], title: str = "PRINTYZ") -> None:
    model = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
        'xmlns:slic3rpe="http://schemas.slic3r.org/3mf/2017/06">',
        f' <metadata name="Title">{escape(title)}</metadata>',
        ' <metadata name="Application">PRINTYZ Clicker Studio</metadata>',
        ' <metadata name="slic3rpe:Version3mf">1</metadata>',
        ' <resources>',
        '  <basematerials id="1">',
    ]
    for i, c in enumerate(filament_colors):
        model.append(f'   <base name="Filament {i+1}" displaycolor="{c.upper()}FF"/>')
    model.append('  </basematerials>')
    cfg = ['<?xml version="1.0" encoding="UTF-8"?>', "<config>"]
    build_items = []
    for oid, obj in enumerate(objects, start=2):
        verts, tris, ranges, pindex = [], [], [], []
        voff = 0
        toff = 0
        for vol in obj.volumes:
            verts.append(vol.mesh.vertices)
            tris.append(vol.mesh.faces + voff)
            ranges.append((toff, toff + len(vol.mesh.faces) - 1, vol))
            pindex.append(np.full(len(vol.mesh.faces), vol.extruder - 1))
            voff += len(vol.mesh.vertices)
            toff += len(vol.mesh.faces)
        V = np.vstack(verts)
        T = np.vstack(tris)
        P = np.concatenate(pindex)
        first = obj.volumes[0].extruder - 1
        model.append(f'  <object id="{oid}" name={quoteattr(obj.name)} type="model" pid="1" pindex="{first}">')
        model.append('   <mesh>\n    <vertices>')
        model.extend(f'     <vertex x="{_fmt(x)}" y="{_fmt(y)}" z="{_fmt(z)}"/>' for x, y, z in V)
        model.append('    </vertices>\n    <triangles>')
        model.extend(
            f'     <triangle v1="{a}" v2="{b}" v3="{c}"' + (f' pid="1" p1="{p}"' if p != first else "") + "/>"
            for (a, b, c), p in zip(T, P)
        )
        model.append('    </triangles>\n   </mesh>\n  </object>')
        build_items.append(f'  <item objectid="{oid}" printable="1"/>')

        cfg.append(f' <object id="{oid}" instances_count="1">')
        cfg.append(f'  <metadata type="object" key="name" value={quoteattr(obj.name)}/>')
        cfg.append(f'  <metadata type="object" key="extruder" value="{obj.volumes[0].extruder}"/>')
        for a, b, vol in ranges:
            cfg.append(f'  <volume firstid="{a}" lastid="{b}">')
            cfg.append(f'   <metadata type="volume" key="name" value={quoteattr(vol.name)}/>')
            cfg.append('   <metadata type="volume" key="volume_type" value="ModelPart"/>')
            cfg.append(f'   <metadata type="volume" key="extruder" value="{vol.extruder}"/>')
            cfg.append('  </volume>')
        cfg.append(' </object>')
    model.append(' </resources>\n <build>')
    model.extend(build_items)
    model.append(' </build>\n</model>')
    cfg.append("</config>")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", "\n".join(model))
        z.writestr("Metadata/Slic3r_PE_model.config", "\n".join(cfg))

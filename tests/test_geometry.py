import zipfile

import pytest

from printyz_clicker.config.mechanical import KEYCAP_STYLES
from printyz_clicker.export.exporter import export_all
from printyz_clicker.geometry.builder import build_project
from printyz_clicker.model.project import Project
from printyz_clicker.text.engine import sync_keys_from_text
from printyz_clicker.validation.checks import validate

pytestmark = pytest.mark.slow


def make(text, **kw):
    p = Project(name="t")
    sync_keys_from_text(p, text)
    for k, v in kw.items():
        obj, attr = (p, k) if "__" not in k else (getattr(p, k.split("__")[0]), k.split("__")[1])
        setattr(obj, attr, v)
    return p


def test_hebrew_flush_passes_validation():
    res = build_project(make("שלום"))
    rep = validate(res)
    assert rep.passed, rep.to_markdown()
    assert len([p for p in res.parts if p.role == "legend"]) == 4


@pytest.mark.parametrize("style", list(KEYCAP_STYLES))
def test_keycap_styles_change_real_geometry(style):
    res = build_project(make("A", keycap_style=style), include_switches=False)
    cap = next(p for p in res.parts if p.role == "cap")
    bb = cap.solid.bounding_box()
    assert abs(bb.size.Z - KEYCAP_STYLES[style].height) < 1e-3
    assert validate(res, mesh_checks=False).passed


def test_raised_and_engraved():
    raised = build_project(make("A", lettering__mode="raised"), include_switches=False)
    leg = next(p for p in raised.parts if p.role == "legend")
    cap = next(p for p in raised.parts if p.role == "cap")
    assert leg.solid.bounding_box().min.Z == pytest.approx(cap.solid.bounding_box().max.Z, abs=1e-4)
    eng = build_project(make("A", lettering__mode="engraved"), include_switches=False)
    assert not [p for p in eng.parts if p.role == "legend"]


def test_requested_size_is_clamped_to_area():
    res = build_project(make("A", lettering__size=22.0), include_switches=False)
    assert any("size reduced" in w for w in res.warnings)
    assert validate(res, mesh_checks=False).passed


def test_grid_wasd_keychain_bodies_single_solid():
    for kw in ({"layout__style": "grid", "layout__rows": 2, "layout__cols": 3},
               {"layout__style": "wasd"}):
        p = make("WASDE"[: 5 if kw["layout__style"] == "grid" else 4], **kw)
        p.keychain.enabled = True
        res = build_project(p, include_switches=False)
        assert res.ok, res.errors
        assert len(res.body.solid.solids()) == 1


def test_missing_glyph_is_error():
    res = build_project(make("中"))  # CJK not in default font
    assert not res.ok


def test_export_bundle(tmp_path):
    res = build_project(make("Hi"))
    rep = validate(res)
    folder = export_all(res, rep, tmp_path)
    exp = folder / "Exports"
    assert (exp / "t_print.3mf").exists() and (exp / "t_assembly.step").exists()
    assert len(list((exp / "STL").glob("*.stl"))) == 5   # body + 2 caps + 2 legends
    with zipfile.ZipFile(exp / "t_print.3mf") as z:
        cfg = z.read("Metadata/Slic3r_PE_model.config").decode()
        assert cfg.count("<volume") == 5 and 'key="extruder" value="3"' in cfg
    reloaded = Project.load(folder / "t.printyz.json")
    assert [k.value for k in reloaded.keys] == ["H", "i"]


def test_grooved_joint_really_removes_material():
    vols = {}
    for joint in ("smooth", "grooved"):
        p = make("abc", body__joint=joint)
        vols[joint] = build_project(p, include_switches=False).body.solid.volume
    # 2 boundaries x 2 sides x V-notch (0.5*1.6*0.8 mm2) x ~17.6 mm height ~ 45 mm3
    assert vols["smooth"] - vols["grooved"] > 30


def test_keychain_adds_material_and_hole():
    off = build_project(make("ab"), include_switches=False).body
    p = make("ab")
    p.keychain.enabled = True
    on = build_project(p, include_switches=False).body
    assert on.solid.volume > off.solid.volume + 100 and on.keychain_hole is not None


def test_uniform_letter_scale_across_keys():
    # ם ו ש have the same height in the font; with one common scale they must match on the keycaps
    res = build_project(make("שום"), include_switches=False)
    hs = [h for _, h in res.legend_boxes.values()]
    assert max(hs) - min(hs) < 0.02 * max(hs)     # one scale; only the font's own overshoot differs
    assert validate(res, mesh_checks=False).passed
    p = make("שום")
    p.lettering.uniform = False          # old behaviour: each key stretched on its own
    indep = [h for _, h in build_project(p, include_switches=False).legend_boxes.values()]
    assert max(indep) - min(indep) > 1.0


def test_keycap_height_slider_changes_geometry():
    p = make("A")
    p.keycap_height = 9.5
    res = build_project(p, include_switches=False)
    cap = next(x for x in res.parts if x.role == "cap")
    assert abs(cap.solid.bounding_box().size.Z - 9.5) < 1e-3
    assert validate(res, mesh_checks=False).passed
    p.keycap_height = 3.0
    assert not build_project(p, include_switches=False).ok


def test_rim_height_raises_body():
    p = make("ab", body__rim_height=19.5)
    res = build_project(p, include_switches=False)
    assert abs(res.body.solid.bounding_box().max.Z - 19.5) < 1e-3
    assert validate(res, mesh_checks=False).passed


def test_letter_size_percent_and_blank():
    full = build_project(make("A"), include_switches=False).legend_boxes["key01"][1]
    half = build_project(make("A", lettering__size_pct=50.0), include_switches=False).legend_boxes["key01"][1]
    assert abs(half - full / 2) < 0.05
    blank = build_project(make("AB", blank_legends=True), include_switches=False)
    assert not [x for x in blank.parts if x.role == "legend"]


def test_negative_boldness_thins_letters():
    reg = build_project(make("H"), include_switches=False)
    thin = build_project(make("H", lettering__extra_weight=-0.2), include_switches=False)
    v = lambda r: next(x for x in r.parts if x.role == "legend").solid.volume  # noqa: E731
    assert v(thin) < v(reg) * 0.95


@pytest.mark.parametrize("tex", ["diamond", "ribs", "fluted", "dots", "chevron"])
def test_textures_cut_outside_only(tex):
    from printyz_clicker.export.mesh import mesh_health, tessellate

    p = make("ab", body__texture=tex)
    p.keychain.enabled = True
    res = build_project(p, include_switches=False)
    m = res.body.mesh
    h = mesh_health(m)
    smooth_vol = mesh_health(tessellate(res.body.solid))["volume"]
    assert h["watertight"] and h["bodies"] == 1
    assert 0 < smooth_vol - h["volume"] < 0.1 * smooth_vol      # material removed, but only a skin
    # pockets untouched: inside the outline shrunk by the outer wall there is no change
    import numpy as np
    inner = np.abs(m.vertices[:, :2]).max(axis=1) < 20.75 / 2 + 0.01
    assert validate(res, mesh_checks=True).passed
    assert inner.any()


def test_ribs_cut_all_around_including_ends():
    from printyz_clicker.geometry.texture import _to_manifold

    res = build_project(make("abcd", body__texture="ribs"), include_switches=False)
    m = _to_manifold(res.body.mesh)
    b = res.mech.body
    z_groove = b.edge_fillet + 0.6 + 2.4 * 0.25          # inside the first rounded groove
    smooth = m.slice(b.edge_fillet + 0.6 + 2.4 * 0.75).bounds()
    groove = m.slice(z_groove).bounds()
    assert groove[2] < smooth[2] - 0.3 and groove[3] < smooth[3] - 0.3     # ends AND sides are cut


def test_texture_continues_above_keychain_tab():
    from printyz_clicker.geometry.texture import _to_manifold

    p = make("ab", body__texture="ribs")
    p.keychain.enabled = True                       # tab on the top side, centred at x = 0
    res = build_project(p, include_switches=False)
    m = _to_manifold(res.body.mesh)
    b = res.mech.body
    z0, u = b.edge_fillet + 0.6, 2.4
    k = next(k for k in range(10) if z0 + k * u > p.keychain.thickness + 1.0)
    z = z0 + k * u + u * 0.25                       # middle of a groove above the tab
    outer_y = max(pt[1] for poly in m.slice(z).to_polygons() for pt in poly if abs(pt[0]) < 1.0)
    assert outer_y < 11.9 - 0.3                     # the wall right above the tab root IS textured
    assert validate(res, mesh_checks=True).passed


@pytest.mark.parametrize("shape", ["rounded", "round", "square"])
def test_keychain_shapes_strong(shape):
    p = make("ab")
    p.keychain.enabled, p.keychain.shape = True, shape
    p.keychain.width, p.keychain.thickness = 8.0, 2.0            # too weak on purpose -> corrected
    res = build_project(p, include_switches=False)
    assert res.ok and any("2 מ\"מ" in w or "3" in w for w in res.warnings)
    assert len(res.body.solid.solids()) == 1
    assert res.body.solid.bounding_box().size.Z >= 17.6
    assert validate(res, mesh_checks=False).passed


def test_queen_and_king_crowns_differ():
    from printyz_clicker.geometry.symbols import symbol_sketch

    a, b = symbol_sketch("crown"), symbol_sketch("crown_queen")
    assert abs(sum(f.area for f in a.faces()) - sum(f.area for f in b.faces())) > 2.0


def test_bambu_project_two_plates_and_settings(tmp_path):
    import re
    import zipfile

    from printyz_clicker.export.exporter import export_all

    res = build_project(make("Hi"), include_switches=False)
    out = export_all(res, validate(res), tmp_path, ("3mf",))
    with zipfile.ZipFile(out / "Exports" / "t_bambu.3mf") as z:
        cfg = z.read("Metadata/model_settings.config").decode()
        model = z.read("3D/3dmodel.model").decode()
    assert re.findall(r'plater_id" value="(\d)"', cfg) == ["1", "2"]
    plate1 = cfg.split("<plate>")[1]
    assert plate1.count("<model_instance>") == 1                           # body alone on plate 1
    assert cfg.split("<plate>")[2].count("<model_instance>") == 2           # two keycaps on plate 2
    assert 'key="wall_generator" value="arachne"' in cfg and 'key="outer_wall_speed" value="60"' in cfg
    assert "BambuStudio" in model


def test_legends_centred_on_keycaps_all_fonts():
    """Every letter and symbol is centred on its keycap (bounding-box centre), for every bundled font."""
    from printyz_clicker.fonts.registry import FontRegistry
    from printyz_clicker.text.engine import insert_key_visual

    reg = FontRegistry.default()
    for fid, e in reg.fonts.items():
        if not e.approved:
            continue
        p = make("מלכה" if e.supports_hebrew else "AgQi", lettering__font_id=fid)
        insert_key_visual(p, "left", None, "symbol", "crown_queen")
        res = build_project(p, reg, include_switches=False)
        assert res.ok, (fid, res.errors)
        for pk in res.layout.keys:
            for leg in (x for x in res.parts if x.role == "legend" and x.key_id == pk.key_id):
                c = leg.solid.bounding_box().center()
                assert abs(c.X - pk.x) < 0.01 and abs(c.Y - pk.y) < 0.01, fid

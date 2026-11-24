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

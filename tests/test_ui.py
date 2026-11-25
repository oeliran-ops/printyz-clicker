"""UI smoke test: real window, real build, real viewer. Needs a display (xvfb-run on Linux)."""

import os
import sys

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtWidgets import QApplication  # noqa: E402

from printyz_clicker.ui.i18n import set_language  # noqa: E402
from printyz_clicker.ui.main_window import MainWindow  # noqa: E402

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_window_builds_and_tracks_edits(app):
    set_language("he")
    w = MainWindow()
    w.show()
    w.ctl.wait_idle()
    assert w.ctl.result is not None and w.ctl.result.ok
    assert len(w.viewer._meshes) > 0
    # typing a new name rebuilds with the new key count (single source of truth)
    w.pages[0][1].name.setText("Daniel")
    w.ctl.wait_idle()
    assert len(w.ctl.result.layout.keys) == 6
    caps = [p for p in w.ctl.result.parts if p.role == "cap"]
    assert len(caps) == 6
    # keycap style change reaches the geometry
    w.ctl.project.keycap_style = "low_profile"
    w.ctl.touch()
    w.ctl.wait_idle()
    cap = next(p for p in w.ctl.result.parts if p.role == "cap")
    assert abs(cap.solid.bounding_box().size.Z - 8.0) < 1e-3
    # over the limit -> error shown, nothing silently truncated
    w.pages[0][1].name.setText("abcdefghijkl")
    w.ctl.wait_idle()
    assert not w.ctl.result.ok and len(w.ctl.project.keys) == 12
    # customer mode hides the mechanical page
    w.mode.setCurrentIndex(1)
    hidden = [w.nav.item(i).isHidden() for i in range(w.nav.count())]
    assert any(hidden)
    w.close()


def test_undo_redo(app):
    set_language("he")
    w = MainWindow()
    w.ctl.wait_idle()
    w.ctl._hist_timer.setInterval(1)
    first = w.ctl.project.text
    w.pages[0][1].name.setText("Dan")
    w.ctl._commit_history()
    w.ctl.project.body.texture = "ribs"
    w.ctl.touch()
    w.ctl._commit_history()
    w.ctl.undo()
    assert w.ctl.project.body.texture == "smooth" and w.ctl.project.text == "Dan"
    w.ctl.undo()
    assert w.ctl.project.text == first
    w.ctl.redo()
    w.ctl.redo()
    assert w.ctl.project.body.texture == "ribs"
    w.ctl.wait_idle()
    assert w.ctl.result.ok and w.ctl.result.body.mesh is not None   # texture really in the geometry
    assert w.pages[0][1].name.text() == "Dan"                          # UI follows the restored project
    w.close()


def test_texture_card_updates_viewer(app):
    """Regression: choosing a texture card must change what the 3D view shows."""
    set_language("he")
    w = MainWindow()
    w.show()
    w.ctl.wait_idle()
    body_before = w.viewer._meshes["body"][0].n_cells
    body_page = next(p for _, p, _ in w.pages if p.__class__.__name__ == "BodyPage")
    body_page.cards["dots"].clicked.emit("dots")
    w.ctl.wait_idle()
    app.processEvents()
    assert w.ctl.project.body.texture == "dots"
    assert w.viewer._meshes["body"][0].n_cells > body_before * 2      # textured mesh is on screen
    w.close()


def test_symbols_page_and_blank_sides(app):
    set_language("he")
    w = MainWindow()
    w.show()
    w.ctl.wait_idle()
    sp = next(p for _, p, _ in w.pages if p.__class__.__name__ == "SymbolsPage")
    w.nav.setCurrentRow(next(i for i, (_, p, _) in enumerate(w.pages) if p is sp))
    app.processEvents()
    sp._pick(("symbol", "crown"))
    sp._new("left")
    w.ctl.wait_idle()
    assert any(k.kind == "symbol" and k.value == "crown" for k in w.ctl.project.keys)
    assert w.ctl.result.ok and "key01" in w.ctl.result.legend_boxes
    w.close()


def test_symbol_apply_any_order_and_customer_library(app, tmp_path):
    from printyz_clicker.geometry.symbols import SymbolLibrary

    set_language("he")
    w = MainWindow()
    w.show()
    w.ctl.wait_idle()
    sp = next(p for _, p, _ in w.pages if p.__class__.__name__ == "SymbolsPage")
    sp.library = SymbolLibrary(tmp_path / "s.json")
    w.nav.setCurrentRow(next(i for i, (_, p, _) in enumerate(w.pages) if p is sp))
    app.processEvents()
    key = w.ctl.project.keys[0]
    sp.click_symbol("crown_queen")             # symbol first ...
    sp.strip._pick(key.id)                     # ... then the key
    assert sp.apply_btn.isEnabled()
    sp.apply_btn.click()
    w.ctl.wait_idle()
    assert w.ctl.project.key_by_id(key.id).value == "crown_queen" and w.ctl.result.ok
    # developer hides a symbol -> customer mode does not offer it
    sp.library.set_visible("cat", False)
    w.mode.setCurrentIndex(1)
    app.processEvents()
    sp._rebuild_grid()
    assert "cat" not in sp.buttons and "heart" in sp.buttons
    w.close()


def test_export_save_as_name_and_no_silent_overwrite(app, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    set_language("he")
    w = MainWindow()
    w.ctl.wait_idle()
    w.export_page.fmt["step"].setChecked(False)
    w.export_page.previews.setChecked(False)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    target = tmp_path / "orders"
    target.mkdir()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target / "Dana gift"), ""))
    w.export_ask_folder()
    first = target / "Dana gift" / "Exports"
    assert list(first.glob("*_bambu.3mf"))                                # saved under the chosen name
    assert QSettings("PRINTYZ", "Clicker Studio").value("export_folder") == str(target)
    stamp = next(first.glob("*_print.3mf")).stat().st_mtime_ns
    # same name again: the dialog asks; choosing "save as new" keeps the old export untouched
    def choose_keep(self):
        self.setProperty("_x", 1)
        self.clickedButton = lambda: self.buttons()[0]
        return 0
    monkeypatch.setattr(QMessageBox, "exec", choose_keep)
    w.export_ask_folder()
    assert next(first.glob("*_print.3mf")).stat().st_mtime_ns == stamp    # old files not replaced
    assert list((target / "Dana gift_2" / "Exports").glob("*_print.3mf"))
    # cancelling writes nothing
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    w.export_ask_folder()
    assert sorted(p.name for p in target.iterdir()) == ["Dana gift", "Dana gift_2"]
    w.close()

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

"""Main window: icon rail + settings panel + live 3D viewer (spec 30-36)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QSize, QStandardPaths, Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QStackedWidget, QStatusBar,
    QVBoxLayout, QWidget,
)

from ..export.exporter import export_all
from ..fonts.registry import FontRegistry
from ..model.project import Project
from ..validation.checks import ERROR, WARN, validate
from .controller import ProjectController
from .i18n import is_rtl, language, tr
from .icons import icon
from .pages import (
    BodyPage, ColorsPage, ExportPage, FontPage, KeycapPage, KeychainPage, LetteringPage, MechanicalPage,
    NamePage,
)
from .viewer import Viewer3D
from .widgets import Page, Segmented


def data_dir() -> Path:
    d = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or Path.home() / ".printyz")
    d.mkdir(parents=True, exist_ok=True)
    return d


class PlaceholderPage(Page):
    """Spec rule 23: features not yet in the geometry are shown as unavailable, never as active."""

    def __init__(self, title: str, text: str):
        super().__init__(title)
        self.hint(text, "Warn")
        self.finish()


class MainWindow(QMainWindow):
    def __init__(self, fonts: FontRegistry | None = None, project: Project | None = None, on_language=None):
        super().__init__()
        self.setWindowTitle("PRINTYZ Clicker Studio")
        self.resize(1480, 900)
        self.setLayoutDirection(Qt.RightToLeft if is_rtl() else Qt.LeftToRight)
        self.on_language = on_language
        self.font_lib = data_dir() / "fonts.json"
        self.fonts = fonts or FontRegistry.default(self.font_lib)
        self.ctl = ProjectController(self.fonts, project)
        self.project_path: Path | None = None

        central = QWidget()
        central.setObjectName("Central")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._top_bar())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root.addLayout(body, 1)
        self.setCentralWidget(central)

        # --- icon rail + pages ----------------------------------------------------------
        self.nav = QListWidget()
        self.nav.setObjectName("NavList")
        self.nav.setViewMode(QListWidget.IconMode)
        self.nav.setMovement(QListWidget.Static)
        self.nav.setFlow(QListWidget.TopToBottom)
        self.nav.setIconSize(QSize(24, 24))
        self.nav.setFixedWidth(108)
        self.nav.setGridSize(QSize(98, 64))
        self.nav.setSpacing(0)
        self.nav.setWordWrap(True)
        self.stack = QStackedWidget()
        self.stack.setFixedWidth(400)
        self.stack.setObjectName("SidePanel")
        self.pages: list[tuple[str, QWidget, bool]] = []
        self._add_page("name", tr("שם ופריסה", "Name"), NamePage(self.ctl))
        self._add_page("font", tr("גופנים", "Fonts"), FontPage(self.ctl, self._save_fonts))
        self._add_page("legend", tr("כיתוב", "Lettering"), LetteringPage(self.ctl))
        self._add_page("keycap", tr("מקשים", "Keycaps"), KeycapPage(self.ctl))
        self._add_page("body", tr("גוף", "Body"), BodyPage(self.ctl))
        self._add_page("palette", tr("צבעים", "Colours"), ColorsPage(self.ctl))
        self._add_page("symbol", tr("סמלים", "Symbols"), PlaceholderPage(
            tr("סמלים ו־SVG", "Symbols & SVG"),
            tr("ספריית סמלים וייבוא SVG עדיין לא ממומשים בגיאומטריה. בינתיים אפשר להשאיר מקש ריק "
               "ולהוסיף SVG ב־Bambu Studio.",
               "Symbols / SVG are not implemented yet. Use a blank key and add the SVG in Bambu Studio.")))
        self._add_page("keychain", tr("מחזיק", "Keychain"), KeychainPage(self.ctl))
        self._add_page("mech", tr("מכאני", "Fit"), MechanicalPage(self.ctl), dev_only=True)
        self.export_page = ExportPage(self.ctl, self.export)
        self._add_page("export", tr("ייצוא", "Export"), self.export_page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        side = QWidget()
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(0, 0, 0, 0)
        side_l.setSpacing(0)
        side_l.addWidget(self.stack, 1)
        side_l.addWidget(self._action_bar())
        side.setFixedWidth(400)
        body.addWidget(self.nav)
        body.addWidget(side)
        body.addWidget(self._viewer_area(), 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status_label = QLabel()
        self.status.addWidget(self.status_label, 1)

        self.ctl.building.connect(lambda: self._set_overlay(tr("מחשב גיאומטריה…", "Building geometry…"), "Hint"))
        self.ctl.built.connect(self._on_built)
        self.ctl.build_failed.connect(self._on_failed)
        self.ctl.changed.connect(self._update_title)
        self._apply_mode()
        if not self.ctl.project.text:
            self.ctl.set_text("PRINTYZ" if language() == "en" else "שלום")
        else:
            self.ctl.touch()

    # ---- layout pieces --------------------------------------------------------------------
    def _top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 8, 16, 8)
        b1 = QLabel("PRINTYZ")
        b1.setObjectName("BrandAccent")
        b2 = QLabel("Clicker Studio")
        b2.setObjectName("Brand")
        lay.addWidget(b1)
        lay.addWidget(b2)
        lay.addSpacing(24)
        lay.addWidget(QLabel(tr("שם הפרויקט:", "Project:")))
        self.proj_name = QLineEdit(self.ctl.project.name)
        self.proj_name.setFixedWidth(220)
        self.proj_name.textEdited.connect(self._rename)
        lay.addWidget(self.proj_name)
        lay.addStretch(1)
        self.mode = QComboBox()
        self.mode.addItem(tr("מצב מפתח", "Developer mode"), True)
        self.mode.addItem(tr("מצב לקוח", "Customer mode"), False)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        lay.addWidget(self.mode)
        lang = QPushButton("English" if is_rtl() else "עברית")
        lang.clicked.connect(lambda: self.on_language and self.on_language("en" if is_rtl() else "he", self))
        lay.addWidget(lang)
        return bar

    def _action_bar(self) -> QWidget:
        w = QFrame()
        w.setObjectName("SidePanel")
        w.setStyleSheet("#SidePanel { border-top: 1px solid #E2E5EA; }")
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 10, 14, 12)
        dl = QPushButton(icon("export", "#FFFFFF"), tr("  הורדת קבצי הדפסה  \u2066(3MF)\u2069", "  Download 3MF"))
        dl.setObjectName("Primary")
        dl.setMinimumHeight(42)
        dl.clicked.connect(lambda: self.export(Path(self.export_page.folder.text()), ("3mf", "stl", "step"), True))
        v.addWidget(dl)
        h = QHBoxLayout()
        for ic, text, fn in (("save", tr("שמור", "Save"), self.save), ("open", tr("פתח", "Open"), self.open)):
            b = QPushButton(icon(ic), " " + text)
            b.clicked.connect(fn)
            h.addWidget(b)
        v.addLayout(h)
        return w

    def _viewer_area(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(14, 12, 14, 12)
        bar = QHBoxLayout()
        self.assembly = Segmented([("assembled", tr("מורכב", "Assembled")), ("exploded", tr("מפורק", "Exploded"))])
        self.assembly.set_value("assembled")
        self.assembly.changed.connect(self._set_exploded)
        bar.addWidget(self.assembly)
        self.cb_switch = QCheckBox(tr("הצג מתג MX", "Show MX switch"))
        self.cb_switch.toggled.connect(lambda v_: self._viewer_flag("show_switches", v_))
        self.cb_cut = QCheckBox(tr("חתך", "Cut it open"))
        self.cb_cut.toggled.connect(lambda v_: self._viewer_flag("cutaway", v_))
        self.cb_glass = QCheckBox(tr("גוף שקוף", "See-through body"))
        self.cb_glass.toggled.connect(lambda v_: self._viewer_flag("body_opacity", 0.35 if v_ else 1.0))
        for c in (self.cb_switch, self.cb_cut, self.cb_glass):
            bar.addWidget(c)
        bar.addStretch(1)
        for key, text in (("iso", tr("אלכסוני", "3D")), ("top", tr("מלמעלה", "Top")),
                          ("side", tr("צד", "Side")), ("bottom", tr("מלמטה", "Bottom"))):
            b = QPushButton(text)
            b.setObjectName("ViewBtn")
            b.clicked.connect(lambda _=False, k=key: self.viewer.set_view(k))
            bar.addWidget(b)
        v.addLayout(bar)
        frame = QFrame()
        frame.setObjectName("ViewerFrame")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(2, 2, 2, 2)
        self.viewer = Viewer3D(frame)
        fl.addWidget(self.viewer.interactor if hasattr(self.viewer, "interactor") else self.viewer)
        v.addWidget(frame, 1)
        self.overlay = QLabel("")
        self.overlay.setObjectName("Hint")
        self.overlay.setWordWrap(True)
        v.addWidget(self.overlay)
        hint = QLabel(tr("גרירה שמאלית — סיבוב · גלגלת — זום · Shift+גרירה — הזזה",
                         "Left-drag rotate · wheel zoom · Shift+drag pan"))
        hint.setObjectName("Hint")
        v.addWidget(hint)
        return wrap

    def _add_page(self, ic: str, label: str, page: QWidget, dev_only: bool = False) -> None:
        it = QListWidgetItem(icon(ic), label)
        it.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        it.setSizeHint(QSize(98, 64))
        self.nav.addItem(it)
        self.stack.addWidget(page)
        self.pages.append((ic, page, dev_only))

    # ---- behaviour ---------------------------------------------------------------------------
    def _rename(self, t: str) -> None:
        self.ctl.project.name = t or "Untitled"

    def _update_title(self) -> None:
        self.setWindowTitle(f"PRINTYZ Clicker Studio — {self.ctl.project.name}")

    def _mode_changed(self) -> None:
        self.ctl.developer_mode = bool(self.mode.currentData())
        self._apply_mode()

    def _apply_mode(self) -> None:
        dev = self.ctl.developer_mode
        for row, (_, page, dev_only) in enumerate(self.pages):
            self.nav.item(row).setHidden(dev_only and not dev)
            if hasattr(page, "refresh"):
                page.refresh()
        if self.nav.currentItem() and self.nav.currentItem().isHidden():
            self.nav.setCurrentRow(0)

    def _set_exploded(self, v: str) -> None:
        self.viewer.exploded = v == "exploded"
        self.viewer.redraw()

    def _viewer_flag(self, attr: str, value) -> None:
        setattr(self.viewer, attr, value)
        self.viewer.redraw()

    def _set_overlay(self, text: str, kind: str) -> None:
        self.overlay.setText(text)
        self.overlay.setObjectName(kind)
        self.overlay.style().unpolish(self.overlay)
        self.overlay.style().polish(self.overlay)

    def _on_built(self, res, rep) -> None:
        if not res.ok:
            self.viewer.clear_model()
            self._set_overlay("⚠ " + " · ".join(res.errors), "Error")
            self.status_label.setText(tr("לא ניתן לבנות את המודל", "Model cannot be built"))
            return
        self.viewer.show_result(res)
        warns = [c for c in rep.checks if c.status == WARN]
        errs = [c for c in rep.checks if c.status == ERROR]
        if errs:
            self._set_overlay("✖ " + " · ".join(c.detail for c in errs[:3]), "Error")
        elif warns:
            self._set_overlay("⚠ " + " · ".join(c.detail.split(" / ")[0] for c in warns[:3]), "Warn")
        else:
            self._set_overlay("", "Hint")
        n = len(res.layout.keys)
        self.status_label.setText(
            tr(f"{n} מקשים · {res.style.name} · {res.project.lettering.mode} · "
               f"בדיקות: {'תקין ✓' if rep.passed else 'נכשל ✖'}",
               f"{n} keys · {res.style.name} · {res.project.lettering.mode} · "
               f"checks: {'passed ✓' if rep.passed else 'failed ✖'}"))

    def _on_failed(self, msg: str) -> None:
        self.viewer.clear_model()
        self._set_overlay(tr("שגיאה ביצירת הגיאומטריה: ", "Geometry error: ") + msg.splitlines()[0], "Error")

    # ---- files ---------------------------------------------------------------------------------
    def _save_fonts(self) -> None:
        self.fonts.save(self.font_lib)

    def save(self) -> None:
        path = self.project_path
        if path is None:
            fn, _ = QFileDialog.getSaveFileName(self, tr("שמירת פרויקט", "Save project"),
                                                f"{self.ctl.project.name}.printyz.json", "PRINTYZ (*.printyz.json *.json)")
            if not fn:
                return
            path = Path(fn)
        self.ctl.project.save(path)
        self.project_path = path
        self.status.showMessage(tr(f"נשמר: {path}", f"Saved: {path}"), 4000)

    def open(self) -> None:
        fn, _ = QFileDialog.getOpenFileName(self, tr("פתיחת פרויקט", "Open project"), "",
                                            "PRINTYZ (*.printyz.json *.json)")
        if not fn:
            return
        try:
            proj = Project.load(fn)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "PRINTYZ", str(e))
            return
        self.project_path = Path(fn)
        self.proj_name.setText(proj.name)
        self.ctl.replace_project(proj)
        for _, page, _ in self.pages:
            if hasattr(page, "ctl"):
                page.ctl = self.ctl
            if hasattr(page, "refresh"):
                page.refresh()

    def export(self, folder: Path, formats: tuple[str, ...], previews: bool) -> None:
        self.ctl.wait_idle()
        res = self.ctl.result
        if res is None or not res.ok:
            QMessageBox.warning(self, "PRINTYZ", tr("אין מודל תקין לייצוא.", "No valid model to export."))
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            rep = validate(res)  # full check incl. watertight meshes before writing files
            out = export_all(res, rep, folder, formats)
            if previews:
                from ..render.preview import render_set
                render_set(res, out / "Exports" / "Preview")
        finally:
            QApplication.restoreOverrideCursor()
        msg = tr(f"יוצא אל: {out}\nבדיקות: {'עברו' if rep.passed else 'נכשלו — ראה validation_report.md'}",
                 f"Exported to: {out}\nChecks: {'passed' if rep.passed else 'FAILED - see validation_report.md'}")
        self.export_page.result.setText(msg)
        box = QMessageBox(self)
        box.setWindowTitle("PRINTYZ")
        box.setText(msg)
        openb = box.addButton(tr("פתח תיקייה", "Open folder"), QMessageBox.AcceptRole)
        box.addButton(tr("סגור", "Close"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is openb:
            exp = out / "Exports"
            if sys.platform.startswith("win"):
                os.startfile(exp)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(exp)])

"""Settings pages. Every control writes into controller.project and calls controller.touch()."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from .. import MAX_KEYS
from ..config.mechanical import KEYCAP_STYLES
from ..fonts.registry import FontEntry
from ..text.engine import insert_extra_key, keys_visual, remove_key
from .controller import ProjectController
from .i18n import tr
from .widgets import ColorButton, Page, Segmented, dspin


def _key_label(k) -> str:
    if k.kind == "char":
        return k.value
    if k.kind == "blank":
        return "□"
    return "★"


class KeyStrip(QWidget):
    """Keys in visual (product) order; click selects one."""

    selected = Signal(str)

    def __init__(self, ctl: ProjectController, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self.current: str | None = None
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(4)
        self.setLayoutDirection(Qt.LeftToRight)   # the strip shows the physical product order

    def refresh(self) -> None:
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        keys = keys_visual(self.ctl.project)
        ids = {k.id for k in keys}
        if self.current not in ids:
            self.current = None
        for k in keys:
            b = QPushButton(_key_label(k))
            b.setObjectName("Chip")
            b.setCheckable(True)
            b.setChecked(k.id == self.current)
            tip = tr("מקש נוסף", "extra key") if k.source == "extra" else ""
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, kid=k.id: self._pick(kid))
            self.lay.addWidget(b)
        self.lay.addStretch(1)

    def _pick(self, kid: str) -> None:
        self.current = kid
        self.refresh()
        self.selected.emit(kid)


# ---------------------------------------------------------------------------------------------
class NamePage(Page):
    def __init__(self, ctl: ProjectController):
        super().__init__(tr("שם ופריסה", "Name & layout"))
        self.ctl = ctl
        p = ctl.project
        self.section(tr("שם / טקסט", "Name / text"))
        self.name = QLineEdit(p.text)
        self.name.setObjectName("NameInput")
        self.name.setPlaceholderText(tr("הקלד שם…", "Type a name…"))
        self.name.textChanged.connect(ctl.set_text)
        self.add(self.name)
        self.count = self.hint("")
        self.err = self.hint("", "Error")

        self.section(tr("מקשים (לפי סדר המוצר)", "Keys (product order)"))
        self.strip = KeyStrip(ctl)
        self.add(self.strip)
        row = QHBoxLayout()
        self.add_blank = QPushButton(tr("+ מקש ריק", "+ Blank key"))
        self.add_blank.clicked.connect(self._add_blank)
        self.remove = QPushButton(tr("הסר מקש נוסף", "Remove extra key"))
        self.remove.clicked.connect(self._remove)
        row.addWidget(self.add_blank)
        row.addWidget(self.remove)
        row.addStretch(1)
        self.lay.addLayout(row)
        self.hint(tr("בחר מקש ולחץ \"+ מקש ריק\" כדי להוסיף מקש ריק אחריו.",
                     "Select a key, then add a blank key after it."))

        self.section(tr("פריסה", "Layout"))
        self.style = Segmented([("row", tr("שורה", "Row")), ("column", tr("עמודה", "Column")),
                                ("grid", tr("רשת", "Grid")), ("wasd", "WASD"),
                                ("arrows", tr("חצים", "Arrows")), ("custom", tr("חופשי", "Custom"))], per_row=3)
        self.style.changed.connect(self._set_style)
        self.add(self.style)
        f = self.form()
        self.rows = QSpinBox()
        self.rows.setRange(1, 10)
        self.cols = QSpinBox()
        self.cols.setRange(1, 10)
        self.rows.valueChanged.connect(lambda v: self._set_layout("rows", v))
        self.cols.valueChanged.connect(lambda v: self._set_layout("cols", v))
        self.fill = QCheckBox(tr("מלא תאים פנויים במקשים ריקים", "Fill free cells with blank keys"))
        self.fill.toggled.connect(lambda v: self._set_layout("fill_empty_with_blank", v))
        self.grid_lbl = QLabel(tr("שורות × עמודות", "Rows × columns"))
        self.grid_w = QWidget()
        gw = QHBoxLayout(self.grid_w)
        gw.setContentsMargins(0, 0, 0, 0)
        gw.addWidget(self.rows)
        gw.addWidget(QLabel("×"))
        gw.addWidget(self.cols)
        gw.addStretch(1)
        f.addRow(self.grid_lbl, self.grid_w)
        f.addRow("", self.fill)
        self.direction = QComboBox()
        for v, t in (("auto", tr("אוטומטי לפי השפה", "Automatic")), ("rtl", tr("מימין לשמאל", "Right to left")),
                     ("ltr", tr("משמאל לימין", "Left to right"))):
            self.direction.addItem(t, v)
        self.direction.currentIndexChanged.connect(
            lambda _: self._set_layout("key_direction", self.direction.currentData()))
        f.addRow(tr("כיוון המקשים", "Key direction"), self.direction)

        self.custom_box = QFrame()
        self.custom_box.setObjectName("Card")
        cb = QVBoxLayout(self.custom_box)
        cb.addWidget(QLabel(tr("בחר מקש למעלה ולחץ על תא כדי למקם אותו:", "Select a key, then click a cell:")))
        self.cgrid = QGridLayout()
        self.cgrid.setSpacing(4)
        cb.addLayout(self.cgrid)
        self.custom_box.setLayoutDirection(Qt.LeftToRight)
        self.add(self.custom_box)
        self.finish()
        ctl.changed.connect(self.refresh)
        self.refresh()

    def _set_style(self, v: str) -> None:
        self.ctl.project.layout.style = v  # type: ignore[assignment]
        self.ctl.touch()

    def _set_layout(self, attr: str, v) -> None:
        if getattr(self.ctl.project.layout, attr) != v:
            setattr(self.ctl.project.layout, attr, v)
            self.ctl.touch()

    def _add_blank(self) -> None:
        p = self.ctl.project
        idx = len(p.keys)
        if self.strip.current:
            idx = next(i for i, k in enumerate(p.keys) if k.id == self.strip.current) + 1
        insert_extra_key(p, idx)
        self.ctl.last_sync.total_keys = len(p.keys)
        self.ctl.touch()

    def _remove(self) -> None:
        kid = self.strip.current
        if kid and self.ctl.project.key_by_id(kid).source == "extra":
            remove_key(self.ctl.project, kid)
            self.ctl.touch()

    def _place(self, r: int, c: int) -> None:
        kid = self.strip.current
        if not kid:
            return
        cells = self.ctl.project.layout.custom_cells
        for other, rc in list(cells.items()):
            if rc == [r, c] and other != kid:
                cells.pop(other)
        cells[kid] = [r, c]
        self.ctl.touch()

    def refresh(self) -> None:
        p = self.ctl.project
        if self.name.text() != p.text:
            self.name.blockSignals(True)
            self.name.setText(p.text)
            self.name.blockSignals(False)
        n = len(p.keys)
        chars = sum(1 for k in p.keys if k.kind == "char")
        extra = sum(1 for k in p.keys if k.source == "extra")
        self.count.setText(tr(f"{chars} תווים · {extra} מקשים נוספים · סה\"כ {n} מקשים (מקסימום {MAX_KEYS})",
                              f"{chars} characters · {extra} extra · {n} keys total (max {MAX_KEYS})"))
        self.err.setText(" ".join(self.ctl.last_sync.messages) if n > MAX_KEYS else "")
        self.err.setVisible(n > MAX_KEYS)
        self.strip.refresh()
        self.style.set_value(p.layout.style)
        for w, v in ((self.rows, p.layout.rows), (self.cols, p.layout.cols)):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        self.fill.blockSignals(True)
        self.fill.setChecked(p.layout.fill_empty_with_blank)
        self.fill.blockSignals(False)
        grid = p.layout.style == "grid"
        for w in (self.grid_w, self.fill, self.grid_lbl):
            w.setVisible(grid)
        self.direction.blockSignals(True)
        self.direction.setCurrentIndex(self.direction.findData(p.layout.key_direction))
        self.direction.blockSignals(False)
        self.custom_box.setVisible(p.layout.style == "custom")
        if p.layout.style == "custom":
            self._refresh_custom()

    def _refresh_custom(self) -> None:
        while self.cgrid.count():
            w = self.cgrid.takeAt(0).widget()
            if w:
                w.deleteLater()
        p = self.ctl.project
        res = self.ctl.result
        placed = {}
        if res is not None:
            for pk in res.layout.keys:
                if pk.key_id:
                    placed[(pk.row, pk.col)] = pk.key_id
        for rc_id, rc in p.layout.custom_cells.items():
            placed[tuple(rc)] = rc_id
        by_id = {k.id: k for k in p.keys}
        for r in range(5):
            for c in range(5):
                kid = placed.get((r, c))
                b = QPushButton(_key_label(by_id[kid]) if kid in by_id else "")
                b.setFixedSize(40, 40)
                b.setStyleSheet("background:#2B2B2B; color:white; border-radius:6px;" if kid in by_id
                                else "background:#F1F3F6; border:1px dashed #C9CED6; border-radius:6px;")
                b.clicked.connect(lambda _=False, rr=r, cc=c: self._place(rr, cc))
                self.cgrid.addWidget(b, r, c)


# ---------------------------------------------------------------------------------------------
class FontCard(QFrame):
    clicked = Signal(str)

    def __init__(self, entry: FontEntry, sample: str, selected: bool, dev: bool, on_approve):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("selected", "true" if selected else "false")
        self.entry = entry
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        top = QHBoxLayout()
        name = QLabel(f"<b>{entry.family}</b>  <span style='color:#6B7280'>{entry.weight}</span>")
        top.addWidget(name)
        top.addStretch(1)
        langs = "עב" if entry.supports_hebrew else ""
        langs += " · EN" if entry.supports_latin else ""
        top.addWidget(QLabel(f"<span style='color:#6B7280'>{langs}</span>"))
        if dev:
            ap = QCheckBox(tr("מאושר ללקוח", "Approved"))
            ap.setChecked(entry.approved)
            ap.toggled.connect(lambda v: on_approve(entry, v))
            top.addWidget(ap)
        lay.addLayout(top)
        fid = QFontDatabase.addApplicationFont(entry.path)
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        prev = QLabel(sample)
        f = QFont(fams[0] if fams else entry.family)
        f.setPointSize(22)
        f.setWeight(QFont.Weight(min(900, max(100, entry.weight))))
        prev.setFont(f)
        lay.addWidget(prev)

    def mousePressEvent(self, e):  # noqa: N802 - Qt API
        self.clicked.emit(self.entry.id)
        super().mousePressEvent(e)


class FontPage(Page):
    def __init__(self, ctl: ProjectController, save_library):
        super().__init__(tr("גופנים", "Fonts"))
        self.ctl = ctl
        self.save_library = save_library
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("חיפוש גופן…", "Search fonts…"))
        self.search.textChanged.connect(self.refresh)
        self.lang = QComboBox()
        for v, t in (("all", tr("כל השפות", "All languages")), ("he", tr("עברית", "Hebrew")),
                     ("en", tr("אנגלית", "English"))):
            self.lang.addItem(t, v)
        self.lang.currentIndexChanged.connect(self.refresh)
        row.addWidget(self.search, 2)
        row.addWidget(self.lang, 1)
        self.lay.addLayout(row)
        self.dev_row = QHBoxLayout()
        add = QPushButton(tr("הוסף גופן (TTF/OTF)…", "Add font (TTF/OTF)…"))
        add.clicked.connect(self._add_font)
        scan = QPushButton(tr("סרוק גופנים מותקנים", "Scan installed fonts"))
        scan.clicked.connect(self._scan)
        self.dev_row.addWidget(add)
        self.dev_row.addWidget(scan)
        self.dev_row.addStretch(1)
        self.dev_widget = QWidget()
        self.dev_widget.setLayout(self.dev_row)
        self.add(self.dev_widget)
        self.list_box = QVBoxLayout()
        self.list_box.setSpacing(8)
        self.lay.addLayout(self.list_box)
        self.finish()
        ctl.changed.connect(self._maybe_refresh)
        self._last_text = None
        self.refresh()

    def _maybe_refresh(self) -> None:
        if self.ctl.project.text != self._last_text:
            self.refresh()

    def _add_font(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("בחר גופן", "Choose font"), "", "Fonts (*.ttf *.otf)")
        if path:
            self.ctl.fonts.add(FontEntry(id=f"user:{Path(path).stem}", path=path, approved=False))
            self.save_library()
            self.refresh()

    def _scan(self) -> None:
        self.ctl.fonts.scan_installed()
        self.refresh()

    def _approve(self, entry: FontEntry, v: bool) -> None:
        entry.approved = v
        self.save_library()

    def _choose(self, fid: str) -> None:
        self.ctl.project.lettering.font_id = fid
        self.ctl.touch()
        self.refresh()

    def refresh(self) -> None:
        while self.list_box.count():
            w = self.list_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        dev = self.ctl.developer_mode
        self.dev_widget.setVisible(dev)
        text = self.ctl.project.text.strip()
        self._last_text = self.ctl.project.text
        q = self.search.text().strip().lower()
        lang = self.lang.currentData()
        fonts = self.ctl.fonts.fonts.values() if dev else self.ctl.fonts.customer_fonts()
        shown = 0
        for e in sorted(fonts, key=lambda f: (not f.approved, f.family.lower(), f.weight)):
            if q and q not in e.family.lower():
                continue
            if lang == "he" and not e.supports_hebrew or lang == "en" and not e.supports_latin:
                continue
            sample = text or ("שלום Abc" if e.supports_hebrew else "Hello Abc")
            card = FontCard(e, sample, e.id == self.ctl.project.lettering.font_id, dev, self._approve)
            card.clicked.connect(self._choose)
            self.list_box.addWidget(card)
            shown += 1
            if shown >= 60:
                break


# ---------------------------------------------------------------------------------------------
class LetteringPage(Page):
    def __init__(self, ctl: ProjectController):
        super().__init__(tr("כיתוב", "Lettering"))
        self.ctl = ctl
        L = ctl.project.lettering
        self.section(tr("סגנון", "Style"))
        self.mode = Segmented([("flush", tr("שטוח צבעוני", "Flush colour")),
                               ("raised", tr("בולט", "Raised")), ("engraved", tr("חרוט", "Engraved"))])
        self.mode.changed.connect(lambda v: self._set("mode", v))
        self.add(self.mode)
        self.mode_hint = self.hint("")
        self.section(tr("משקל", "Weight"))
        self.weight = Segmented([("regular", "Regular"), ("bold", "Bold")])
        self.weight.changed.connect(self._set_weight)
        self.add(self.weight)
        f = self.form()
        self.extra = dspin(0, 0.8, 0.05, L.extra_weight)
        self.extra.valueChanged.connect(lambda v: self._set("extra_weight", v))
        f.addRow(tr("עיבוי נוסף", "Extra weight"), self.extra)
        self.section(tr("גודל ומיקום", "Size & position"))
        f = self.form()
        self.auto = QCheckBox(tr("הגדול ביותר שנכנס", "Largest that fits"))
        self.auto.toggled.connect(self._auto)
        self.size = dspin(3, 25, 0.5, L.size or 11.0)
        self.size.valueChanged.connect(lambda v: self._set("size", v))
        f.addRow(tr("גודל אות", "Letter size"), self.auto)
        f.addRow("", self.size)
        self.margin = dspin(1.0, 3.5, 0.05, L.margin)
        self.margin.valueChanged.connect(lambda v: self._set("margin", v))
        f.addRow(tr("שוליים", "Margin"), self.margin)
        self.ox = dspin(-6, 6, 0.1, L.offset_x)
        self.oy = dspin(-6, 6, 0.1, L.offset_y)
        self.ox.valueChanged.connect(lambda v: self._set("offset_x", v))
        self.oy.valueChanged.connect(lambda v: self._set("offset_y", v))
        f.addRow(tr("הזזה אופקית", "Offset X"), self.ox)
        f.addRow(tr("הזזה אנכית", "Offset Y"), self.oy)
        self.depth_lbl = QLabel()
        self.depth = dspin(0.2, 1.2, 0.2, L.depth)
        self.depth.valueChanged.connect(self._depth)
        f.addRow(self.depth_lbl, self.depth)
        self.size_info = self.hint("")
        self.finish()
        ctl.changed.connect(self.refresh)
        ctl.built.connect(lambda *_: self.refresh())
        self.refresh()

    def _set(self, attr, v) -> None:
        setattr(self.ctl.project.lettering, attr, v)
        self.ctl.touch()

    def _auto(self, on: bool) -> None:
        self._set("size", None if on else self.size.value())

    def _depth(self, v: float) -> None:
        attr = "raise_height" if self.ctl.project.lettering.mode == "raised" else "depth"
        self._set(attr, v)

    def _set_weight(self, w: str) -> None:
        reg = self.ctl.fonts
        try:
            cur = reg.resolve(self.ctl.project.lettering.font_id)
        except KeyError:
            return
        sib = reg.sibling(cur, w == "bold")
        if sib:
            self._set("font_id", sib.id)

    def refresh(self) -> None:
        L = self.ctl.project.lettering
        self.mode.set_value(L.mode)
        hints = {
            "flush": tr("האות בצבע נפרד ובגובה זהה בדיוק לפני הכובע. מודפס כשפני הכובע על המגש.",
                        "Different colour, exactly level with the keycap top. Printed face-down."),
            "raised": tr("האות בולטת מעל הכובע. הכובע מודפס זקוף.", "Legend stands above the top. Printed upright."),
            "engraved": tr("חריטה שקועה ללא מילוי.", "Recessed engraving, no fill."),
        }
        self.mode_hint.setText(hints[L.mode])
        try:
            cur = self.ctl.fonts.resolve(L.font_id)
            self.weight.set_value("bold" if cur.is_bold else "regular")
            for w in ("regular", "bold"):
                ok = self.ctl.fonts.sibling(cur, w == "bold") is not None
                self.weight.set_enabled_value(w, ok, "" if ok else tr("אין משקל כזה בגופן", "Not available"))
        except KeyError:
            pass
        for w, v in ((self.extra, L.extra_weight), (self.margin, L.margin), (self.ox, L.offset_x),
                     (self.oy, L.offset_y)):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        self.auto.blockSignals(True)
        self.auto.setChecked(L.size is None)
        self.auto.blockSignals(False)
        self.size.setEnabled(L.size is not None)
        raised = L.mode == "raised"
        self.depth_lbl.setText(tr("גובה בליטה", "Raise height") if raised else tr("עומק", "Depth"))
        self.depth.blockSignals(True)
        self.depth.setValue(L.raise_height if raised else L.depth)
        self.depth.blockSignals(False)
        res = self.ctl.result
        if res and res.legend_boxes:
            hmax = max(h for _, h in res.legend_boxes.values())
            area = res.style.legend_area - 2 * L.margin
            self.size_info.setText(tr(f"גובה אות בפועל: {hmax:.1f} מ\"מ · שטח מותר: {area:.1f} מ\"מ",
                                      f"Actual letter height: {hmax:.1f} mm · allowed: {area:.1f} mm"))


# ---------------------------------------------------------------------------------------------
class KeycapPage(Page):
    NAMES = {"standard": ("Standard", "רגיל"), "low_profile": ("Low Profile", "נמוך"), "thocky": ("Thocky", "עבה")}

    def __init__(self, ctl: ProjectController):
        super().__init__(tr("כובעי מקשים", "Keycaps"))
        self.ctl = ctl
        self.cards: dict[str, QFrame] = {}
        for sid, st in KEYCAP_STYLES.items():
            card = QFrame()
            card.setObjectName("Card")
            v = QVBoxLayout(card)
            en, he = self.NAMES[sid]
            v.addWidget(QLabel(f"<b style='font-size:12pt'>{en}</b>  <span style='color:#6B7280'>{he}</span>"))
            v.addWidget(QLabel(tr(
                f"גובה {st.height:.2f} · דופן {st.wall:.1f} · עובי עליון {st.top_thickness:.1f} · שיפוע {st.taper_deg:.2f}°",
                f"Height {st.height:.2f} · wall {st.wall:.1f} · top {st.top_thickness:.1f} · taper {st.taper_deg:.2f}°")))
            card.mousePressEvent = lambda e, s=sid: self._pick(s)  # type: ignore[method-assign]
            self.cards[sid] = card
            self.add(card)
        self.hint(tr("Thocky משנה את המבנה; הצליל בפועל ייקבע רק בבדיקה פיזית.",
                     "Thocky changes the structure; actual sound needs a physical test."))
        self.finish()
        ctl.changed.connect(self.refresh)
        self.refresh()

    def _pick(self, sid: str) -> None:
        self.ctl.project.keycap_style = sid
        self.ctl.touch()

    def refresh(self) -> None:
        for sid, card in self.cards.items():
            card.setProperty("selected", "true" if sid == self.ctl.project.keycap_style else "false")
            card.style().unpolish(card)
            card.style().polish(card)


# ---------------------------------------------------------------------------------------------
class BodyPage(Page):
    def __init__(self, ctl: ProjectController):
        super().__init__(tr("גוף וטקסטורות", "Body & textures"))
        self.ctl = ctl
        self.section(tr("חיבור בין המקשים", "Joint between keys"))
        self.joint = Segmented([("grooved", tr("שקע עדין", "Grooved")), ("smooth", tr("חלק", "Smooth"))])
        self.joint.changed.connect(self._joint)
        self.add(self.joint)
        f = self.form()
        self.depth = dspin(0.3, 1.2, 0.1, ctl.project.body.groove_depth)
        self.depth.valueChanged.connect(self._depth)
        f.addRow(tr("עומק השקע", "Groove depth"), self.depth)
        self.section(tr("טקסטורה חיצונית", "Outside texture"))
        self.hint(tr("טקסטורות (יהלומים, פסים, חריצים, נקודות, זיגזג) עדיין לא ממומשות בגיאומטריה ולכן אינן "
                     "מוצגות כאפשרות פעילה.",
                     "Textures are not implemented in the geometry yet, so they are not offered."), "Warn")
        self.finish()
        ctl.changed.connect(self.refresh)
        self.refresh()

    def _joint(self, v: str) -> None:
        self.ctl.project.body.joint = v  # type: ignore[assignment]
        self.ctl.touch()

    def _depth(self, v: float) -> None:
        self.ctl.project.body.groove_depth = v
        self.ctl.touch()

    def refresh(self) -> None:
        self.joint.set_value(self.ctl.project.body.joint)
        self.depth.setEnabled(self.ctl.project.body.joint == "grooved")


# ---------------------------------------------------------------------------------------------
class ColorsPage(Page):
    def __init__(self, ctl: ProjectController):
        super().__init__(tr("צבעים", "Colours"))
        self.ctl = ctl
        c = ctl.project.colors
        self.section(tr("צבעי ברירת מחדל", "Default colours"))
        f = self.form()
        self.body = ColorButton(c.body)
        self.cap = ColorButton(c.cap)
        self.legend = ColorButton(c.legend)
        self.body.picked.connect(lambda v: self._set("body", v))
        self.cap.picked.connect(lambda v: self._set("cap", v))
        self.legend.picked.connect(lambda v: self._set("legend", v))
        f.addRow(tr("גוף", "Body"), self.body)
        f.addRow(tr("כובעים", "Keycaps"), self.cap)
        f.addRow(tr("אותיות", "Letters"), self.legend)
        self.section(tr("צבע למקש בודד", "Per-key colour"))
        self.strip = KeyStrip(ctl)
        self.strip.selected.connect(lambda _: self.refresh())
        self.add(self.strip)
        f2 = self.form()
        self.kcap = ColorButton("#000000")
        self.kleg = ColorButton("#000000")
        self.kcap.picked.connect(lambda v: self._key("cap_color", v))
        self.kleg.picked.connect(lambda v: self._key("legend_color", v))
        self.kreset = QPushButton(tr("חזור לברירת מחדל", "Use defaults"))
        self.kreset.clicked.connect(self._reset_key)
        f2.addRow(tr("כובע", "Keycap"), self.kcap)
        f2.addRow(tr("אות", "Letter"), self.kleg)
        f2.addRow("", self.kreset)
        self.count = self.hint("")
        self.finish()
        ctl.changed.connect(self.refresh)
        self.refresh()

    def _set(self, attr: str, v: str) -> None:
        setattr(self.ctl.project.colors, attr, v)
        self.ctl.touch()

    def _key(self, attr: str, v: str) -> None:
        if self.strip.current:
            setattr(self.ctl.project.key_by_id(self.strip.current), attr, v)
            self.ctl.touch()

    def _reset_key(self) -> None:
        if self.strip.current:
            k = self.ctl.project.key_by_id(self.strip.current)
            k.cap_color = k.legend_color = None
            self.ctl.touch()

    def refresh(self) -> None:
        p = self.ctl.project
        self.body.set_color(p.colors.body)
        self.cap.set_color(p.colors.cap)
        self.legend.set_color(p.colors.legend)
        self.strip.refresh()
        has = self.strip.current is not None
        for w in (self.kcap, self.kleg, self.kreset):
            w.setEnabled(has)
        if has:
            k = p.key_by_id(self.strip.current)
            self.kcap.set_color(p.cap_color(k))
            self.kleg.set_color(p.legend_color(k))
        cols = {p.colors.body.upper()} | {p.cap_color(k).upper() for k in p.keys} | {
            p.legend_color(k).upper() for k in p.keys if k.kind == "char"}
        warn = len(cols) > 4
        self.count.setObjectName("Warn" if warn else "Hint")
        self.count.setText(tr(f"{len(cols)} צבעים בסך הכל (AMS lite: עד 4)", f"{len(cols)} colours (AMS lite: up to 4)"))
        self.count.style().unpolish(self.count)
        self.count.style().polish(self.count)


# ---------------------------------------------------------------------------------------------
class KeychainPage(Page):
    def __init__(self, ctl: ProjectController):
        super().__init__(tr("מחזיק מפתחות", "Keychain"))
        self.ctl = ctl
        k = ctl.project.keychain
        self.enabled = QCheckBox(tr("הוסף מחזיק מפתחות", "Add keychain tab"))
        self.enabled.toggled.connect(lambda v: self._set("enabled", v))
        self.add(self.enabled)
        self.side = Segmented([("top", tr("עליון", "Top")), ("bottom", tr("תחתון", "Bottom")),
                               ("right", tr("ימין", "Right")), ("left", tr("שמאל", "Left"))])
        self.side.changed.connect(lambda v: self._set("side", v))
        self.add(self.side)
        f = self.form()
        self.offset = QSlider(Qt.Horizontal)
        self.offset.setRange(-100, 100)
        self.offset.valueChanged.connect(lambda v: self._set("offset", v / 2.0))
        f.addRow(tr("מיקום לאורך הצלע", "Position along side"), self.offset)
        self.fields = {}
        for attr, lab, lo, hi in (("hole_diameter", tr("קוטר חור", "Hole Ø"), 3, 8),
                                  ("width", tr("רוחב", "Width"), 8, 20), ("length", tr("אורך", "Length"), 6, 16),
                                  ("thickness", tr("עובי", "Thickness"), 2.5, 8),
                                  ("root_radius", tr("רדיוס חיבור", "Root radius"), 0.5, 4)):
            s = dspin(lo, hi, 0.1, getattr(k, attr))
            s.valueChanged.connect(lambda v, a=attr: self._set(a, v))
            f.addRow(lab, s)
            self.fields[attr] = s
        self.hint(tr("חוזק הלשונית ייבדק בהדפסה ובמשיכה לפני שימוש מסחרי.",
                     "Tab strength must be verified with a printed pull test."))
        self.finish()
        ctl.changed.connect(self.refresh)
        self.refresh()

    def _set(self, attr, v) -> None:
        if getattr(self.ctl.project.keychain, attr) != v:
            setattr(self.ctl.project.keychain, attr, v)
            self.ctl.touch()

    def refresh(self) -> None:
        k = self.ctl.project.keychain
        self.enabled.blockSignals(True)
        self.enabled.setChecked(k.enabled)
        self.enabled.blockSignals(False)
        self.side.set_value(k.side)
        self.offset.blockSignals(True)
        self.offset.setValue(int(k.offset * 2))
        self.offset.blockSignals(False)
        for a, s in self.fields.items():
            s.blockSignals(True)
            s.setValue(getattr(k, a))
            s.blockSignals(False)
            s.setEnabled(k.enabled)
        self.side.setEnabled(k.enabled)
        self.offset.setEnabled(k.enabled)


# ---------------------------------------------------------------------------------------------
class MechanicalPage(Page):
    """Developer only: calibrated mechanical dimensions."""

    def __init__(self, ctl: ProjectController):
        super().__init__(tr("התאמה מכאנית (מפתח)", "Mechanical fit (developer)"))
        self.ctl = ctl
        self.hint(tr("שינוי ערכים אלה משפיע על התאמת המתג והכובע. אין לשנות ללא הדפסת בדיקה.",
                     "These values affect switch / keycap fit. Do not change without a test print."), "Warn")
        self.spins: dict[tuple[str, str], object] = {}
        m = ctl.project.mechanical
        for group, obj in (("switch", m.switch), ("body", m.body)):
            self.section("MX switch" if group == "switch" else tr("גוף", "Body"))
            f = self.form()
            for fld in dataclasses.fields(obj):
                v = getattr(obj, fld.name)
                s = dspin(0, 60, 0.05, v)
                s.valueChanged.connect(lambda val, g=group, n=fld.name: self._set(g, n, val))
                f.addRow(fld.name, s)
                self.spins[(group, fld.name)] = s
        reset = QPushButton(tr("החזר לערכי ברירת מחדל", "Restore defaults"))
        reset.clicked.connect(self._reset)
        self.add(reset)
        self.finish()

    def _set(self, group: str, name: str, val: float) -> None:
        m = self.ctl.project.mechanical
        part = dataclasses.replace(getattr(m, group), **{name: val})
        self.ctl.project.mechanical = dataclasses.replace(m, **{group: part})
        self.ctl.touch()

    def _reset(self) -> None:
        from ..config.mechanical import DEFAULT_PROFILE

        self.ctl.project.mechanical = DEFAULT_PROFILE
        for (g, n), s in self.spins.items():
            s.blockSignals(True)
            s.setValue(getattr(getattr(DEFAULT_PROFILE, g), n))
            s.blockSignals(False)
        self.ctl.touch()


# ---------------------------------------------------------------------------------------------
class ExportPage(Page):
    def __init__(self, ctl: ProjectController, do_export):
        super().__init__(tr("ייצוא", "Export"))
        self.ctl = ctl
        self.section(tr("תיקיית פרויקטים", "Projects folder"))
        row = QHBoxLayout()
        self.folder = QLineEdit(str(Path.home() / "Documents" / "PRINTYZ" / "Projects"))
        browse = QPushButton("…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        self.lay.addLayout(row)
        self.section(tr("פורמטים", "Formats"))
        self.fmt = {}
        for k, t in (("3mf", tr("3MF להדפסה צבעונית (Bambu Studio)", "3MF multi-colour (Bambu Studio)")),
                     ("stl", tr("STL לכל חלק", "STL per part")), ("step", tr("STEP להרכבה (CAD)", "STEP assembly (CAD)"))):
            cb = QCheckBox(t)
            cb.setChecked(True)
            self.fmt[k] = cb
            self.add(cb)
        self.previews = QCheckBox(tr("תמונות תצוגה", "Preview images"))
        self.previews.setChecked(True)
        self.add(self.previews)
        btn = QPushButton(tr("ייצא קבצי הדפסה", "Export print files"))
        btn.setObjectName("Primary")
        btn.clicked.connect(lambda: do_export(Path(self.folder.text()),
                                              tuple(k for k, cb in self.fmt.items() if cb.isChecked()),
                                              self.previews.isChecked()))
        self.add(btn)
        self.result = self.hint("")
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.finish()

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("בחר תיקייה", "Choose folder"), self.folder.text())
        if d:
            self.folder.setText(d)

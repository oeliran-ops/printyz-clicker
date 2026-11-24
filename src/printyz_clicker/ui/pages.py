"""Settings pages. Every control writes into controller.project and calls controller.touch()."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from .. import MAX_KEYS
from ..config.mechanical import KEYCAP_STYLES
from ..fonts.registry import FontEntry
from ..text.engine import insert_blank_visual, keys_visual, remove_key
from .controller import ProjectController
from .i18n import is_rtl, tr
from .widgets import ColorButton, Page, Segmented, dspin


def _key_label(k) -> str:
    if k.kind == "char":
        return k.value
    if k.kind == "blank":
        return "□"
    if k.kind == "svg":
        return "SVG"
    from ..geometry.symbols import SYMBOLS

    return SYMBOLS.get(k.value, (k.value, k.value))[0 if is_rtl() else 1]


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
                w.setParent(None)
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



LAYOUT_ICONS = {
    "row": [(0, 0), (0, 1), (0, 2), (0, 3)],
    "column": [(0, 0), (1, 0), (2, 0)],
    "grid": [(r, c) for r in range(3) for c in range(3)],
    "wasd": [(0, 1), (1, 0), (1, 1), (1, 2)],
    "arrows": [(0, 1), (1, 0), (1, 2), (2, 1)],
    "custom": [(0, 0), (0, 1), (1, 1), (1, 2), (2, 0), (2, 2)],
}


def layout_pixmap(style: str, size: int = 64):
    from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

    cells = LAYOUT_ICONS[style]
    rows = max(r for r, _ in cells) + 1
    cols = max(c for _, c in cells) + 1
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    u = size * 2 / max(rows, cols, 3) * 0.82
    ox = (size * 2 - cols * u) / 2
    oy = (size * 2 - rows * u) / 2
    for r in range(rows):
        for c in range(cols):
            x, y = ox + c * u + u * 0.08, oy + r * u + u * 0.08
            if (r, c) in cells:
                p.setPen(QPen(QColor("#7B8494"), 2))
                p.setBrush(QColor("#CDD3DC"))
                p.drawRoundedRect(x, y, u * 0.84, u * 0.84, u * 0.18, u * 0.18)
            elif style == "custom":
                pen = QPen(QColor("#A6AEBB"), 2, Qt.DashLine)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(x, y, u * 0.84, u * 0.84, u * 0.18, u * 0.18)
    p.end()
    return pm


class IconCard(QFrame):
    clicked = Signal(str)

    def __init__(self, key: str, title: str, pixmap):
        super().__init__()
        self.key = key
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 8, 6, 8)
        pic = QLabel()
        pic.setAlignment(Qt.AlignCenter)
        pic.setPixmap(pixmap.scaledToHeight(54, Qt.SmoothTransformation))
        v.addWidget(pic)
        t = QLabel(title)
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("font-weight: 600;")
        v.addWidget(t)

    def set_selected(self, on: bool) -> None:
        self.setProperty("selected", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, e):  # noqa: N802
        self.clicked.emit(self.key)


class Stepper(QWidget):
    """[ − ] value [ + ] control."""

    changed = Signal(int)

    def __init__(self, lo: int, hi: int):
        super().__init__()
        self.lo, self.hi, self.v = lo, hi, lo
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.minus = QPushButton("−")
        self.plus = QPushButton("+")
        self.lab = QLabel()
        self.lab.setAlignment(Qt.AlignCenter)
        self.lab.setStyleSheet("background:#F1F3F6; border:1px solid #E2E5EA; border-radius:8px; padding:7px;")
        for b in (self.minus, self.plus):
            b.setFixedWidth(40)
        h.addWidget(self.minus)
        h.addWidget(self.lab, 1)
        h.addWidget(self.plus)
        self.minus.clicked.connect(lambda: self._step(-1))
        self.plus.clicked.connect(lambda: self._step(1))
        self.set_value(lo)

    def _step(self, d: int) -> None:
        nv = min(self.hi, max(self.lo, self.v + d))
        if nv != self.v:
            self.set_value(nv)
            self.changed.emit(nv)

    def set_value(self, v: int) -> None:
        self.v = v
        self.lab.setText(str(v))
        self.minus.setEnabled(v > self.lo)
        self.plus.setEnabled(v < self.hi)


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
        self.add_left = QPushButton(tr("+ ריק משמאל", "+ Blank left"))
        self.add_right = QPushButton(tr("+ ריק מימין", "+ Blank right"))
        self.add_left.clicked.connect(lambda: self._add_blank("left"))
        self.add_right.clicked.connect(lambda: self._add_blank("right"))
        self.remove = QPushButton(tr("הסר מקש", "Remove key"))
        self.remove.clicked.connect(self._remove)
        row.addWidget(self.add_right)
        row.addWidget(self.add_left)
        row.addWidget(self.remove)
        row.addStretch(1)
        self.lay.addLayout(row)
        self.hint(tr("מקש ריק נוסף ליד המקש שנבחר, או בקצה אם לא נבחר מקש. \"הסר\" מוחק מקש ריק או סמל שהוספת.",
                     "Blank keys go next to the selected key, or at the end. Remove deletes an added key."))

        self.section(tr("פריסה", "Layout"))
        names = [("row", tr("שורה", "Row")), ("column", tr("עמודה", "Column")), ("grid", tr("רשת", "Grid")),
                 ("wasd", "WASD"), ("arrows", tr("חצים", "Arrows")), ("custom", tr("חופשי", "Custom"))]
        self.layout_cards: dict[str, IconCard] = {}
        for k, t in names:
            c = IconCard(k, t, layout_pixmap(k))
            c.clicked.connect(self._set_style)
            self.layout_cards[k] = c
        grid_w = QWidget()
        gl = QGridLayout(grid_w)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(8)
        for i, c in enumerate(self.layout_cards.values()):
            gl.addWidget(c, i // 3, i % 3)
        self.add(grid_w)
        f = self.form()
        self.rows = Stepper(1, 10)
        self.cols = Stepper(1, 10)
        self.rows.changed.connect(lambda v: self._set_layout("rows", v))
        self.cols.changed.connect(lambda v: self._set_layout("cols", v))
        self.fill = QCheckBox(tr("מלא תאים פנויים במקשים ריקים", "Fill free cells with blank keys"))
        self.fill.toggled.connect(lambda v: self._set_layout("fill_empty_with_blank", v))
        self.grid_lbl = QLabel(tr("שורות", "Rows"))
        self.cols_lbl = QLabel(tr("עמודות", "Columns"))
        f.addRow(self.grid_lbl, self.rows)
        f.addRow(self.cols_lbl, self.cols)
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

    def _add_blank(self, side: str) -> None:
        p = self.ctl.project
        k = insert_blank_visual(p, side, self.strip.current)
        self.strip.current = k.id
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
        for k, c in self.layout_cards.items():
            c.set_selected(k == p.layout.style)
        self.rows.set_value(p.layout.rows)
        self.cols.set_value(p.layout.cols)
        self.fill.blockSignals(True)
        self.fill.setChecked(p.layout.fill_empty_with_blank)
        self.fill.blockSignals(False)
        grid = p.layout.style == "grid"
        for w in (self.rows, self.cols, self.fill, self.grid_lbl, self.cols_lbl):
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
                w.setParent(None)
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
_QT_FONTS: dict[str, list[str]] = {}


def _qt_families(path: str) -> list[str]:
    if path not in _QT_FONTS:
        fid = QFontDatabase.addApplicationFont(path)
        _QT_FONTS[path] = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
    return _QT_FONTS[path]


class FontCard(QFrame):
    """Compact card: the user's text in the font (large) + family name (small)."""

    clicked = Signal(str)

    def __init__(self, entry: FontEntry, sample: str, selected: bool, dev: bool, on_approve):
        from PySide6.QtWidgets import QSizePolicy

        super().__init__()
        self.setObjectName("Card")
        self.setProperty("selected", "true" if selected else "false")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setFixedHeight(92 if dev else 78)
        self.entry = entry
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(0)
        fams = _qt_families(entry.path)
        prev = QLabel(sample)
        prev.setTextFormat(Qt.PlainText)
        prev.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        fam = (fams[0] if fams else entry.family).replace("'", "")
        # the app stylesheet sets font-family on every QWidget, so the sample font must be a stylesheet too
        prev.setStyleSheet(f"font-family: '{fam}'; font-size: 28px; font-weight: {min(900, max(100, entry.weight))};")
        lay.addWidget(prev)
        name = QLabel(entry.family)
        name.setStyleSheet("color:#6B7280; font-size:9pt;")
        name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        lay.addWidget(name)
        if dev:
            ap = QCheckBox(tr("ללקוח", "Customer"))
            ap.setStyleSheet("font-size:8.5pt;")
            ap.setChecked(entry.approved)
            ap.toggled.connect(lambda v: on_approve(entry, v))
            lay.addWidget(ap)

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
        self.count_lbl = self.hint("")
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
                w.setParent(None)
                w.deleteLater()
        dev = self.ctl.developer_mode
        self.dev_widget.setVisible(dev)
        text = self.ctl.project.text.strip()
        self._last_text = self.ctl.project.text
        q = self.search.text().strip().lower()
        lang = self.lang.currentData()
        cur = self.ctl.project.lettering.font_id
        fonts = list(self.ctl.fonts.fonts.values()) if dev else self.ctl.fonts.customer_fonts()
        # one card per family: the selected variant, else the boldest approved one
        fam: dict[str, FontEntry] = {}
        for e in fonts:
            best = fam.get(e.family)
            if best is None or e.id == cur or (best.id != cur and (e.approved, e.weight) > (best.approved, best.weight)):
                fam[e.family] = e
        heb_text = any("\u0590" <= ch <= "\u05ff" for ch in text)
        cards = []
        for e in sorted(fam.values(), key=lambda f: (not f.approved, not f.supports_hebrew, f.family.lower())):
            if q and q not in e.family.lower():
                continue
            if lang == "he" and not e.supports_hebrew or lang == "en" and not e.supports_latin:
                continue
            if heb_text and not e.supports_hebrew and not dev:
                continue                         # never offer a font that cannot write the name
            sample = (text[:7] if text else ("שלום" if e.supports_hebrew else "Name"))
            card = FontCard(e, sample, e.family == self._family_of(cur), dev, self._approve)
            card.clicked.connect(self._choose)
            cards.append(card)
        grid = QWidget()
        g = QGridLayout(grid)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(8)
        for i, c in enumerate(cards):
            g.addWidget(c, i // 2, i % 2)
        self.list_box.addWidget(grid)
        self.count_lbl.setText(tr(f"{len(cards)} גופנים", f"{len(cards)} fonts"))

    def _family_of(self, fid: str) -> str:
        try:
            return self.ctl.fonts.resolve(fid).family
        except KeyError:
            return ""


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
        self.extra = dspin(-0.3, 0.8, 0.05, L.extra_weight)
        self.extra.valueChanged.connect(lambda v: self._set("extra_weight", v))
        f.addRow(tr("עובי (Boldness)", "Boldness"), self.extra)
        self.section(tr("גודל ומיקום", "Size & position"))
        f = self.form()
        self.auto = QCheckBox(tr("לפי אחוזים (ללא מ\"מ מדויק)", "Use percentage"))
        self.auto.toggled.connect(self._auto)
        self.size = dspin(3, 25, 0.5, L.size or 11.0)
        self.size.valueChanged.connect(lambda v: self._set("size", v))
        self.pct = SliderRow(10, 100, 1, 0, " %")
        self.pct.changed.connect(lambda v: self._set("size_pct", v))
        f.addRow(tr("גודל אות", "Letter size"), self.pct)
        f.addRow(tr("גודל מדויק", "Exact size"), self.auto)
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
        self.pct.setEnabled(L.size is None)
        self.pct.set_value(L.size_pct)
        raised = L.mode == "raised"
        self.depth_lbl.setText(tr("גובה בליטה", "Raise height") if raised else tr("עומק", "Depth"))
        self.depth.blockSignals(True)
        self.depth.setValue(L.raise_height if raised else L.depth)
        self.depth.blockSignals(False)
        res = self.ctl.result
        dev = self.ctl.developer_mode
        for w in (self.auto, self.size):
            w.setVisible(dev)                  # exact mm only for the developer; customers use %
        if res and res.ok:
            lo, hi = res.boldness_range
            self.extra.blockSignals(True)
            self.extra.setRange(lo, hi)        # never offer a weight that would break the letters
            self.extra.setValue(min(max(L.extra_weight, lo), hi))
            self.extra.blockSignals(False)
            self.extra.setToolTip(tr(f"טווח בטוח לגופן ולגודל הנוכחיים: {lo:+.2f} עד {hi:+.2f} מ\"מ",
                                     f"Safe range for this font and size: {lo:+.2f} to {hi:+.2f} mm"))
            area = res.style.legend_area - 2 * L.margin
            if res.letter_height:
                self.size.blockSignals(True)
                self.size.setMaximum(round(area, 1))
                self.size.blockSignals(False)
            self.size_info.setText(tr(
                f"גובה האות בפועל: {res.letter_height:.1f} מ\"מ · מקסימום לשטח: {area:.1f} מ\"מ · עובי מותר {lo:+.2f}..{hi:+.2f}",
                f"Letter height: {res.letter_height:.1f} mm · max for area: {area:.1f} mm · weight {lo:+.2f}..{hi:+.2f}"))


# ---------------------------------------------------------------------------------------------
THUMBS = Path(__file__).resolve().parent.parent / "assets" / "thumbs"


class ThumbCard(QFrame):
    """Selectable card with a thumbnail rendered from the real geometry."""

    clicked = Signal(str)

    def __init__(self, key: str, title: str, image: Path, img_h: int = 92):
        super().__init__()
        from PySide6.QtGui import QPixmap

        self.key = key
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(4)
        pic = QLabel()
        pic.setAlignment(Qt.AlignCenter)
        pm = QPixmap(str(image))
        if not pm.isNull():
            pic.setPixmap(pm.scaledToHeight(img_h, Qt.SmoothTransformation))
        v.addWidget(pic)
        t = QLabel(title)
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("font-weight: 600;")
        v.addWidget(t)

    def set_selected(self, on: bool) -> None:
        self.setProperty("selected", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, e):  # noqa: N802
        self.clicked.emit(self.key)


class SliderRow(QWidget):
    """Label + value box + slider (like a numeric field with a scrubber)."""

    changed = Signal(float)

    def __init__(self, lo: float, hi: float, step: float, decimals: int, suffix: str):
        super().__init__()
        self.lo, self.step = lo, step
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.spin = dspin(lo, hi, step, lo, decimals, suffix)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, int(round((hi - lo) / step)))
        lay.addWidget(self.spin)
        lay.addWidget(self.slider)
        self.slider.valueChanged.connect(lambda i: self.spin.setValue(lo + i * step))
        self.spin.valueChanged.connect(self._spin)

    def _spin(self, v: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(int(round((v - self.lo) / self.step)))
        self.slider.blockSignals(False)
        self.changed.emit(v)

    def set_value(self, v: float) -> None:
        for w in (self.spin, self.slider):
            w.blockSignals(True)
        self.spin.setValue(v)
        self.slider.setValue(int(round((v - self.lo) / self.step)))
        for w in (self.spin, self.slider):
            w.blockSignals(False)


def card_grid(cards: list[QWidget], cols: int = 2) -> QWidget:
    w = QWidget()
    g = QGridLayout(w)
    g.setContentsMargins(0, 0, 0, 0)
    g.setSpacing(8)
    for i, c in enumerate(cards):
        g.addWidget(c, i // cols, i % cols)
    return w


class KeycapPage(Page):
    NAMES = {"standard": ("Standard", "רגיל"), "low_profile": ("Low profile", "נמוך"), "thocky": ("Thocky", "עבה")}

    def __init__(self, ctl: ProjectController):
        super().__init__(tr("כובעי מקשים", "Keycaps"))
        self.ctl = ctl
        self.cards: dict[str, ThumbCard] = {}
        for sid in KEYCAP_STYLES:
            en, he = self.NAMES[sid]
            c = ThumbCard(sid, tr(he, en), THUMBS / f"keycap_{sid}.png", 70)
            c.clicked.connect(self._pick)
            self.cards[sid] = c
        self.add(card_grid(list(self.cards.values()), 3))
        self.section(tr("גובה הכובע", "Keycap height"))
        self.height = SliderRow(5.0, 12.3, 0.1, 1, " mm")
        self.height.changed.connect(self._height)
        self.add(self.height)
        self.info = self.hint("")
        self.hint(tr("Thocky משנה את המבנה; הצליל בפועל ייקבע רק בבדיקה פיזית.",
                     "Thocky changes the structure; actual sound needs a physical test."))
        self.finish()
        ctl.changed.connect(self.refresh)
        self.refresh()

    def _pick(self, sid: str) -> None:
        self.ctl.project.keycap_style = sid
        self.ctl.project.keycap_height = None
        self.ctl.touch()

    def _height(self, v: float) -> None:
        st = KEYCAP_STYLES[self.ctl.project.keycap_style]
        self.ctl.project.keycap_height = None if v >= st.height - 1e-6 else v
        self.ctl.touch()

    def refresh(self) -> None:
        from ..config.mechanical import min_keycap_height

        p = self.ctl.project
        st = KEYCAP_STYLES[p.keycap_style]
        for sid, c in self.cards.items():
            c.set_selected(sid == p.keycap_style)
        lo = round(min_keycap_height(st) + 0.05, 1)
        for w in (self.height.spin, self.height.slider):
            w.blockSignals(True)
        self.height.spin.setRange(lo, st.height)
        for w in (self.height.spin, self.height.slider):
            w.blockSignals(False)
        self.height.set_value(p.keycap_height or st.height)
        self.info.setText(tr(f"טווח מותר: {lo:.1f}–{st.height:.2f} מ\"מ (המתג קובע את המינימום)",
                             f"Allowed: {lo:.1f}–{st.height:.2f} mm (minimum set by the switch)"))


# ---------------------------------------------------------------------------------------------
class BodyPage(Page):
    TEX = [("smooth", "חלק", "Smooth"), ("diamond", "יהלומים", "Diamond"), ("ribs", "פסים", "Ribs"),
           ("fluted", "חריצים", "Fluted"), ("dots", "נקודות", "Dots"), ("chevron", "זיגזג", "Chevron")]

    def __init__(self, ctl: ProjectController):
        super().__init__(tr("גוף וטקסטורות", "Body & textures"))
        self.ctl = ctl
        self.section(tr("טקסטורה חיצונית", "Outside texture"))
        self.cards: dict[str, ThumbCard] = {}
        for key, he, en in self.TEX:
            c = ThumbCard(key, tr(he, en), THUMBS / f"texture_{key}.png", 84)
            c.clicked.connect(lambda k: self._set("texture", k))
            self.cards[key] = c
        self.add(card_grid(list(self.cards.values()), 2))
        f = self.form()
        self.tdepth = dspin(0.2, 0.8, 0.05, ctl.project.body.texture_depth)
        self.tdepth.valueChanged.connect(lambda v: self._set("texture_depth", v))
        self.tunit = dspin(1.5, 5.0, 0.1, ctl.project.body.texture_unit)
        self.tunit.valueChanged.connect(lambda v: self._set("texture_unit", v))
        f.addRow(tr("עומק הטקסטורה", "Texture depth"), self.tdepth)
        f.addRow(tr("גודל הדוגמה", "Pattern size"), self.tunit)
        self.section(tr("גובה שפת הגוף", "Body rim height"))
        self.rim = SliderRow(17.6, 22.0, 0.1, 1, " mm")
        self.rim.changed.connect(lambda v: self._set("rim_height", None if v <= 17.64 else v))
        self.add(self.rim)
        self.hint(tr("שפה גבוהה יותר מסתירה חלק גדול יותר מהכובע. הבדיקות מוודאות שהכובע לא נתקע בלחיצה.",
                     "A taller rim hides more of the keycap; checks make sure keys never rub when pressed."))
        self.section(tr("חיבור בין המקשים", "Joint between keys"))
        self.joint = Segmented([("grooved", tr("שקע עדין", "Grooved")), ("smooth", tr("חלק", "Smooth"))])
        self.joint.changed.connect(lambda v: self._set("joint", v))
        self.add(self.joint)
        f2 = self.form()
        self.depth = dspin(0.3, 1.2, 0.1, ctl.project.body.groove_depth)
        self.depth.valueChanged.connect(lambda v: self._set("groove_depth", v))
        f2.addRow(tr("עומק השקע", "Groove depth"), self.depth)
        self.finish()
        ctl.changed.connect(self.refresh)
        self.refresh()

    def _set(self, attr: str, v) -> None:
        if getattr(self.ctl.project.body, attr) != v:
            setattr(self.ctl.project.body, attr, v)
            self.ctl.touch()

    def refresh(self) -> None:
        b = self.ctl.project.body
        for k, c in self.cards.items():
            c.set_selected(k == b.texture)
        for w, v in ((self.tdepth, b.texture_depth), (self.tunit, b.texture_unit), (self.depth, b.groove_depth)):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        self.tdepth.setEnabled(b.texture != "smooth")
        self.tunit.setEnabled(b.texture != "smooth")
        self.rim.set_value(b.rim_height or 17.64)
        self.joint.set_value(b.joint)
        self.depth.setEnabled(b.joint == "grooved")


# ---------------------------------------------------------------------------------------------
class ColorsPage(Page):
    def __init__(self, ctl: ProjectController):
        super().__init__(tr("צבעים", "Colours"))
        self.ctl = ctl
        c = ctl.project.colors
        self.blank = QCheckBox(tr("כובעים ריקים (ללא אותיות)", "Blank caps (no letters)"))
        self.blank.toggled.connect(self._blank)
        self.add(self.blank)
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
        self.hint(tr("טיפ: לחיצה על גוף, כובע או אות במודל התלת־ממדי בוחרת אותו לצביעה.",
                     "Tip: click the body, a keycap or a letter in the 3D view to recolour it."))
        self.finish()
        ctl.changed.connect(self.refresh)
        self.refresh()

    def _set(self, attr: str, v: str) -> None:
        setattr(self.ctl.project.colors, attr, v)
        self.ctl.touch()

    def _blank(self, on: bool) -> None:
        self.ctl.project.blank_legends = on
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
        self.blank.blockSignals(True)
        self.blank.setChecked(p.blank_legends)
        self.blank.blockSignals(False)
        self.legend.setEnabled(not p.blank_legends)
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


# ---------------------------------------------------------------------------------------------
def svg_pixmap(svg: str, size: int = 44):
    from PySide6.QtCore import QByteArray
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtSvg import QSvgRenderer

    r = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    r.render(p)
    p.end()
    return pm


class SymbolsPage(Page):
    """Built-in symbol library + SVG import (spec 19-21). Symbols use the same modes and colours as letters."""

    def __init__(self, ctl: ProjectController):
        super().__init__(tr("סמלים ו־SVG", "Symbols & SVG"))
        from ..geometry.symbols import SYMBOLS

        self.ctl = ctl
        self.picked: tuple[str, str] | None = None      # (kind, value)
        self.hint(tr("1. בחר סמל  2. בחר מקש למטה (או בלי מקש)  3. לחץ על פעולה.",
                     "1. Pick a symbol  2. pick a key below (optional)  3. choose an action."))
        self.grid = QGridLayout()
        self.grid.setSpacing(6)
        self.buttons: dict[str, QPushButton] = {}
        self._icons_built = False
        self._symbols = SYMBOLS
        self.lay.addLayout(self.grid)
        imp = QPushButton(tr("ייבוא קובץ SVG…", "Import SVG file…"))
        imp.clicked.connect(self._import_svg)
        self.add(imp)
        self.svg_info = self.hint("")
        self.section(tr("מקשים (לפי סדר המוצר)", "Keys (product order)"))
        self.strip = KeyStrip(ctl)
        self.add(self.strip)
        row = QHBoxLayout()
        self.apply_btn = QPushButton(tr("החל על המקש שנבחר", "Apply to selected key"))
        self.apply_btn.setObjectName("Primary")
        self.apply_btn.clicked.connect(self._apply)
        self.left_btn = QPushButton(tr("+ מקש חדש משמאל", "+ New key left"))
        self.right_btn = QPushButton(tr("+ מקש חדש מימין", "+ New key right"))
        self.left_btn.clicked.connect(lambda: self._new("left"))
        self.right_btn.clicked.connect(lambda: self._new("right"))
        row.addWidget(self.apply_btn)
        self.lay.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(self.right_btn)
        row2.addWidget(self.left_btn)
        self.lay.addLayout(row2)
        self.clear_btn = QPushButton(tr("הסר סמל מהמקש (מקש ריק)", "Clear symbol (blank key)"))
        self.clear_btn.clicked.connect(self._clear)
        self.add(self.clear_btn)
        self.status = self.hint("")
        self.finish()
        ctl.changed.connect(self.refresh)
        self.refresh()

    def showEvent(self, e):  # noqa: N802 - build the icon grid lazily (first time the page is opened)
        if not self._icons_built:
            from ..geometry.symbols import sketch_to_svg, symbol_sketch

            for i, (sid, (he, en, _)) in enumerate(self._symbols.items()):
                b = QPushButton()
                b.setCheckable(True)
                b.setFixedSize(58, 58)
                b.setIconSize(QSize(40, 40))
                b.setIcon(QIcon(svg_pixmap(sketch_to_svg(symbol_sketch(sid)))))
                b.setToolTip(tr(he, en))
                b.clicked.connect(lambda _=False, s=sid: self._pick(("symbol", s)))
                self.grid.addWidget(b, i // 5, i % 5)
                self.buttons[sid] = b
            self._icons_built = True
        super().showEvent(e)

    def _pick(self, what: tuple[str, str]) -> None:
        self.picked = what
        for sid, b in self.buttons.items():
            b.setChecked(what == ("symbol", sid))
        self.refresh()

    def _import_svg(self) -> None:
        from ..geometry.symbols import SvgImportError, svg_sketch

        path, _ = QFileDialog.getOpenFileName(self, tr("בחר קובץ SVG", "Choose SVG"), "", "SVG (*.svg)")
        if not path:
            return
        try:
            _, warns = svg_sketch(path)
        except SvgImportError as e:
            self.svg_info.setObjectName("Error")
            self.svg_info.setText(str(e))
            self.svg_info.style().polish(self.svg_info)
            return
        self.svg_info.setObjectName("Warn" if warns else "Ok")
        self.svg_info.setText(f"{Path(path).name}: " + (" · ".join(w.split(' / ')[0] for w in warns) or tr("תקין ✓", "OK ✓")))
        self.svg_info.style().polish(self.svg_info)
        self._pick(("svg", path))

    def _apply(self) -> None:
        from ..text.engine import set_key_content

        if self.picked and self.strip.current:
            set_key_content(self.ctl.project, self.strip.current, *self.picked)
            self.ctl.touch()

    def _new(self, side: str) -> None:
        from ..text.engine import insert_key_visual

        if self.picked:
            k = insert_key_visual(self.ctl.project, side, self.strip.current, *self.picked)
            self.strip.current = k.id
            self.ctl.touch()

    def _clear(self) -> None:
        from ..text.engine import set_key_content

        if self.strip.current:
            set_key_content(self.ctl.project, self.strip.current, "blank", "")
            self.ctl.touch()

    def refresh(self) -> None:
        self.strip.refresh()
        has_key = self.strip.current is not None
        self.apply_btn.setEnabled(bool(self.picked) and has_key)
        self.left_btn.setEnabled(bool(self.picked))
        self.right_btn.setEnabled(bool(self.picked))
        self.clear_btn.setEnabled(has_key)
        n = len(self.ctl.project.keys)
        self.status.setText(tr(f"{n} מקשים מתוך 10", f"{n} of 10 keys"))

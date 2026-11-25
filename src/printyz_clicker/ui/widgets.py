"""Small reusable widgets."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup, QColorDialog, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

FILAMENT_SWATCHES = [
    "#FFFFFF", "#F2F2F2", "#9AA0A6", "#2B2B2B", "#000000", "#C62828", "#FF6F00", "#FFD400",
    "#2E7D32", "#00A3A3", "#1E5BD8", "#6A1B9A", "#E91E63", "#8D6E63", "#F5DEB3", "#C0C0C0",
]


class Page(QScrollArea):
    """Scrollable settings page with a title."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("SidePanel")
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(18, 14, 18, 18)
        self.lay.setSpacing(8)
        t = QLabel(title)
        t.setObjectName("PageTitle")
        self.lay.addWidget(t)
        self.setWidget(inner)
        self._end_added = False

    def section(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("Section")
        self.lay.addWidget(lab)
        return lab

    def hint(self, text: str, name: str = "Hint") -> QLabel:
        lab = QLabel(text)
        lab.setObjectName(name)
        lab.setWordWrap(True)
        self.lay.addWidget(lab)
        return lab

    def form(self) -> QFormLayout:
        f = QFormLayout()
        f.setLabelAlignment(Qt.AlignLeading | Qt.AlignVCenter)
        f.setHorizontalSpacing(14)
        f.setVerticalSpacing(8)
        self.lay.addLayout(f)
        return f

    def add(self, w):
        self.lay.addWidget(w)
        return w

    def finish(self) -> None:
        if not self._end_added:
            self.lay.addStretch(1)
            self._end_added = True


class Segmented(QWidget):
    """Exclusive button row; emits the selected value."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent: QWidget | None = None, per_row: int = 4):
        super().__init__(parent)
        from PySide6.QtWidgets import QGridLayout

        lay = QGridLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for value, label in options:
            b = QPushButton(label)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, v=value: self.changed.emit(v))
            self.group.addButton(b)
            i = len(self.buttons)
            lay.addWidget(b, i // per_row, i % per_row)
            self.buttons[value] = b
        lay.setColumnStretch(per_row, 1)

    def set_value(self, value: str) -> None:
        b = self.buttons.get(value)
        if b:
            b.blockSignals(True)
            b.setChecked(True)
            b.blockSignals(False)

    def set_enabled_value(self, value: str, enabled: bool, tooltip: str = "") -> None:
        b = self.buttons[value]
        b.setEnabled(enabled)
        b.setToolTip(tooltip)


class ColorButton(QPushButton):
    """Colour picker: click opens quick filament swatches + full dialog."""

    picked = Signal(str)

    def __init__(self, color: str = "#FFFFFF", parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumWidth(110)
        self.clicked.connect(self._open)
        self.set_color(color)

    def set_color(self, color: str) -> None:
        self._color = color.upper()
        fg = "#000000" if QColor(color).lightness() > 140 else "#FFFFFF"
        names = dict((h.upper(), n) for h, n in (self.restrict or []))
        name = names.get(self._color)
        self.setText(name or self._color)
        font = "" if name else "font-family: Consolas, monospace;"     # names in the normal UI font
        self.setStyleSheet(f"QPushButton {{ background: {color}; color: {fg}; border: 1px solid #C9CED6; "
                           f"border-radius: 8px; padding: 7px 12px; {font} }}"
                           f"QPushButton:disabled {{ background: #F1F3F6; color: #A9AEB6; }}")

    def clear(self, text: str = "—") -> None:
        self._color = ""
        self.setText(text)
        self.setStyleSheet("QPushButton { background: #F1F3F6; color: #A9AEB6; border: 1px solid #E2E5EA; "
                           "border-radius: 8px; padding: 7px 12px; }")

    def color(self) -> str:
        return self._color

    # customer edition: only these (hex, name) filaments, no free colour dialog
    restrict: list[tuple[str, str]] | None = None

    def _open(self) -> None:
        pop = SwatchPopup(self._color, self, self.restrict)
        pop.picked.connect(self._apply)
        pos = self.mapToGlobal(self.rect().bottomLeft())
        pop.move(pos)
        pop.show()

    def _apply(self, c: str) -> None:
        self.set_color(c)
        self.picked.emit(c.upper())


class SwatchPopup(QFrame):
    picked = Signal(str)

    def __init__(self, current: str, parent: QWidget | None = None,
                 restrict: list[tuple[str, str]] | None = None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("Card")
        self.setStyleSheet("#Card { background: white; border: 1px solid #D5DAE1; border-radius: 10px; }")
        lay = QVBoxLayout(self)
        self._current = current
        if restrict is not None:
            # inventory filaments only, with their names - no free colour choice
            for hex_, name in restrict:
                b = QPushButton(f"  {name}")
                fg = "#000000" if QColor(hex_).lightness() > 140 else "#FFFFFF"
                border = "2px solid #2F6FED" if hex_.upper() == current.upper() else "1px solid #C9CED6"
                b.setStyleSheet(f"QPushButton {{ background:{hex_}; color:{fg}; border:{border}; border-radius:8px; "
                                f"padding:6px 14px; text-align:left; }}")
                b.clicked.connect(lambda _=False, col=hex_: self._pick(col))
                lay.addWidget(b)
            return
        grid = QHBoxLayout()
        rows = [FILAMENT_SWATCHES[:8], FILAMENT_SWATCHES[8:]]
        for row in rows:
            h = QHBoxLayout()
            for c in row:
                b = QPushButton()
                b.setFixedSize(26, 26)
                border = "2px solid #2F6FED" if c.upper() == current.upper() else "1px solid #C9CED6"
                b.setStyleSheet(f"background:{c}; border:{border}; border-radius:13px;")
                b.setToolTip(c)
                b.clicked.connect(lambda _=False, col=c: self._pick(col))
                h.addWidget(b)
            lay.addLayout(h)
        more = QPushButton("…")
        more.clicked.connect(self._dialog)
        grid.addWidget(more)
        lay.addLayout(grid)

    def _pick(self, c: str) -> None:
        self.picked.emit(c)
        self.close()

    def _dialog(self) -> None:
        self.hide()
        c = QColorDialog.getColor(QColor(self._current), self.parentWidget())
        if c.isValid():
            self.picked.emit(c.name().upper())
        self.close()


def dspin(lo: float, hi: float, step: float, value: float, decimals: int = 2, suffix: str = " mm") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    s.setValue(value)
    s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s

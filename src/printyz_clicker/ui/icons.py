"""Uniform line icons (original simple SVG shapes), rendered to QIcon."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_P = {
    "name": '<path d="M4 7V5h16v2M9 19h6M12 5v14"/>',
    "font": '<path d="M5 19 11 5h2l6 14M8 13h8"/>',
    "legend": '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 15l3-7 3 7M10 13h4"/>',
    "keycap": '<path d="M5 18 7 6h10l2 12z"/><path d="M8.5 9h7"/>',
    "body": '<rect x="3" y="8" width="18" height="10" rx="2.5"/><path d="M9 8v10M15 8v10"/>',
    "palette": '<path d="M12 3a9 9 0 1 0 0 18c1.5 0 2-1 2-2s-1-1.5-1-2.5 1-1.5 2-1.5h2a4 4 0 0 0 4-4c0-4.5-4-8-9-8z"/>'
               '<circle cx="7.5" cy="11" r="1"/><circle cx="10" cy="7" r="1"/><circle cx="15" cy="7.5" r="1"/>',
    "symbol": '<path d="M12 4l2.4 5 5.6.6-4.2 3.8 1.2 5.6L12 16.2 7 19l1.2-5.6L4 9.6 9.6 9z"/>',
    "keychain": '<circle cx="12" cy="7" r="3.5"/><path d="M7 11h10v8a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2z"/>',
    "texture": '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 9l5-5M4 15l11-11M9 20l11-11M15 20l5-5"/>',
    "mech": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>',
    "export": '<path d="M12 3v12M7 10l5 5 5-5M4 19h16"/>',
    "open": '<path d="M3 7h6l2 2h10v10H3z"/>',
    "save": '<path d="M5 3h11l3 3v15H5z"/><path d="M8 3v5h7V3M8 21v-6h8v6"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "reset": '<path d="M4 12a8 8 0 1 0 2.3-5.6M4 4v4h4"/>',
}


def icon(name: str, color: str = "#3A4250", size: int = 22) -> QIcon:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{_P[name]}</svg>')
    r = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    r.render(p)
    p.end()
    return QIcon(pm)

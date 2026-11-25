"""Entry point: python -m printyz_clicker.ui"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .i18n import set_language
from .main_window import MainWindow
from .theme import STYLESHEET, light_palette


def _switch_language(lang: str, old: MainWindow) -> None:
    set_language(lang)
    win = MainWindow(fonts=old.fonts, project=old.ctl.project, on_language=_switch_language)
    win.resize(old.size())
    win.show()
    old.close()
    QApplication.instance()._win = win  # keep a reference


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PRINTYZ Clicker Studio")
    app.setOrganizationName("PRINTYZ")
    from pathlib import Path

    from PySide6.QtGui import QIcon

    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent.parent / "assets" / "printyz.png")))
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    app.setStyleSheet(STYLESHEET)
    set_language("he")
    win = MainWindow(on_language=_switch_language)
    win.show()
    app._win = win
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

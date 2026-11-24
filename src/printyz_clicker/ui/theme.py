"""Light, professional theme (spec 30-32)."""

ACCENT = "#2F6FED"
ACCENT_DARK = "#2459C4"
BG = "#F4F5F7"
PANEL = "#FFFFFF"
BORDER = "#E2E5EA"
TEXT = "#1F2328"
MUTED = "#6B7280"
ERROR = "#C62828"
WARN = "#B26A00"
OK = "#1E7D3A"

STYLESHEET = f"""
QWidget {{ font-family: 'Segoe UI', 'Rubik', 'Arial'; font-size: 10.5pt; color: {TEXT}; }}
QMainWindow, #Central {{ background: {BG}; }}
#TopBar {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
#Brand {{ font-size: 15pt; font-weight: 700; color: {TEXT}; }}
#BrandAccent {{ font-size: 15pt; font-weight: 700; color: {ACCENT}; }}
#NavList {{ background: {PANEL}; border: none; outline: 0; padding: 8px 6px; }}
#NavList::item {{ padding: 9px 10px; margin: 2px 0; border-radius: 8px; color: {TEXT}; }}
#NavList::item:hover {{ background: #EEF2FB; }}
#NavList::item:selected {{ background: #E3ECFD; color: {ACCENT_DARK}; font-weight: 600; }}
#NavList::item:disabled {{ color: #A9AEB6; }}
#SidePanel {{ background: {PANEL}; }}
#PageTitle {{ font-size: 14pt; font-weight: 700; padding: 4px 0 2px 0; }}
#Section {{ font-size: 10pt; font-weight: 700; color: {MUTED}; padding-top: 10px; }}
#Hint {{ color: {MUTED}; font-size: 9.5pt; }}
#Error {{ color: {ERROR}; font-weight: 600; }}
#Warn {{ color: {WARN}; }}
#Ok {{ color: {OK}; font-weight: 600; }}
#Card {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; }}
#Card[selected="true"] {{ border: 2px solid {ACCENT}; background: #F5F8FF; }}
#ViewerFrame {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
  background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 8px; min-height: 22px; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
#NameInput {{ font-size: 18pt; padding: 10px 12px; }}
QPushButton {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; padding: 7px 14px; }}
QPushButton:hover {{ background: #F0F3F8; }}
QPushButton:checked {{ background: #E3ECFD; border: 1px solid {ACCENT}; color: {ACCENT_DARK}; font-weight: 600; }}
QPushButton#Primary {{ background: {ACCENT}; color: white; border: none; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {ACCENT_DARK}; }}
QPushButton#Chip {{ border-radius: 14px; padding: 4px 10px; min-width: 26px; font-size: 12pt; }}
QPushButton#ViewBtn {{ padding: 5px 10px; font-size: 9.5pt; }}
QCheckBox {{ spacing: 8px; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 16px; margin: -6px 0; border-radius: 8px; }}
QScrollArea {{ border: none; background: transparent; }}
QStatusBar {{ background: {PANEL}; border-top: 1px solid {BORDER}; }}
QComboBox QAbstractItemView {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};
  selection-background-color: #E3ECFD; selection-color: {ACCENT_DARK}; outline: 0; padding: 4px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid #B8BEC7; border-radius: 4px; background: {PANEL}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}
QToolTip {{ background: {TEXT}; color: white; border: none; padding: 6px; }}
"""


def light_palette():
    """Explicit light palette so Windows dark mode never produces dark popups / unreadable text."""
    from PySide6.QtGui import QColor, QPalette

    pal = QPalette()
    roles = {
        QPalette.Window: BG, QPalette.WindowText: TEXT, QPalette.Base: PANEL, QPalette.AlternateBase: "#F7F8FA",
        QPalette.ToolTipBase: TEXT, QPalette.ToolTipText: "#FFFFFF", QPalette.Text: TEXT, QPalette.Button: PANEL,
        QPalette.ButtonText: TEXT, QPalette.BrightText: "#FFFFFF", QPalette.Highlight: ACCENT,
        QPalette.HighlightedText: "#FFFFFF", QPalette.PlaceholderText: "#9AA0A8", QPalette.Link: ACCENT,
    }
    for role, col in roles.items():
        pal.setColor(QPalette.All, role, QColor(col))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor("#A9AEB6"))
    return pal

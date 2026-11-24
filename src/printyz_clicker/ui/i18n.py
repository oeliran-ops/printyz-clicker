"""Minimal bilingual helper: tr("עברית", "English") returns the active language."""

from __future__ import annotations

_LANG = "he"


def set_language(lang: str) -> None:
    global _LANG
    _LANG = "en" if lang == "en" else "he"


def language() -> str:
    return _LANG


def is_rtl() -> bool:
    return _LANG == "he"


def tr(he: str, en: str) -> str:
    return he if _LANG == "he" else en

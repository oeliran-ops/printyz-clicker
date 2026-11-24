"""Font registry: developer-managed list of fonts; customers see approved ones only."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fontTools.ttLib import TTFont


@dataclass
class FontEntry:
    id: str
    path: str
    family: str = ""
    category: str = "sans"
    approved: bool = False                 # visible to customers
    min_size: float = 6.0
    max_size: float = 20.0
    recommended_extra_weight: float = 0.0
    notes: str = ""                        # test-print notes
    supports_hebrew: bool = False          # filled by inspect()
    supports_latin: bool = False


def _candidate_default_fonts() -> list[tuple[str, str]]:
    """(id, path) of bold fonts with Hebrew coverage found on this machine."""
    win = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    cands = [
        ("default-bold", str(win / "arialbd.ttf")),
        ("default-bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("default-bold", "/Library/Fonts/Arial Bold.ttf"),
        ("default-regular", str(win / "arial.ttf")),
        ("default-regular", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    return [(i, p) for i, p in cands if Path(p).exists()]


@lru_cache(maxsize=64)
def font_cmap(path: str) -> frozenset[int]:
    f = TTFont(path, lazy=True, fontNumber=0)
    return frozenset(f.getBestCmap().keys())


def missing_glyphs(path: str, text: str) -> list[str]:
    cmap = font_cmap(path)
    return sorted({ch for ch in text if not ch.isspace() and ord(ch) not in cmap})


def inspect(entry: FontEntry) -> FontEntry:
    cmap = font_cmap(entry.path)
    entry.supports_hebrew = all(ord(c) in cmap for c in "אבגדהוזחטיכלמנסעפצקרשתךםןףץ")
    entry.supports_latin = all(ord(c) in cmap for c in "ABCabc0123")
    if not entry.family:
        name = TTFont(entry.path, lazy=True)["name"]
        entry.family = str(name.getDebugName(1) or Path(entry.path).stem)
    return entry


@dataclass
class FontRegistry:
    fonts: dict[str, FontEntry] = field(default_factory=dict)

    @classmethod
    def default(cls, library_file: Optional[Path] = None) -> "FontRegistry":
        reg = cls()
        for fid, path in _candidate_default_fonts():
            if fid not in reg.fonts:
                reg.fonts[fid] = inspect(FontEntry(id=fid, path=path, approved=True))
        if library_file and library_file.exists():
            reg.load(library_file)
        return reg

    def add(self, entry: FontEntry) -> FontEntry:
        """Developer-only: register a TTF/OTF file."""
        if Path(entry.path).suffix.lower() not in (".ttf", ".otf"):
            raise ValueError("Only TTF / OTF fonts are supported")
        self.fonts[entry.id] = inspect(entry)
        return entry

    def resolve(self, font_id: str) -> FontEntry:
        if font_id in self.fonts:
            return self.fonts[font_id]
        if Path(font_id).exists():  # direct path (developer use)
            return inspect(FontEntry(id=font_id, path=font_id))
        raise KeyError(f"Font {font_id!r} is not registered")

    def customer_fonts(self) -> list[FontEntry]:
        return [f for f in self.fonts.values() if f.approved]

    def save(self, path: Path) -> None:
        path.write_text(json.dumps([asdict(f) for f in self.fonts.values()], ensure_ascii=False, indent=2), "utf-8")

    def load(self, path: Path) -> None:
        for d in json.loads(path.read_text("utf-8")):
            if Path(d["path"]).exists():
                self.fonts[d["id"]] = inspect(FontEntry(**d))
            else:
                print(f"[fonts] missing file for {d['id']}: {d['path']}", file=sys.stderr)

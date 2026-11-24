"""Single source of truth: the project data model.

The UI edits a Project; every engine (layout, geometry, preview, export) reads
the same Project. Nothing is recomputed separately per consumer.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Literal, Optional

from ..config.mechanical import DEFAULT_PROFILE, MechanicalProfile

SCHEMA_VERSION = 1

KeyKind = Literal["char", "symbol", "svg", "blank"]
KeySource = Literal["text", "extra"]
Direction = Literal["auto", "rtl", "ltr"]
LayoutStyle = Literal["row", "column", "grid", "wasd", "arrows", "custom"]
LegendMode = Literal["flush", "raised", "engraved"]
JointStyle = Literal["smooth", "grooved"]


def new_key_id() -> str:
    return "k_" + uuid.uuid4().hex[:8]


@dataclass
class KeySlot:
    id: str
    kind: KeyKind = "blank"
    value: str = ""                  # character, symbol id or svg path
    source: KeySource = "text"
    cap_color: Optional[str] = None  # per-key overrides (None = project default)
    legend_color: Optional[str] = None


@dataclass
class LayoutSpec:
    style: LayoutStyle = "row"
    rows: int = 2
    cols: int = 3
    key_direction: Direction = "auto"      # order of keys, independent of text direction
    fill_empty_with_blank: bool = False    # grid: put blank keys in free cells
    custom_cells: dict[str, list[int]] = field(default_factory=dict)  # key_id -> [row, col]


@dataclass
class LetteringSpec:
    mode: LegendMode = "flush"
    font_id: str = "default-bold"
    extra_weight: float = 0.0       # mm of real outline growth (negative = thinner, min -0.3)
    size: Optional[float] = None    # requested height (mm) of the tallest glyph; None = largest that fits
    uniform: bool = True            # one scale for all keys (consistent letter size)
    size_pct: float = 100.0         # % of the largest size that fits (used when size is None)
    margin: float = 1.25            # mm from flat top-face edge (allowed 1.0 - 3.5)
    offset_x: float = 0.0
    offset_y: float = 0.0
    depth: float = 0.60             # flush inlay / engraving depth
    raise_height: float = 0.80      # raised legend height


@dataclass
class BodyDesign:
    joint: JointStyle = "grooved"
    groove_depth: float = 0.80
    texture: str = "smooth"              # smooth | diamond | ribs | fluted | dots | chevron
    texture_depth: float = 0.5
    texture_unit: float = 2.4            # pattern size (mm)
    rim_height: Optional[float] = None   # body height override (None = calibrated 17.64)


@dataclass
class KeychainSpec:
    enabled: bool = False
    side: Literal["top", "bottom", "left", "right"] = "top"
    offset: float = 0.0          # along the side, from the body centre
    hole_diameter: float = 5.2
    width: float = 12.0
    length: float = 9.0          # from body surface
    thickness: float = 4.0
    corner_radius: float = 3.0
    root_radius: float = 2.0     # fillet where the tab meets the body


@dataclass
class ColorSpec:
    body: str = "#F2F2F2"
    cap: str = "#2B2B2B"
    legend: str = "#FFFFFF"


@dataclass
class Project:
    name: str = "Untitled"
    text: str = ""
    text_direction: Direction = "auto"
    spaces_as_blank: bool = True
    keys: list[KeySlot] = field(default_factory=list)
    layout: LayoutSpec = field(default_factory=LayoutSpec)
    lettering: LetteringSpec = field(default_factory=LetteringSpec)
    keycap_style: str = "standard"
    keycap_height: Optional[float] = None   # None = style default
    blank_legends: bool = False             # "Blank": caps without letters
    body: BodyDesign = field(default_factory=BodyDesign)
    keychain: KeychainSpec = field(default_factory=KeychainSpec)
    colors: ColorSpec = field(default_factory=ColorSpec)
    mechanical: MechanicalProfile = field(default_factory=lambda: DEFAULT_PROFILE)

    # ---- convenience -------------------------------------------------
    def key_by_id(self, key_id: str) -> KeySlot:
        for k in self.keys:
            if k.id == key_id:
                return k
        raise KeyError(key_id)

    def cap_color(self, key: KeySlot) -> str:
        return key.cap_color or self.colors.cap

    def legend_color(self, key: KeySlot) -> str:
        return key.legend_color or self.colors.legend

    # ---- serialisation -------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["mechanical"] = self.mechanical.to_dict()
        d["schema_version"] = SCHEMA_VERSION
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        def build(klass, data):
            names = {f.name for f in fields(klass)}
            return klass(**{k: v for k, v in (data or {}).items() if k in names})

        return cls(
            name=d.get("name", "Untitled"),
            text=d.get("text", ""),
            text_direction=d.get("text_direction", "auto"),
            spaces_as_blank=d.get("spaces_as_blank", True),
            keys=[build(KeySlot, k) for k in d.get("keys", [])],
            layout=build(LayoutSpec, d.get("layout")),
            lettering=build(LetteringSpec, d.get("lettering")),
            keycap_style=d.get("keycap_style", "standard"),
            keycap_height=d.get("keycap_height"),
            blank_legends=d.get("blank_legends", False),
            body=build(BodyDesign, d.get("body")),
            keychain=build(KeychainSpec, d.get("keychain")),
            colors=build(ColorSpec, d.get("colors")),
            mechanical=MechanicalProfile.from_dict(d["mechanical"]) if "mechanical" in d else DEFAULT_PROFILE,
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

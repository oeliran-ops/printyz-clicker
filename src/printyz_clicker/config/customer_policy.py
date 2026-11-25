"""Customer policy: what the customer edition may use (developer-managed, stored as JSON).

The developer edits it in the "Customer settings" page; the customer edition bundles the file
and enforces it in every page. Empty lists mean "everything the developer has approved".
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass
class FilamentColor:
    name: str          # shown to the customer, e.g. "שחור מט"
    hex: str           # "#2B2B2B"
    in_stock: bool = True


@dataclass
class CustomerPolicy:
    colors: list[FilamentColor] = field(default_factory=lambda: [
        FilamentColor("לבן", "#F2F2F2"), FilamentColor("שחור", "#2B2B2B"), FilamentColor("צהוב", "#FFD400"),
    ])
    default_body: str = "#F2F2F2"
    default_cap: str = "#2B2B2B"
    default_legend: str = "#FFD400"
    fonts: list[str] = field(default_factory=list)          # font ids; empty = all approved fonts
    symbols_allowed: bool = True                            # built-in symbols (per-symbol visibility is
                                                            # the developer's symbol library)
    svg_import: bool = False
    textures: list[str] = field(default_factory=lambda: ["smooth", "diamond", "ribs", "fluted", "dots", "chevron"])
    keycap_styles: list[str] = field(default_factory=lambda: ["standard", "low_profile", "thocky"])
    layouts: list[str] = field(default_factory=lambda: ["row", "column", "grid", "wasd", "arrows", "custom"])
    legend_modes: list[str] = field(default_factory=lambda: ["flush", "raised", "engraved"])
    max_keys: int = 10
    keychain: bool = True
    per_key_colors: bool = True
    shop_name: str = "PRINTYZ"
    shop_contact: str = ""                                  # shown on the order screen (phone / email / site)

    # ---- helpers --------------------------------------------------------------------------
    def stock_colors(self) -> list[FilamentColor]:
        return [c for c in self.colors if c.in_stock]

    def color_allowed(self, hex_: str) -> bool:
        return hex_.upper() in {c.hex.upper() for c in self.stock_colors()}

    def color_name(self, hex_: str) -> str:
        for c in self.colors:
            if c.hex.upper() == hex_.upper():
                return c.name
        return hex_.upper()

    def violations(self, project) -> list[str]:
        """What in a project breaks this policy (used when the developer opens a customer order)."""
        out = []
        p = project
        cols = {p.colors.body, p.colors.cap, p.colors.legend}
        cols |= {k.cap_color for k in p.keys if k.cap_color} | {k.legend_color for k in p.keys if k.legend_color}
        for c in sorted(cols):
            if not self.color_allowed(c):
                out.append(f"צבע שאינו במלאי: {c} / colour not in stock")
        if self.fonts and p.lettering.font_id not in self.fonts:
            out.append(f"גופן לא מאושר: {p.lettering.font_id} / font not allowed")
        if p.body.texture not in self.textures:
            out.append(f"טקסטורה לא מאושרת: {p.body.texture}")
        if p.keycap_style not in self.keycap_styles:
            out.append(f"סוג כובע לא מאושר: {p.keycap_style}")
        if p.layout.style not in self.layouts:
            out.append(f"פריסה לא מאושרת: {p.layout.style}")
        if p.lettering.mode not in self.legend_modes:
            out.append(f"סגנון כיתוב לא מאושר: {p.lettering.mode}")
        if len(p.keys) > self.max_keys:
            out.append(f"{len(p.keys)} מקשים — המקסימום ללקוח {self.max_keys}")
        if p.keychain.enabled and not self.keychain:
            out.append("מחזיק מפתחות אינו מותר ללקוח")
        if any(k.kind == "svg" for k in p.keys) and not self.svg_import:
            out.append("SVG אינו מותר ללקוח")
        return out

    # ---- persistence -----------------------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CustomerPolicy":
        names = {f.name for f in fields(cls)}
        data = {k: v for k, v in d.items() if k in names}
        if "colors" in data:
            data["colors"] = [FilamentColor(**c) for c in data["colors"]]
        return cls(**data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1), "utf-8")

    @classmethod
    def load(cls, path: Path | None) -> "CustomerPolicy":
        if path and Path(path).exists():
            try:
                return cls.from_dict(json.loads(Path(path).read_text("utf-8")))
            except Exception:  # noqa: BLE001 - a broken file falls back to safe defaults
                pass
        return cls()

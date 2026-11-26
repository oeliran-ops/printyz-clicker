"""Automatic clicker pricing (spec 43). All amounts in ILS; the developer edits them in the admin."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass
class PricingRules:
    per_key: float = 6.0            # every key on the clicker
    base: float = 0.0               # fixed amount per clicker
    symbol_extra: float = 0.0       # per symbol key
    keychain_extra: float = 0.0
    texture_extra: float = 0.0      # any texture other than smooth
    raised_extra: float = 0.0       # raised lettering
    extra_colour: float = 0.0       # per colour beyond 3
    minimum: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "PricingRules":
        names = {f.name for f in fields(cls)}
        return cls(**{k: float(v) for k, v in (d or {}).items() if k in names})


def price(project, rules: PricingRules) -> tuple[float, list[tuple[str, float]]]:
    """Total and a readable breakdown (label, amount)."""
    p = project
    lines: list[tuple[str, float]] = []
    n = len(p.keys)
    if rules.base:
        lines.append(("מחיר בסיס", rules.base))
    lines.append((f"{n} מקשים × ₪{rules.per_key:g}", n * rules.per_key))
    sym = sum(1 for k in p.keys if k.kind in ("symbol", "svg"))
    if sym and rules.symbol_extra:
        lines.append((f"{sym} סמלים", sym * rules.symbol_extra))
    if p.keychain.enabled and rules.keychain_extra:
        lines.append(("מחזיק מפתחות", rules.keychain_extra))
    if p.body.texture != "smooth" and rules.texture_extra:
        lines.append(("טקסטורה", rules.texture_extra))
    if p.lettering.mode == "raised" and rules.raised_extra:
        lines.append(("אותיות בולטות", rules.raised_extra))
    cols = {p.colors.body.upper(), p.colors.cap.upper(), p.colors.legend.upper()}
    cols |= {k.cap_color.upper() for k in p.keys if k.cap_color} | {k.legend_color.upper() for k in p.keys if k.legend_color}
    extra = max(0, len(cols) - 3)
    if extra and rules.extra_colour:
        lines.append((f"{extra} צבעים נוספים", extra * rules.extra_colour))
    total = round(sum(a for _, a in lines), 2)
    if total < rules.minimum:
        lines.append(("השלמה למינימום", rules.minimum - total))
        total = rules.minimum
    return total, lines

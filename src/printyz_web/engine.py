"""Geometry worker: runs in a process pool (OCC is not thread safe). Builds the REAL clicker for the
browser preview and the order file. Everything from the browser is sanitised against the policy."""

from __future__ import annotations

import base64
from pathlib import Path

import numpy as np

from printyz_clicker.config.customer_policy import CustomerPolicy
from printyz_clicker.model.project import Project
from printyz_clicker.text.engine import sync_keys_from_text

from .pricing import PricingRules, price

_FONTS = None
_MESH_CACHE: dict[int, tuple[object, dict]] = {}


def fonts():
    global _FONTS
    if _FONTS is None:
        from printyz_clicker.fonts.registry import FontRegistry

        _FONTS = FontRegistry.default()
    return _FONTS


def warm_up() -> bool:
    import printyz_clicker.geometry.builder  # noqa: F401  (heavy OCC import)

    fonts()
    return True


def sanitize(data: dict, policy: CustomerPolicy) -> tuple[Project, list[str]]:
    """Build a Project from browser input, forcing every choice into what the policy allows."""
    errors: list[str] = []
    p = Project(name=str(data.get("name") or "Printyz")[:60])
    text = str(data.get("text", ""))[:40]
    sync_keys_from_text(p, text)
    # extra keys (blank / symbol) placed left / right in product order
    from printyz_clicker.geometry.symbols import SYMBOLS
    from printyz_clicker.text.engine import insert_key_visual

    for ex in data.get("extras", [])[:10]:
        kind = ex.get("kind")
        side = "left" if ex.get("side") == "left" else "right"
        if kind == "symbol" and policy.symbols_allowed and ex.get("value") in SYMBOLS:
            insert_key_visual(p, side, None, "symbol", ex["value"])
        elif kind == "blank":
            insert_key_visual(p, side, None, "blank", "")
    if len(p.keys) > policy.max_keys:
        errors.append(f"מקסימום {policy.max_keys} מקשים (יש {len(p.keys)}).")
    if not p.keys:
        errors.append("הקלידו שם או טקסט.")

    def pick(value, allowed, default):
        return value if value in allowed else (allowed[0] if allowed else default)

    lay = data.get("layout", {})
    p.layout.style = pick(lay.get("style", "row"), policy.layouts, "row")
    p.layout.rows = max(1, min(4, int(lay.get("rows", 2) or 2)))
    p.layout.cols = max(1, min(5, int(lay.get("cols", 3) or 3)))
    p.keycap_style = pick(data.get("keycap", "standard"), policy.keycap_styles, "standard")
    p.lettering.mode = pick(data.get("mode", "flush"), policy.legend_modes, "flush")
    p.lettering.size_pct = max(50.0, min(100.0, float(data.get("size_pct", 100) or 100)))
    allowed_fonts = policy.fonts or [f.id for f in fonts().customer_fonts()]
    p.lettering.font_id = pick(data.get("font"), allowed_fonts, "gf:rubik-700")
    p.body.texture = pick(data.get("texture", "smooth"), policy.textures, "smooth")
    kc = data.get("keychain") or {}
    p.keychain.enabled = bool(kc.get("enabled")) and policy.keychain
    p.keychain.side = kc.get("side") if kc.get("side") in ("top", "bottom", "left", "right") else "top"
    p.keychain.shape = kc.get("shape") if kc.get("shape") in ("rounded", "round", "square") else "rounded"
    cols = data.get("colors", {})
    p.colors.body = cols.get("body") if policy.color_allowed(cols.get("body", "")) else policy.default_body
    p.colors.cap = cols.get("cap") if policy.color_allowed(cols.get("cap", "")) else policy.default_cap
    p.colors.legend = cols.get("legend") if policy.color_allowed(cols.get("legend", "")) else policy.default_legend
    return p, errors


def _mesh_payload(part) -> dict:
    from printyz_clicker.geometry.builder import part_mesh

    src = part.mesh if part.mesh is not None else part.solid
    hit = _MESH_CACHE.get(id(src))
    if hit is None or hit[0] is not src:
        m = part_mesh(part, tol=0.05, ang=0.3)
        payload = {
            "positions": base64.b64encode(m.vertices.astype(np.float32).tobytes()).decode(),
            "indices": base64.b64encode(m.faces.astype(np.uint32).tobytes()).decode(),
        }
        if len(_MESH_CACHE) > 3000:
            _MESH_CACHE.clear()
        _MESH_CACHE[id(src)] = (src, payload)
        hit = _MESH_CACHE[id(src)]
    return {"name": part.name, "role": part.role, "color": part.color, "key_id": part.key_id} | hit[1]


def preview(data: dict, policy_d: dict, pricing_d: dict) -> dict:
    from printyz_clicker.geometry.builder import build_project
    from printyz_clicker.validation.checks import validate

    policy = CustomerPolicy.from_dict(policy_d)
    p, errors = sanitize(data, policy)
    total, lines = price(p, PricingRules.from_dict(pricing_d))
    out = {"errors": errors, "warnings": [], "price": total, "price_lines": lines, "parts": [],
           "keys": [{"id": k.id, "kind": k.kind, "value": k.value} for k in p.keys]}
    if errors:
        return out
    res = build_project(p, fonts(), include_switches=False)
    if not res.ok:
        out["errors"] = [e.split(" / ")[0] for e in res.errors]
        return out
    rep = validate(res, mesh_checks=False)
    out["errors"] = [c.detail for c in rep.errors]
    out["warnings"] = sorted({w.split(" / ")[0] for w in res.warnings})[:5]
    out["parts"] = [_mesh_payload(pt) for pt in res.parts]
    return out


def make_order_file(data: dict, policy_d: dict, pricing_d: dict, customer: dict, path: str) -> dict:
    """Validated order: project dict, summary, price; writes the .printyz-order file (with previews)."""
    from printyz_clicker.export.order import order_summary, write_order
    from printyz_clicker.geometry.builder import build_project

    policy = CustomerPolicy.from_dict(policy_d)
    p, errors = sanitize(data, policy)
    if errors:
        return {"errors": errors}
    res = build_project(p, fonts(), include_switches=False)
    if not res.ok:
        return {"errors": [e.split(" / ")[0] for e in res.errors]}
    total, lines = price(p, PricingRules.from_dict(pricing_d))
    write_order(Path(path), p, res, policy, customer)
    return {"errors": [], "project": p.to_dict(), "summary": order_summary(p, policy), "price": total,
            "price_lines": lines}

"""Regenerate the UI thumbnail images from the REAL geometry (run after geometry changes)."""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from printyz_clicker.config.mechanical import KEYCAP_STYLES
from printyz_clicker.geometry.builder import build_project
from printyz_clicker.model.project import Project
from printyz_clicker.render.preview import _gather, rasterize
from printyz_clicker.text.engine import sync_keys_from_text

OUT = Path("src/printyz_clicker/assets/thumbs")
BG = (0.93, 0.94, 0.96)


def crop(img, pad=6):
    mask = np.any(np.abs(img - np.array(BG)) > 0.01, axis=2)
    ys, xs = np.where(mask)
    return img[max(0, ys.min() - pad):ys.max() + pad, max(0, xs.min() - pad):xs.max() + pad]


for tex in ("smooth", "diamond", "ribs", "fluted", "dots", "chevron"):
    p = Project()
    sync_keys_from_text(p, "ab")
    p.body.texture = tex
    p.body.joint = "smooth"
    p.blank_legends = True
    p.colors.body = "#B9BEC6"
    r = build_project(p, include_switches=False)
    r.parts = [x for x in r.parts if x.role == "body"]
    tri, col = _gather(r, False, False)
    img = rasterize(tri, col, 28, -62, 520, 360, bg=BG, ss=3)
    plt.imsave(OUT / f"texture_{tex}.png", np.clip(crop(img), 0, 1))
    print("texture", tex)

for sid in KEYCAP_STYLES:
    p = Project()
    sync_keys_from_text(p, "A")
    p.keycap_style = sid
    p.colors.cap = "#4A5160"
    p.colors.legend = "#FFFFFF"
    r = build_project(p, include_switches=False)
    r.parts = [x for x in r.parts if x.role in ("cap", "legend")]
    tri, col = _gather(r, False, False)
    # same scale for every style: include an invisible reference point via fixed framing
    img = rasterize(tri, col, 12, -90, 300, 220, bg=BG, ss=3)
    plt.imsave(OUT / f"keycap_{sid}.png", np.clip(crop(img), 0, 1))
    print("keycap", sid)

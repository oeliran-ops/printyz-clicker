"""Slicer settings written into the Bambu Studio project (per object, so they travel with the
model regardless of the selected process preset). Developer-editable; stored as JSON.

Keys are Bambu Studio config keys. Values are strings exactly as Bambu Studio stores them.
"""

from __future__ import annotations

import json
from pathlib import Path

PROCESS_PRESET = "0.16mm High Quality @BBL A1"
BED_SIZE = (256.0, 256.0)            # Bambu Lab A1
PLATE_GAP_RATIO = 0.2                # Bambu Studio lays plates out with a 1/5 bed-width gap

DEFAULT_SETTINGS: dict[str, str] = {
    "layer_height": "0.16",
    "only_one_wall_first_layer": "1",
    "wall_generator": "arachne",
    "ironing_type": "top",
    "initial_layer_speed": "30",
    "initial_layer_infill_speed": "60",
    "outer_wall_speed": "60",
    "inner_wall_speed": "150",
    "small_perimeter_speed": "50%",
    "small_perimeter_threshold": "0",
    "sparse_infill_speed": "200",
    "internal_solid_infill_speed": "200",
    "vertical_shell_speed": "80%",
    "top_surface_speed": "100",
}

LABELS_HE = {
    "layer_height": "גובה שכבה", "only_one_wall_first_layer": "דופן אחת בשכבה ראשונה",
    "wall_generator": "מחולל דפנות", "ironing_type": "גיהוץ", "initial_layer_speed": "מהירות שכבה ראשונה",
    "initial_layer_infill_speed": "מילוי שכבה ראשונה", "outer_wall_speed": "דופן חיצונית",
    "inner_wall_speed": "דופן פנימית", "small_perimeter_speed": "היקפים קטנים",
    "small_perimeter_threshold": "סף היקף קטן", "sparse_infill_speed": "מילוי דליל",
    "internal_solid_infill_speed": "מילוי מלא פנימי", "vertical_shell_speed": "מעטפת אנכית",
    "top_surface_speed": "משטח עליון",
}


def load(path: Path | None) -> dict[str, str]:
    s = dict(DEFAULT_SETTINGS)
    if path and path.exists():
        try:
            s.update({k: str(v) for k, v in json.loads(path.read_text("utf-8")).items()})
        except Exception:  # noqa: BLE001 - fall back to defaults
            pass
    return s


def save(path: Path, settings: dict[str, str]) -> None:
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=1), "utf-8")

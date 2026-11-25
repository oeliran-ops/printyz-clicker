"""Mechanical profile - DEVELOPER-ONLY dimensions.

All values are in millimetres. Values marked VERIFY are engineering estimates
that must be confirmed against the original reference model / a physical test
print before they are treated as final. Values marked MEASURED come from the
reference model measurements in the specification.

Customers never edit this file's values; the UI exposes it only in Developer Mode.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, fields


@dataclass(frozen=True)
class SwitchSpec:
    """Cherry-MX compatible switch envelope (used for clearance checks + proxy)."""

    plate_hole: float = 13.90           # MEASURED/CHOSEN: 14.00 was pull-out-able
    plate_thickness: float = 1.50       # MX clip design thickness
    below_plate_depth: float = 5.00     # VERIFY: housing below plate
    pin_length: float = 3.30            # VERIFY: pins below housing
    housing_top_above_plate: float = 6.60  # VERIFY
    bottom_housing_width: float = 14.00    # MX bottom housing passes through the plate cut-out
    travel: float = 4.00                # MX total travel
    # keycap stem bottom rests this far above the housing top (= travel to bottom-out)
    stem_rest_gap: float = 4.00         # VERIFY


@dataclass(frozen=True)
class BodySpec:
    single_outer: float = 23.80         # MEASURED: single-body outer width/length
    height: float = 17.64               # MEASURED: body height
    upper_recess: float = 20.75         # MEASURED: keycap recess opening
    partition: float = 1.75             # wall between key recesses; MEASURED on the MakerWorld clicker model
    floor: float = 2.00                 # design value: closed bottom
    lower_pocket: float = 14.20         # pocket under the plate: straight walls up to the plate, so the
                                        # plate is printed on solid material (no floating ledge)
    lower_pocket_depth: float = 8.50    # floor-top to plate-bottom (switch needs 5.0 housing + 3.3 pins)
    clip_notch_width: float = 6.00      # recesses for the MX clips under the plate (VERIFY with a print)
    clip_notch_depth: float = 0.80
    clip_notch_height: float = 1.70     # vertical part; below it a 45 degree floor (self-supporting)
    clip_notch_sides: str = "ns"        # "ns" = clips on the north/south faces, "ew", or "all"
    outer_corner_radius: float = 3.00
    concave_corner_radius: float = 1.50
    recess_corner_radius: float = 1.00
    pocket_corner_radius: float = 0.50
    edge_fillet: float = 0.80           # top / bottom outer edge rounding
    groove_depth: float = 0.80          # reference groove depth
    groove_width: float = 1.60
    min_wall: float = 1.20              # validation threshold (outer wall)
    min_partition: float = 0.80         # two 0.4 mm extrusion lines

    @property
    def pitch(self) -> float:
        """Centre-to-centre distance between neighbouring keys."""
        return self.upper_recess + self.partition

    @property
    def outer_wall(self) -> float:
        return (self.single_outer - self.upper_recess) / 2.0

    @property
    def plate_bottom_z(self) -> float:
        return self.floor + self.lower_pocket_depth

    @property
    def plate_top_z(self) -> float:
        return self.plate_bottom_z + SwitchSpec().plate_thickness


@dataclass(frozen=True)
class KeycapStyle:
    """Geometry of one keycap style. z=0 is the skirt bottom (keycap local frame)."""

    name: str
    bottom_width: float
    height: float
    taper_deg: float
    wall: float
    top_thickness: float
    corner_radius: float
    top_edge_fillet: float
    stem_offset: float          # skirt bottom -> stem bottom distance (MEASURED on the reference keycap:
                                # the stem runs down to the skirt plane; 9.996 mm from inner top to stem end)
    stem_diameter: float = 5.60
    cross_length: float = 4.15  # VERIFY with a test print
    cross_width: float = 1.30   # VERIFY with a test print
    socket_depth: float = 3.80

    @property
    def top_width(self) -> float:
        return self.bottom_width - 2.0 * self.height * math.tan(math.radians(self.taper_deg))

    def width_at(self, z: float) -> float:
        return self.bottom_width - 2.0 * z * math.tan(math.radians(self.taper_deg))

    @property
    def legend_area(self) -> float:
        """Side length of the flat top area usable for a legend (before margins)."""
        return self.top_width - 2.0 * self.top_edge_fillet

    @property
    def stem_length(self) -> float:
        return self.height - self.top_thickness - self.stem_offset


KEYCAP_STYLES: dict[str, KeycapStyle] = {
    "standard": KeycapStyle(
        name="standard", bottom_width=18.14, height=11.83, taper_deg=6.725,
        wall=1.50, top_thickness=1.80, corner_radius=2.0, top_edge_fillet=0.8,
        stem_offset=0.03,
    ),
    "low_profile": KeycapStyle(
        name="low_profile", bottom_width=18.14, height=8.00, taper_deg=6.725,
        wall=1.50, top_thickness=1.60, corner_radius=2.0, top_edge_fillet=0.6,
        stem_offset=0.03,
    ),
    "thocky": KeycapStyle(
        name="thocky", bottom_width=18.14, height=12.30, taper_deg=6.725,
        wall=2.00, top_thickness=2.50, corner_radius=2.2, top_edge_fillet=1.0,
        stem_offset=0.03,
    ),
}


@dataclass(frozen=True)
class MechanicalProfile:
    name: str = "mx-default-v1"
    switch: SwitchSpec = field(default_factory=SwitchSpec)
    body: BodySpec = field(default_factory=BodySpec)
    min_press_clearance: float = 1.00   # keycap skirt vs plate at bottom-out
    min_side_clearance: float = 0.50    # keycap vs recess wall at bottom-out

    @property
    def plate_top_z(self) -> float:
        return self.body.plate_bottom_z + self.switch.plate_thickness

    def stem_bottom_rest_z(self) -> float:
        return self.plate_top_z + self.switch.housing_top_above_plate + self.switch.stem_rest_gap

    def keycap_rest_z(self, style: KeycapStyle) -> float:
        """World z of the keycap skirt bottom when not pressed."""
        return self.stem_bottom_rest_z() - style.stem_offset

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MechanicalProfile":
        def build(klass, data):
            names = {f.name for f in fields(klass)}
            return klass(**{k: v for k, v in data.items() if k in names})

        return cls(
            name=d.get("name", "custom"),
            switch=build(SwitchSpec, d.get("switch", {})),
            body=build(BodySpec, d.get("body", {})),
            min_press_clearance=d.get("min_press_clearance", 1.0),
            min_side_clearance=d.get("min_side_clearance", 0.5),
        )


def keycap_with_height(style: KeycapStyle, height: float | None) -> KeycapStyle:
    """Lower a keycap: first shorten stem-to-top (keeping socket depth + 0.3 mm), then the skirt.

    Raising above the style height is not allowed (the socket position is fixed by the switch).
    """
    import dataclasses

    if height is None or height >= style.height:
        return style
    delta = style.height - height
    slack_top = max(0.0, style.stem_length - (style.socket_depth + 0.3))
    from_top = min(delta, slack_top)
    from_skirt = delta - from_top
    if from_skirt > style.stem_offset:
        raise ValueError(f"Keycap height {height:.2f} mm is below the minimum {min_keycap_height(style):.2f} mm")
    return dataclasses.replace(style, height=height, stem_offset=style.stem_offset - from_skirt)


def min_keycap_height(style: KeycapStyle) -> float:
    return style.top_thickness + style.socket_depth + 0.3


DEFAULT_PROFILE = MechanicalProfile()

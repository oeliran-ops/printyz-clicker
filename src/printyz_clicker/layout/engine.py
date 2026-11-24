"""Layout engine - the ONE place where key positions are computed.

Preview and export both consume `compute_layout(project)`; nothing else
computes positions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .. import MAX_KEYS
from ..model.project import KeySlot, Project
from ..text.engine import key_direction, keys_visual


@dataclass(frozen=True)
class PlacedKey:
    key_id: Optional[str]      # None for an auto-generated blank cell
    row: int
    col: int
    x: float                   # mm, body centred on origin
    y: float
    auto_blank: bool = False


@dataclass
class LayoutResult:
    keys: list[PlacedKey]
    rows: int
    cols: int
    pitch: float
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def cells(self) -> set[tuple[int, int]]:
        return {(k.row, k.col) for k in self.keys}

    @property
    def ok(self) -> bool:
        return not self.errors

    def placed(self, key_id: str) -> PlacedKey:
        for k in self.keys:
            if k.key_id == key_id:
                return k
        raise KeyError(key_id)


# Fixed shapes. Slots listed in logical fill order for an LTR reader.
WASD_SLOTS = [(0, 1), (1, 0), (1, 1), (1, 2)]
ARROWS_SLOTS = [(0, 1), (1, 0), (1, 2), (2, 1)]
ARROWS_SLOTS_5 = [(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)]


def _mirror(cells: list[tuple[int, int]], cols: int) -> list[tuple[int, int]]:
    return [(r, cols - 1 - c) for r, c in cells]


def _row_major_rtl_aware(slots: list[tuple[int, int]], rtl: bool, cols: int) -> list[tuple[int, int]]:
    """Fill order: top row first; within a row in reading direction."""
    return sorted(slots, key=lambda rc: (rc[0], -rc[1] if rtl else rc[1]))


def compute_layout(project: Project) -> LayoutResult:
    spec = project.layout
    pitch = project.mechanical.body.pitch
    keys = project.keys
    rtl = key_direction(project) == "rtl"
    errors: list[str] = []
    warnings: list[str] = []
    cells: list[tuple[Optional[str], int, int, bool]] = []  # key_id, r, c, auto_blank

    if not keys:
        errors.append("אין מקשים — הקלד שם. / No keys - type a name.")
    if len(keys) > MAX_KEYS:
        errors.append(f"{len(keys)} מקשים — המקסימום {MAX_KEYS}. / {len(keys)} keys, max {MAX_KEYS}.")

    style = spec.style
    if style == "row":
        vis = keys_visual(project)
        cells = [(k.id, 0, i, False) for i, k in enumerate(vis)]
    elif style == "column":
        # reading order top -> bottom, regardless of language
        cells = [(k.id, i, 0, False) for i, k in enumerate(keys)]
    elif style == "grid":
        rows, cols = max(1, spec.rows), max(1, spec.cols)
        if len(keys) > rows * cols:
            errors.append(
                f"ברשת {rows}×{cols} יש רק {rows*cols} מקומות ל-{len(keys)} מקשים. / "
                f"Grid {rows}x{cols} has {rows*cols} cells for {len(keys)} keys."
            )
        for r in range(rows):
            chunk = keys[r * cols:(r + 1) * cols]
            if not chunk:
                break
            vis = keys_visual(project, chunk)
            # RTL rows are right-aligned so the first key sits in the right column
            start = cols - len(vis) if rtl else 0
            for i, k in enumerate(vis):
                cells.append((k.id, r, start + i, False))
        if spec.fill_empty_with_blank:
            used = {(r, c) for _, r, c, _ in cells}
            for r in range(rows):
                for c in range(cols):
                    if (r, c) not in used:
                        cells.append((None, r, c, True))
            if len(cells) > MAX_KEYS:
                errors.append(
                    f"מילוי הרשת יוצר {len(cells)} מקשים — המקסימום {MAX_KEYS}. / "
                    f"Filling the grid makes {len(cells)} keys, max {MAX_KEYS}."
                )
    elif style in ("wasd", "arrows"):
        if style == "wasd":
            slots, cols = WASD_SLOTS, 3
        else:
            slots, cols = (ARROWS_SLOTS_5 if len(keys) == 5 else ARROWS_SLOTS), 3
        if len(keys) != len(slots) and not (style == "arrows" and len(keys) in (4, 5)):
            errors.append(
                f"פריסת {style.upper()} דורשת {len(slots)} מקשים (יש {len(keys)}). / "
                f"{style.upper()} needs {len(slots)} keys (have {len(keys)})."
            )
        order = _row_major_rtl_aware(slots, rtl, cols)
        for k, (r, c) in zip(keys, order):
            cells.append((k.id, r, c, False))
    elif style == "custom":
        taken: dict[tuple[int, int], str] = {}
        pending: list[KeySlot] = []
        for k in keys:
            pos = spec.custom_cells.get(k.id)
            if pos is None:
                pending.append(k)
                continue
            rc = (int(pos[0]), int(pos[1]))
            if rc in taken:
                errors.append(f"שני מקשים באותו תא {rc}. / Two keys share cell {rc}.")
                continue
            taken[rc] = k.id
            cells.append((k.id, rc[0], rc[1], False))
        # unplaced keys go to the first free cell of the bounding grid (row-major)
        r = c = 0
        width = max([c for _, _, c, _ in cells] + [spec.cols - 1, 0]) + 1
        for k in pending:
            while (r, c) in taken:
                c += 1
                if c >= width:
                    c, r = 0, r + 1
            taken[(r, c)] = k.id
            cells.append((k.id, r, c, False))
            warnings.append(f"מקש '{k.value or 'ריק'}' מוקם אוטומטית. / Key auto-placed at {(r, c)}.")
    else:
        errors.append(f"Unknown layout style {style!r}")

    if not cells:
        return LayoutResult([], 0, 0, pitch, errors, warnings)

    # normalise to start at (0, 0)
    rmin = min(r for _, r, _, _ in cells)
    cmin = min(c for _, _, c, _ in cells)
    cells = [(kid, r - rmin, c - cmin, ab) for kid, r, c, ab in cells]
    rows = max(r for _, r, _, _ in cells) + 1
    cols = max(c for _, _, c, _ in cells) + 1

    placed = [
        PlacedKey(
            key_id=kid, row=r, col=c,
            x=(c - (cols - 1) / 2.0) * pitch,
            y=((rows - 1) / 2.0 - r) * pitch,
            auto_blank=ab,
        )
        for kid, r, c, ab in cells
    ]
    res = LayoutResult(placed, rows, cols, pitch, errors, warnings)
    if not _connected(res.cells):
        res.errors.append(
            "המקשים בפריסה אינם מחוברים — הגוף יתפצל לחלקים. / Layout cells are not connected."
        )
    return res


def _connected(cells: set[tuple[int, int]]) -> bool:
    if not cells:
        return True
    start = next(iter(cells))
    seen = {start}
    stack = [start]
    while stack:
        r, c = stack.pop()
        for nb in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if nb in cells and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return len(seen) == len(cells)

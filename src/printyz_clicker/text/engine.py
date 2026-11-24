"""Text engine: tokenising names into keys, direction detection, visual order.

Each key carries exactly one glyph, so no in-key shaping is needed; bidi only
affects the ORDER of keys. Hebrew final forms (ך ם ן ף ץ) are distinct code
points and are kept as typed.
"""

from __future__ import annotations

import difflib
import unicodedata
from dataclasses import dataclass, field
from typing import Sequence

from .. import MAX_KEYS
from ..model.project import KeySlot, Project, new_key_id

HEBREW_RANGE = (0x0590, 0x05FF)


def char_class(ch: str) -> str:
    """Simplified bidi class: 'R' (Hebrew/Arabic), 'L' (Latin etc), 'EN' (digit), 'N' (neutral)."""
    if not ch:
        return "N"
    bc = unicodedata.bidirectional(ch[0])
    if bc in ("R", "AL"):
        return "R"
    if bc == "L":
        return "L"
    if bc in ("EN", "AN"):
        return "EN"
    return "N"


def detect_direction(text: str) -> str:
    """Paragraph direction from the first strong character (UAX#9 P2/P3)."""
    for ch in text:
        c = char_class(ch)
        if c == "R":
            return "rtl"
        if c == "L":
            return "ltr"
    return "ltr"


def tokenize(text: str, spaces_as_blank: bool = True) -> list[tuple[str, str]]:
    """Split text into key tokens: list of (kind, value).

    Combining marks (niqqud etc.) stay attached to their base letter.
    Spaces become blank keys (or are dropped).
    """
    tokens: list[tuple[str, str]] = []
    for ch in unicodedata.normalize("NFC", text):
        if unicodedata.combining(ch) and tokens and tokens[-1][0] == "char":
            tokens[-1] = ("char", tokens[-1][1] + ch)
            continue
        if ch.isspace():
            if spaces_as_blank and ch == " ":
                tokens.append(("blank", ""))
            continue
        if unicodedata.category(ch).startswith("C"):
            continue  # control / format chars (e.g. RLM) never become keys
        tokens.append(("char", ch))
    # leading / trailing spaces never create keys
    while tokens and tokens[0][0] == "blank":
        tokens.pop(0)
    while tokens and tokens[-1][0] == "blank":
        tokens.pop()
    return tokens


@dataclass
class SyncResult:
    char_count: int = 0          # characters in the name
    text_keys: int = 0           # keys generated from text
    extra_keys: int = 0          # user-added keys
    total_keys: int = 0
    messages: list[str] = field(default_factory=list)

    @property
    def over_limit(self) -> bool:
        return self.total_keys > MAX_KEYS


def sync_keys_from_text(project: Project, text: str) -> SyncResult:
    """Regenerate text-derived keys while preserving ids/overrides of unchanged chars
    and keeping user-added (extra) keys at their positions. Never truncates silently."""
    old_text_keys = [k for k in project.keys if k.source == "text"]
    extras = [(i, k) for i, k in enumerate(project.keys) if k.source == "extra"]

    tokens = tokenize(text, project.spaces_as_blank)
    old_sig = [(k.kind, k.value) for k in old_text_keys]
    matcher = difflib.SequenceMatcher(a=old_sig, b=tokens, autojunk=False)
    new_text_keys: list[KeySlot] = [None] * len(tokens)  # type: ignore[list-item]
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag == "equal":
            for off in range(a1 - a0):
                new_text_keys[b0 + off] = old_text_keys[a0 + off]
    for i, (kind, value) in enumerate(tokens):
        if new_text_keys[i] is None:
            new_text_keys[i] = KeySlot(id=new_key_id(), kind=kind, value=value, source="text")  # type: ignore[arg-type]

    keys = list(new_text_keys)
    for idx, k in extras:
        keys.insert(min(idx, len(keys)), k)

    project.text = text
    project.keys = keys
    # drop custom positions of keys that no longer exist
    ids = {k.id for k in keys}
    project.layout.custom_cells = {k: v for k, v in project.layout.custom_cells.items() if k in ids}

    res = SyncResult(
        char_count=sum(1 for t in tokens if t[0] == "char"),
        text_keys=len(new_text_keys),
        extra_keys=len(extras),
        total_keys=len(keys),
    )
    if res.over_limit:
        res.messages.append(
            f"השם דורש {res.total_keys} מקשים — המקסימום הוא {MAX_KEYS}. "
            f"קצר את השם או הסר מקשים נוספים. / Name needs {res.total_keys} keys, max is {MAX_KEYS}."
        )
    return res


def insert_extra_key(project: Project, index: int, kind: str = "blank", value: str = "") -> KeySlot:
    key = KeySlot(id=new_key_id(), kind=kind, value=value, source="extra")  # type: ignore[arg-type]
    project.keys.insert(max(0, min(index, len(project.keys))), key)
    return key


def remove_key(project: Project, key_id: str) -> None:
    project.keys = [k for k in project.keys if k.id != key_id]
    project.layout.custom_cells.pop(key_id, None)


def paragraph_direction(project: Project) -> str:
    if project.text_direction != "auto":
        return project.text_direction
    return detect_direction(project.text)


def key_direction(project: Project) -> str:
    """Direction in which keys are laid out (may differ from text direction)."""
    if project.layout.key_direction != "auto":
        return project.layout.key_direction
    return paragraph_direction(project)


def visual_order(keys: Sequence[KeySlot], base: str) -> list[KeySlot]:
    """Left-to-right visual order of keys (simplified UAX#9, per-key granularity).

    Digits and Latin runs inside an RTL name keep their left-to-right order;
    neutrals (blank/symbol keys) take the direction of their surroundings.
    """
    n = len(keys)
    if n == 0:
        return []
    base_level = 1 if base == "rtl" else 0
    classes = [char_class(k.value) if k.kind == "char" else "N" for k in keys]
    # strong direction per key (EN behaves like L for run purposes)
    dirs: list[str | None] = []
    for c in classes:
        dirs.append("R" if c == "R" else "L" if c in ("L", "EN") else None)
    # resolve neutrals: same strong type on both sides -> that type; else base
    base_dir = "R" if base_level else "L"
    resolved: list[str] = []
    for i, d in enumerate(dirs):
        if d is not None:
            resolved.append(d)
            continue
        left = next((dirs[j] for j in range(i - 1, -1, -1) if dirs[j]), base_dir)
        right = next((dirs[j] for j in range(i + 1, n) if dirs[j]), base_dir)
        resolved.append(left if left == right else base_dir)
    levels = []
    for d in resolved:
        if base_level == 0:
            levels.append(0 if d == "L" else 1)
        else:
            levels.append(1 if d == "R" else 2)
    # L2: reverse runs from the highest level down to 1
    order = list(range(n))
    for lvl in range(max(levels), 0, -1):
        i = 0
        while i < n:
            if levels[order[i]] >= lvl:
                j = i
                while j < n and levels[order[j]] >= lvl:
                    j += 1
                order[i:j] = reversed(order[i:j])
                i = j
            else:
                i += 1
    return [keys[i] for i in order]


def keys_visual(project: Project, keys: Sequence[KeySlot] | None = None) -> list[KeySlot]:
    keys = list(project.keys if keys is None else keys)
    kd = key_direction(project)
    if project.layout.key_direction != "auto":
        # explicit override: simple mirror, no bidi run handling
        return list(reversed(keys)) if kd == "rtl" else keys
    return visual_order(keys, kd)


def insert_blank_visual(project: Project, side: str, anchor_id: str | None = None) -> KeySlot:
    """Add a blank key to the LEFT or RIGHT of `anchor_id` as seen on the product
    (or at the far left / right end). Works for RTL, LTR and mixed names."""
    vis = keys_visual(project)
    if anchor_id is None:
        target = 0 if side == "left" else len(vis)
    else:
        idx = next(i for i, k in enumerate(vis) if k.id == anchor_id)
        target = idx if side == "left" else idx + 1
    key = KeySlot(id=new_key_id(), kind="blank", value="", source="extra")
    base = list(project.keys)

    def visual_pos(li: int) -> int:
        project.keys = base[:li] + [key] + base[li:]
        return [k.id for k in keys_visual(project)].index(key.id)

    # <= 11 logical slots: take the one that puts the key at the wanted spot (or closest to it)
    li = min(range(len(base) + 1), key=lambda i: abs(visual_pos(i) - target))
    project.keys = base[:li] + [key] + base[li:]
    return key


def set_key_content(project: Project, key_id: str, kind: str, value: str) -> KeySlot:
    """Put a symbol / svg / blank on an existing key. A key that came from the typed name
    is detached from the text (its character is removed from the name) so later name edits
    never overwrite it."""
    key = project.key_by_id(key_id)
    if key.source == "text":
        text_keys = [k for k in project.keys if k.source == "text" and k.id != key_id]
        project.text = "".join(k.value if k.kind == "char" else " " for k in text_keys)
        key.source = "extra"
    key.kind, key.value = kind, value  # type: ignore[assignment]
    return key


def insert_key_visual(project: Project, side: str, anchor_id: str | None, kind: str, value: str) -> KeySlot:
    key = insert_blank_visual(project, side, anchor_id)
    key.kind, key.value = kind, value  # type: ignore[assignment]
    return key

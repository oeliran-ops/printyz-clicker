from printyz_clicker.layout.engine import compute_layout
from printyz_clicker.model.project import Project
from printyz_clicker.text.engine import sync_keys_from_text


def lay(text, style="row", **kw):
    p = Project()
    sync_keys_from_text(p, text)
    p.layout.style = style
    for k, v in kw.items():
        setattr(p.layout, k, v)
    return p, compute_layout(p)


def letters_by_x(p, res):
    by_id = {k.id: k.value for k in p.keys}
    return "".join(by_id[k.key_id] for k in sorted(res.keys, key=lambda k: k.x))


def test_row_hebrew_rtl_positions():
    p, r = lay("שלום")
    assert r.ok and letters_by_x(p, r) == "םולש"


def test_row_centered_and_pitch():
    p, r = lay("ab")
    xs = sorted(k.x for k in r.keys)
    assert abs(xs[0] + xs[1]) < 1e-9 and abs(xs[1] - xs[0] - r.pitch) < 1e-9


def test_column_top_to_bottom():
    p, r = lay("abc", "column")
    by_id = {k.id: k.value for k in p.keys}
    assert "".join(by_id[k.key_id] for k in sorted(r.keys, key=lambda k: -k.y)) == "abc"


def test_grid_rtl_first_key_top_right():
    p, r = lay("אבגדה", "grid", rows=2, cols=3)
    first = r.placed(p.keys[0].id)
    assert (first.row, first.col) == (0, 2)
    assert len(r.cells) == 5 and r.ok


def test_grid_fill_blank():
    p, r = lay("abcde", "grid", rows=2, cols=3, fill_empty_with_blank=True)
    assert len(r.keys) == 6 and sum(k.auto_blank for k in r.keys) == 1


def test_grid_too_small_is_error():
    _, r = lay("abcdefg", "grid", rows=2, cols=3)
    assert not r.ok


def test_wasd_shape():
    p, r = lay("WASD", "wasd")
    assert r.ok and r.cells == {(0, 1), (1, 0), (1, 1), (1, 2)}
    assert r.placed(p.keys[0].id).row == 0


def test_arrows_shape():
    _, r = lay("abcd", "arrows")
    assert r.cells == {(0, 1), (1, 0), (1, 2), (2, 1)}
    assert not r.ok  # plus shape without centre is disconnected -> flagged


def test_custom_disconnected_is_error():
    p = Project()
    sync_keys_from_text(p, "ab")
    p.layout.style = "custom"
    p.layout.custom_cells = {p.keys[0].id: [0, 0], p.keys[1].id: [0, 2]}
    assert not compute_layout(p).ok


def test_more_than_ten_keys_error():
    _, r = lay("abcdefghijk")
    assert not r.ok

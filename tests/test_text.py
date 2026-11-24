from printyz_clicker.model.project import Project
from printyz_clicker.text.engine import (
    detect_direction, insert_extra_key, keys_visual, sync_keys_from_text, tokenize,
)


def proj(text):
    p = Project()
    sync_keys_from_text(p, text)
    return p


def vis(p):
    return "".join(k.value or "_" for k in keys_visual(p))


def test_key_count_from_name():
    assert len(proj("דני").keys) == 3
    assert len(proj("שלום").keys) == 4
    assert len(proj("Daniel").keys) == 6
    assert len(proj("PRINTYZ").keys) == 7


def test_direction_detection():
    assert detect_direction("שלום") == "rtl"
    assert detect_direction("Daniel") == "ltr"
    assert detect_direction("123 שלום") == "rtl"


def test_hebrew_visual_order_is_right_to_left():
    assert vis(proj("שלום")) == "םולש"          # left-to-right on the product


def test_final_forms_preserved():
    p = proj("ךםןףץ")
    assert [k.value for k in p.keys] == list("ךםןףץ")


def test_english_order_and_case():
    assert vis(proj("DaNiel")) == "DaNiel"


def test_mixed_digits_inside_hebrew_keep_ltr():
    # "דני 12": digits run stays 1,2 left-to-right, placed left of the Hebrew
    assert vis(proj("דני 12")) == "12_ינד"


def test_over_limit_is_reported_not_truncated():
    p = Project()
    res = sync_keys_from_text(p, "abcdefghijk")
    assert res.over_limit and res.messages
    assert len(p.keys) == 11


def test_ids_stable_when_editing_name():
    p = proj("Dan")
    ids = [k.id for k in p.keys]
    p.keys[0].cap_color = "#FF0000"
    sync_keys_from_text(p, "Dana")
    assert [k.id for k in p.keys[:3]] == ids
    assert p.keys[0].cap_color == "#FF0000"


def test_extra_blank_survives_text_change():
    p = proj("abc")
    extra = insert_extra_key(p, 1)
    sync_keys_from_text(p, "abcd")
    assert p.keys[1].id == extra.id and len(p.keys) == 5


def test_niqqud_attached_and_spaces():
    toks = tokenize("שָׁלוֹם")
    assert len(toks) == 4
    assert tokenize("  a b ") == [("char", "a"), ("blank", ""), ("char", "b")]


def test_blank_left_right_in_product_order():
    from printyz_clicker.text.engine import insert_blank_visual
    for name in ("שלום", "Dan", "דני 12"):
        p = proj(name)
        before = vis(p)
        insert_blank_visual(p, "left")
        assert vis(p) == "_" + before
        insert_blank_visual(p, "right")
        assert vis(p) == "_" + before + "_"
    p = proj("שלום")                       # next to a selected key (ל): right of it on the product
    lamed = next(k for k in p.keys if k.value == "ל")
    insert_blank_visual(p, "right", lamed.id)
    assert vis(p) == "םול_ש"
    insert_blank_visual(p, "left", lamed.id)
    assert vis(p) == "םו_ל_ש"

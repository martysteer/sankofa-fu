import pytest
from sankofa_fu.grammar import tokenise, Component

def comps(s):  # helper: (kind, value) tuples
    return [(c.kind, c.value) for c in tokenise(s, "archival")]

def comps_raw(s):
    return [(c.kind, c.value) for c in tokenise(s, "raw")]

def test_archival_tokenise():
    # canonical form of "RM c.801.k.5"
    assert comps("RM C 801 K 5") == [
        ("ALPHA", "RM"), ("ALPHA", "C"), ("NUM", 801),
        ("ALPHA", "K"), ("NUM", 5)]

def test_letter_digit_boundary_split():
    assert comps("MS123B") == [("ALPHA", "MS"), ("NUM", 123), ("ALPHA", "B")]

def test_parenthesised_item_suffix():
    # "(1)" vs "(11)" — #distinct-item guard lives in NUM values
    assert comps("RM C 502 P 1 (1)")[-1] == ("NUM", 1)
    assert comps("RM C 502 P 1 (11)")[-1] == ("NUM", 11)

def test_num_is_int():
    c = tokenise("MS 42", "archival")[1]
    assert c.kind == "NUM" and c.value == 42

def test_raw_scheme_single_component():
    assert comps_raw("ANYTHING AT ALL") == [("RAW", "ANYTHING AT ALL")]

def test_unknown_scheme():
    with pytest.raises(KeyError):
        tokenise("X 1", "nope")

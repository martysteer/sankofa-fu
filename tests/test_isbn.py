import pytest
from sankofa_fu.schemes.isbn import canonical_isbn, canonical_issn
from sankofa_fu.grammar import tokenise

def test_isbn10_converts_to_13():
    # "0-306-40615-2" (valid ISBN-10) -> 9780306406157
    assert canonical_isbn("0-306-40615-2") == "9780306406157"

def test_isbn13_passthrough():
    assert canonical_isbn("978-0-306-40615-7") == "9780306406157"

def test_isbn_bad_check_digit():
    with pytest.raises(ValueError, match="check digit"):
        canonical_isbn("0-306-40615-3")

def test_isbn10_x_check():
    assert canonical_isbn("097522980X") == "9780975229804"

def test_issn_valid():
    assert canonical_issn("0378-5955") == "0378-5955"

def test_issn_bad_check():
    with pytest.raises(ValueError, match="check digit"):
        canonical_issn("0378-5954")

def test_isbn_scheme_single_component():
    comps = tokenise("9780306406157", "isbn")
    assert [(c.kind, c.value) for c in comps] == [("ID", "9780306406157")]

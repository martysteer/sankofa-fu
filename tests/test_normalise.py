import pytest
from sankofa_fu.config import IndexConfig
from sankofa_fu.normalise import normalise

CFG = IndexConfig(name="t", code_column="c",
                  abbreviations={"ms": "MS", "add": "ADD"})

# mechanism: #formatting — all must collapse to identical canonical form
@pytest.mark.parametrize("dirty", [
    "MS 12345", "ms 12345", "Ms. 12345", "MS.12345",
    "MS/12345", "MS-12345", "MS  12345", "MS\u00a012345",  # NBSP
    "MS 012345",                                            # padding
])
def test_formatting_variants_converge(dirty):
    assert normalise(dirty, CFG) == "MS 12345"

def test_unicode_nfkc():
    # fullwidth digits fold under NFKC  #formatting
    assert normalise("ＭＳ １２３", CFG) == "MS 123"

def test_case_fold_diacritics():
    assert normalise("Códex 5", CFG) == "CÓDEX 5"

def test_abbreviation_map_word_boundary():
    assert normalise("Add. 4to 9", CFG) == "ADD 4TO 9"
    # "add" inside a word must NOT be replaced
    assert normalise("Madder 1", CFG) == "MADDER 1"

def test_idempotent():
    once = normalise("Ms./00123-a", CFG)
    assert normalise(once, CFG) == once

def test_pad_policy():
    cfg = IndexConfig(name="t", code_column="c", numeric_padding="pad:5")
    assert normalise("MS 42", cfg) == "MS 00042"

def test_distinct_items_stay_distinct():
    # mechanism: #distinct-item — normalisation must NOT merge these
    assert normalise("MS 12345", CFG) != normalise("MS 12346", CFG)
    assert normalise("RM c.502.p.1 (1)", CFG) != normalise("RM c.502.p.1 (11)", CFG)

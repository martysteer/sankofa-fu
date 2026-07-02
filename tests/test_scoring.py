import pytest
from sankofa_fu.config import IndexConfig
from sankofa_fu.grammar import tokenise
from sankofa_fu.scoring import score, score_canonical

CFG = IndexConfig(name="t", code_column="c")

def s(q, c, cfg=CFG):
    return score(tokenise(q, "archival"), tokenise(c, "archival"), cfg)

def test_identical_scores_100():
    assert s("RM C 801 K 5", "RM C 801 K 5").score == 100

def test_numeric_mismatch_vetoes():           # #distinct-item
    assert s("MS 12345", "MS 12346").score == 0

def test_item_suffix_mismatch_vetoes():       # #distinct-item (screenshot case)
    assert s("RM C 502 P 1 (1)", "RM C 502 P 1 (11)").score == 0

def test_trailing_unmatched_penalised():      # #distinct-item
    full = s("RM C 801 P 1", "RM C 801 P 1").score
    extra = s("RM C 801 P 1", "RM C 801 P 1 7").score
    assert extra < full and extra < 90

def test_transposition_scores_high():         # #typo
    r = s("EGETRON 12", "EGERTON 12")
    assert 70 < r.score < 100

def test_prefix_fuzzy_numbers_exact():        # #typo in prefix only
    r = s("EGERTN 3025", "EGERTON 3025")
    assert r.score > 80

def test_ocr_confusable_rescues_num():        # #ocr-artifact: O vs 0
    # NOTE: confusables work at canonical-string level (score_canonical),
    # not component level — "1O5" tokenises as [NUM 1][ALPHA O][NUM 5],
    # a different shape from [NUM 105], so alignment would break first.
    r = score_canonical("MS 1O5", "MS 105", "archival", CFG)
    assert r.score == 100                      # O→0 makes them identical

def test_ocr_confusable_off():
    cfg = IndexConfig(name="t", code_column="c", ocr_confusables=False)
    assert score_canonical("MS 1O5", "MS 105", "archival", cfg).score == 0
    # NUM 1 vs NUM 105 -> veto

def test_penalty_gate_softens():
    cfg = IndexConfig(name="t", code_column="c", numeric_gate="penalty:50")
    r = s("MS 12345", "MS 12346", cfg)
    assert 0 < r.score < 60

def test_evidence_breakdown():
    r = s("MS 12345", "MS 12346")
    kinds = [e.detail for e in r.evidence]
    assert any("veto" in d for d in kinds)
    assert r.evidence[0].similarity == 1.0     # MS == MS

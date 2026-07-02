from pathlib import Path
import pytest
from sankofa_fu.config import IndexConfig
from sankofa_fu.index import build_index
from sankofa_fu.engine import Engine

FIX = Path(__file__).parent / "fixtures" / "catalogue.csv"
CFG = IndexConfig(name="t", code_column="shelfmark", id_column="record_id",
                  description_columns=("title", "date"))

@pytest.fixture
def engine(tmp_path):
    out = tmp_path / "authority.db"
    build_index(FIX, CFG, out)
    return Engine(out)          # config comes from meta snapshot, not yaml

def test_exact_dirty_variants(engine):
    # #formatting variants resolve to exact match, score 100, match=True
    for dirty in ["RM c.801.k.5", "rm C/801/K/5", "RM  c.801.k.05"]:
        top = engine.match(dirty)[0]
        assert (top.id, top.score, top.match) == ("r1", 100, True)

def test_typo_ranked_first_not_automatch(engine):     # #typo
    results = engine.match("Egetron 3025")
    assert results[0].id == "r7"
    assert results[0].score >= 70
    assert results[0].match is False          # fuzzy never auto-matches

def test_distinct_item_not_merged(engine):    # #distinct-item
    results = engine.match("RM c.502.p.1 (1)")
    assert results[0].id == "r3" and results[0].match is True
    assert all(r.id != "r4" or r.score == 0 for r in results)

def test_numeric_veto(engine):                # #distinct-item
    ids = {r.id: r.score for r in engine.match("MS 12345")}
    assert ids.get("r6", 0) == 0              # 12346 vetoed or absent

def test_evidence_attached(engine):
    top = engine.match("Egetron 3025")[0]
    assert top.evidence                        # non-empty breakdown

def test_no_candidates(engine):
    assert engine.match("ZZZ 999999") == [] or \
           all(r.score < 50 for r in engine.match("ZZZ 999999"))

def test_unparseable_falls_back(engine):
    # grammar can't fail on archival, but RAW fallback path must not 500;
    # simulate by querying empty-ish input
    assert engine.match("///") == []

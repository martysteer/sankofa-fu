from pathlib import Path
import pytest
from sankofa_fu.config import IndexConfig
from sankofa_fu.index import build_index
from sankofa_fu.blocking import TrigramBlocker

FIX = Path(__file__).parent / "fixtures" / "catalogue.csv"
CFG = IndexConfig(name="t", code_column="shelfmark", id_column="record_id",
                  description_columns=("title", "date"))

@pytest.fixture
def blocker(tmp_path):
    out = tmp_path / "authority.db"
    build_index(FIX, CFG, out)
    return TrigramBlocker(out)

def test_exact_canonical(blocker):
    rows = blocker.exact("MS 12345")
    assert [r["id"] for r in rows] == ["r5"]

def test_candidates_share_trigrams(blocker):
    ids = {r["id"] for r in blocker.candidates("RM C 801 K 5", limit=50)}
    assert "r1" in ids and "r2" in ids
    assert "r7" not in ids                    # Egerton shares no trigram

def test_short_query_fallback(blocker):
    # queries < 3 chars can't trigram-match; must not crash, may LIKE-scan
    assert isinstance(blocker.candidates("M", limit=10), list)

def test_row_shape(blocker):
    r = blocker.exact("MS 12345")[0]
    assert set(r) >= {"id", "raw_code", "canonical", "components", "extra"}

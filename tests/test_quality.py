"""Recall/precision floor. Every variance mechanism class must pass:
#formatting (normalisation), #typo (fuzzy), #ocr-artifact (confusables),
#distinct-item (false-positive guards)."""
import csv
from pathlib import Path
import pytest
from sankofa_fu.config import IndexConfig
from sankofa_fu.engine import Engine
from sankofa_fu.index import build_index

HERE = Path(__file__).parent / "fixtures"
CFG = IndexConfig(name="t", code_column="shelfmark", id_column="record_id",
                  description_columns=("title", "date"),
                  abbreviations={"ms": "MS"})

def pairs():
    return list(csv.DictReader(open(HERE / "labelled_pairs.csv")))

@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    out = tmp_path_factory.mktemp("q") / "authority.db"
    build_index(HERE / "catalogue.csv", CFG, out)
    return Engine(out)

@pytest.mark.parametrize("row", pairs(),
                         ids=lambda r: f"{r['mechanism']}:{r['dirty']}")
def test_labelled_pair(engine, row):
    results = engine.match(row["dirty"])
    if row["expect_match"] == "rank1":
        assert results and results[0].id == row["expected_id"], \
            f"expected {row['expected_id']} at rank 1, got " \
            f"{[(r.id, r.score) for r in results[:3]]}"
    else:  # absent — the distinct item must not surface
        assert all(r.id != row["expected_id"] for r in results), \
            f"{row['expected_id']} wrongly surfaced: " \
            f"{[(r.id, r.score) for r in results]}"

def test_all_mechanisms_covered():
    assert {"formatting", "typo", "ocr-artifact", "distinct-item"} <= \
           {r["mechanism"] for r in pairs()}

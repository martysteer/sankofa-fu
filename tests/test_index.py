import csv, json, sqlite3
from pathlib import Path
from sankofa_fu.config import IndexConfig
from sankofa_fu.index import build_index

FIX = Path(__file__).parent / "fixtures" / "catalogue.csv"
CFG = IndexConfig(name="t", code_column="shelfmark", id_column="record_id",
                  description_columns=("title", "date"))

def build(tmp_path):
    out = tmp_path / "authority.db"
    stats = build_index(FIX, CFG, out)
    return out, stats

def test_builds_and_counts(tmp_path):
    out, stats = build(tmp_path)
    assert stats.indexed == 7 and stats.rejected == 1
    db = sqlite3.connect(out)
    assert db.execute("select count(*) from records").fetchone()[0] == 7

def test_canonical_and_components_stored(tmp_path):
    out, _ = build(tmp_path)
    db = sqlite3.connect(out)
    raw, canonical, comps = db.execute(
        "select raw_code, canonical, components from records where id='r1'"
    ).fetchone()
    assert raw == "RM c.801.k.5"            # raw never overwritten
    assert canonical == "RM C 801 K 5"
    assert json.loads(comps) == [["ALPHA","RM"],["ALPHA","C"],
                                 ["NUM",801],["ALPHA","K"],["NUM",5]]

def test_meta_snapshot(tmp_path):
    out, _ = build(tmp_path)
    db = sqlite3.connect(out)
    snap = db.execute("select value from meta where key='config'").fetchone()[0]
    assert IndexConfig.from_json(snap) == CFG

def test_fts_populated(tmp_path):
    out, _ = build(tmp_path)
    db = sqlite3.connect(out)
    rows = db.execute(
        "select rowid from records_fts where records_fts match '801'").fetchall()
    assert len(rows) == 2                    # r1, r2

def test_rejects_file(tmp_path):
    build(tmp_path)
    rejects = list(csv.DictReader(open(tmp_path / "authority.rejects.csv")))
    assert len(rejects) == 1 and rejects[0]["reason"] == "empty code"

def test_extra_json(tmp_path):
    out, _ = build(tmp_path)
    db = sqlite3.connect(out)
    extra = json.loads(db.execute(
        "select extra from records where id='r7'").fetchone()[0])
    assert extra == {"title": "Charter", "date": "1210"}

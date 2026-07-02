import sqlite3
from pathlib import Path
from sankofa_fu.cli import main

FIX = Path(__file__).parent / "fixtures" / "catalogue.csv"

YAML = """\
name: test
code_column: shelfmark
id_column: record_id
description_columns: [title]
"""

def test_index_command(tmp_path, capsys):
    cfg = tmp_path / "repo.yaml"; cfg.write_text(YAML)
    out = tmp_path / "authority.db"
    rc = main(["index", str(FIX), "--config", str(cfg), "--out", str(out)])
    assert rc == 0
    db = sqlite3.connect(out)
    assert db.execute("select count(*) from records").fetchone()[0] == 7

def test_missing_config(tmp_path):
    rc = main(["index", str(FIX), "--config", str(tmp_path / "nope.yaml"),
               "--out", str(tmp_path / "o.db")])
    assert rc == 2

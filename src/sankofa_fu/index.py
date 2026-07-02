"""Build authority.db from CSV (spec §4.3). Bad rows go to
<out>.rejects.csv with a reason; never silently dropped (spec §7)."""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import IndexConfig
from .grammar import to_json, tokenise
from .normalise import normalise
from .schemes import SCHEMES

SCHEMA = """
create table records(
  id text primary key, raw_code text, canonical text,
  components text, scheme text, extra text);
create index idx_canonical on records(canonical);
create virtual table records_fts using fts5(
  canonical, content=records, content_rowid=rowid, tokenize="trigram");
create table meta(key text primary key, value text);
"""


@dataclass
class BuildStats:
    indexed: int = 0
    rejected: int = 0


def _check_sqlite():
    if sqlite3.sqlite_version_info < (3, 34, 0):
        raise SystemExit(
            f"SQLite >= 3.34 required for trigram FTS "
            f"(found {sqlite3.sqlite_version})")


def build_index(csv_path: Path | str, cfg: IndexConfig,
                out_db: Path | str) -> BuildStats:
    _check_sqlite()
    out_db = Path(out_db)
    rejects_path = out_db.with_suffix(".rejects.csv")
    stats = BuildStats()
    scheme_mod = SCHEMES[cfg.scheme]
    db = sqlite3.connect(out_db)
    db.executescript(SCHEMA)
    with open(csv_path, newline="", encoding="utf-8") as fh, \
         open(rejects_path, "w", newline="", encoding="utf-8") as rej:
        reader = csv.DictReader(fh)
        rej_writer = csv.DictWriter(rej,
            fieldnames=[*reader.fieldnames, "reason"])
        rej_writer.writeheader()
        for n, row in enumerate(reader, start=1):
            raw = (row.get(cfg.code_column) or "").strip()
            rid = row[cfg.id_column] if cfg.id_column else str(n)
            if not raw:
                rej_writer.writerow({**row, "reason": "empty code"})
                stats.rejected += 1
                continue
            try:
                if hasattr(scheme_mod, "canonicalise"):
                    canonical = scheme_mod.canonicalise(raw)
                else:
                    canonical = normalise(raw, cfg)
                comps = tokenise(canonical, cfg.scheme)
            except ValueError as e:
                rej_writer.writerow({**row, "reason": str(e)})
                stats.rejected += 1
                continue
            extra = {c: row.get(c, "") for c in cfg.description_columns}
            db.execute("insert into records values (?,?,?,?,?,?)",
                       (rid, raw, canonical, to_json(comps),
                        cfg.scheme, json.dumps(extra)))
            stats.indexed += 1
    db.execute("insert into records_fts(rowid, canonical) "
               "select rowid, canonical from records")
    db.execute("insert into meta values ('config', ?)", (cfg.to_json(),))
    db.execute("insert into meta values ('indexed', ?)", (stats.indexed,))
    db.commit()
    db.close()
    print(f"indexed {stats.indexed}, rejected {stats.rejected} "
          f"(see {rejects_path.name})", file=sys.stderr)
    return stats

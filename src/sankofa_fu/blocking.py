"""Candidate generation. Blocker is a Protocol so bigger-scale adapters
(spellfix1, sqlite-vec) can replace TrigramBlocker without touching
scorer or plugin (spec §10)."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol


class Blocker(Protocol):
    def exact(self, canonical: str) -> list[dict]: ...
    def candidates(self, canonical: str, limit: int = 200) -> list[dict]: ...


_COLS = "id, raw_code, canonical, components, scheme, extra"


class TrigramBlocker:
    def __init__(self, db_path: Path | str):
        self.db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        self.db.row_factory = sqlite3.Row

    def _rows(self, sql: str, params) -> list[dict]:
        return [dict(r) for r in self.db.execute(sql, params)]

    def exact(self, canonical: str) -> list[dict]:
        return self._rows(
            f"select {_COLS} from records where canonical = ?", (canonical,))

    def candidates(self, canonical: str, limit: int = 200) -> list[dict]:
        # Token-level OR matching: whole-string phrase MATCH would require
        # every trigram to appear, which is too strict for typo'd queries.
        toks = [t for t in canonical.split(" ") if len(t) >= 3]
        if not toks:            # short query: trigram can't match, LIKE-scan
            return self._rows(
                f"select {_COLS} from records where canonical like ? limit ?",
                (f"%{canonical}%", limit))
        match_expr = " OR ".join('"' + t.replace('"', '""') + '"' for t in toks)
        try:
            return self._rows(
                f"""select {_COLS} from records
                    where rowid in (select rowid from records_fts
                                    where records_fts match ?)
                    limit ?""", (match_expr, limit))
        except sqlite3.OperationalError:
            return []

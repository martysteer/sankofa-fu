"""Facade: Engine(db).match(raw) -> ranked Candidates.
Config is read from the index's meta snapshot (spec §4.3) so query-time
normalisation always matches index-time."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .blocking import TrigramBlocker
from .config import IndexConfig
from .normalise import normalise
from .schemes import SCHEMES
from .scoring import CONFUSABLES, Evidence, score_canonical

MIN_SCORE = 30          # drop noise below this


@dataclass(frozen=True)
class Candidate:
    id: str
    name: str                     # raw_code — what the curator recognises
    score: int
    match: bool                   # True only for unique exact-canonical hit
    evidence: tuple[Evidence, ...] = ()
    extra: str = "{}"


class Engine:
    def __init__(self, db_path: Path | str):
        self.blocker = TrigramBlocker(db_path)
        snap = self.blocker.db.execute(
            "select value from meta where key='config'").fetchone()
        if snap is None:
            raise ValueError(f"{db_path}: not a sankofa-fu index (no meta)")
        self.cfg = IndexConfig.from_json(snap[0])

    def match(self, raw_query: str, limit: int = 5) -> list[Candidate]:
        scheme_mod = SCHEMES[self.cfg.scheme]
        if hasattr(scheme_mod, "canonicalise"):
            try:
                canonical = scheme_mod.canonicalise(raw_query)
            except ValueError:
                return []         # invalid check digit -> no match (spec §7)
        else:
            canonical = normalise(raw_query, self.cfg)
        if not canonical:
            return []
        exact = self.blocker.exact(canonical)
        if len(exact) == 1:
            r = exact[0]
            return [Candidate(r["id"], r["raw_code"], 100, True,
                              extra=r["extra"])]
        if exact:                 # ambiguous exact: propose all, no auto-match
            return [Candidate(r["id"], r["raw_code"], 100, False,
                              extra=r["extra"]) for r in exact][:limit]
        # blocking; if OCR confusables enabled, also block on the
        # translated string (an OCR'd token may share no trigram with
        # its true form, e.g. "I2345" vs "12345")
        rows = {r["id"]: r for r in self.blocker.candidates(canonical)}
        if self.cfg.ocr_confusables:
            alt = canonical.translate(CONFUSABLES)
            if alt != canonical:
                for r in (self.blocker.candidates(alt)
                          + self.blocker.exact(alt)):
                    rows.setdefault(r["id"], r)
        out = []
        for r in rows.values():
            res = score_canonical(canonical, r["canonical"],
                                  self.cfg.scheme, self.cfg)
            if res.score >= MIN_SCORE:
                out.append(Candidate(r["id"], r["raw_code"], res.score,
                                     False, res.evidence, r["extra"]))
        out.sort(key=lambda c: -c.score)
        return out[:limit]

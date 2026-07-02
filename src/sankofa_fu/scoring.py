"""Component-aware scoring (spec §5).
Alignment: pairwise in order (sequences are short).
Combine: weighted mean × numeric gate. Evidence carried per component.
OCR confusables are applied at CANONICAL-STRING level (score_canonical):
translating O→0 etc. can change tokenisation shape ("1O5" is three
components, "105" is one), so component-level rescue can't work."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import zip_longest

from rapidfuzz.distance import DamerauLevenshtein, JaroWinkler

from .config import IndexConfig
from .grammar import Component, tokenise

CONFUSABLES = str.maketrans({"O": "0", "L": "1", "I": "1"})


@dataclass(frozen=True)
class Evidence:
    query: str | int | None
    candidate: str | int | None
    similarity: float
    detail: str


@dataclass(frozen=True)
class ScoreResult:
    score: int                    # 0-100
    evidence: tuple[Evidence, ...]


def _text_sim(a: str, b: str, first: bool) -> float:
    if first:
        return JaroWinkler.normalized_similarity(a, b)
    return DamerauLevenshtein.normalized_similarity(a, b)


def score(query: list[Component], cand: list[Component],
          cfg: IndexConfig) -> ScoreResult:
    evidence, weighted, weights = [], 0.0, 0.0
    vetoed = False
    penalty_gate = 1.0
    for i, (q, c) in enumerate(zip_longest(query, cand)):
        w = cfg.weights.get("prefix", 2.0) if i == 0 else cfg.weights.get("alpha", 1.0)
        if q is None or c is None:            # unmatched trailing component
            evidence.append(Evidence(getattr(q, "value", None),
                                     getattr(c, "value", None), 0.0, "unmatched"))
            weighted += 0.0
            weights += w
            continue
        if q.kind == "NUM" and c.kind == "NUM":
            if q.value == c.value:
                sim, detail = 1.0, "num exact"
            else:
                sim, detail = 0.0, f"num mismatch ({cfg.numeric_gate})"
                if cfg.numeric_gate == "veto":
                    vetoed = True
                else:                          # "penalty:N"
                    penalty_gate = int(cfg.numeric_gate.split(":")[1]) / 100.0
        elif q.kind == "ID" or c.kind == "ID":
            sim = 1.0 if (q.kind == c.kind and q.value == c.value) else 0.0
            detail = "id exact" if sim else "id mismatch"
            if sim == 0.0:
                vetoed = True
        elif q.kind != c.kind:                 # ALPHA vs NUM
            sim, detail = 0.0, "kind mismatch"
        else:                                  # ALPHA vs ALPHA (or RAW)
            sim = _text_sim(str(q.value), str(c.value), first=(i == 0))
            detail = "text fuzzy"
        evidence.append(Evidence(q.value, c.value, round(sim, 3), detail))
        weighted += sim * w
        weights += w
    base = (weighted / weights) if weights else 0.0
    final = 0 if vetoed else int(round(base * penalty_gate * 100))
    return ScoreResult(final, tuple(evidence))


def score_canonical(q_canonical: str, c_canonical: str, scheme: str,
                    cfg: IndexConfig) -> ScoreResult:
    """Score two canonical strings; retry with OCR-confusable translation
    if enabled and it improves the score (spec §5 OCR row)."""
    base = score(tokenise(q_canonical, scheme),
                 tokenise(c_canonical, scheme), cfg)
    if cfg.ocr_confusables and base.score < 100:
        qt = q_canonical.translate(CONFUSABLES)
        ct = c_canonical.translate(CONFUSABLES)
        if (qt, ct) != (q_canonical, c_canonical):
            alt = score(tokenise(qt, scheme), tokenise(ct, scheme), cfg)
            if alt.score > base.score:
                note = Evidence(q_canonical, c_canonical,
                                alt.score / 100, "ocr-confusables applied")
                return ScoreResult(alt.score, alt.evidence + (note,))
    return base

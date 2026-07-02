# sankofa-fu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Authority-matching reconciliation engine for classmarks/shelfmarks (Python + SQLite), surfaced to OpenRefine as a Datasette plugin speaking the W3C Reconciliation API 0.2.

**Architecture:** Two packages in one repo. `sankofa_fu` core (normalise → tokenise → index → block → score → engine facade, zero web deps) and `datasette_sankofa_fu` plugin (protocol layer only, delegates matching to core). Canonicalise first; fuzzy-match only the residue; numeric components gate the score.

**Tech Stack:** Python ≥3.11, stdlib `sqlite3` (SQLite ≥3.34 for FTS5 trigram), RapidFuzz, PyYAML, Datasette (plugin only), pytest.

**Spec:** `docs/2026-07-02-SPEC-sankofa-fu-design.md`

**Fixture discipline (similarity-modifier):** every dirty→canonical test pair is tagged with the *mechanism* that produced the variance — `#formatting` (delimiters/case/padding — must normalise away), `#typo` (transposition/substitution — fuzzy layer must catch), `#ocr-artifact` (confusable chars — confusable table must catch), `#distinct-item` (near-identical codes for *different* records — scorer must NOT merge; these are the false-positive guards). Each mechanism class must have at least one test; `#distinct-item` cases assert score 0 or exclusion.

---

## File structure

```
pyproject.toml
src/sankofa_fu/
  __init__.py
  config.py        # IndexConfig dataclass, YAML load/dump
  normalise.py     # normalise(text, cfg) -> canonical string
  grammar.py       # tokenise(canonical, scheme) -> [Component]; scheme registry
  scoring.py       # score(query_comps, cand_comps, cfg) -> ScoreResult(evidence)
  index.py         # build_index(csv, cfg, out_db); schema + meta snapshot + rejects
  blocking.py      # Blocker protocol; TrigramBlocker
  engine.py        # Engine.match(raw_query) -> [Candidate]
  cli.py           # `sankofa-fu index` entry point
  schemes/
    __init__.py    # SCHEMES registry
    archival.py
    isbn.py        # + issn
src/datasette_sankofa_fu/
  __init__.py      # register_routes, ReconcileView
tests/
  test_normalise.py test_grammar.py test_scoring.py test_index.py
  test_blocking.py test_engine.py test_isbn.py test_plugin.py
  fixtures/catalogue.csv fixtures/labelled_pairs.csv
```

---

### Task 0: Project scaffold

**Files:**
- Create: `pyproject.toml`, `src/sankofa_fu/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Write pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "sankofa-fu"
version = "0.1.0"
description = "Catalogue-backed reconciliation of classmarks and shelfmarks"
requires-python = ">=3.11"
dependencies = ["rapidfuzz>=3.0", "pyyaml>=6.0"]

[project.optional-dependencies]
datasette = ["datasette>=0.64"]
dev = ["pytest>=8.0", "datasette>=0.64"]

[project.scripts]
sankofa-fu = "sankofa_fu.cli:main"

[project.entry-points.datasette]
sankofa_fu = "datasette_sankofa_fu"

[tool.hatch.build.targets.wheel]
packages = ["src/sankofa_fu", "src/datasette_sankofa_fu"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create empty packages**

`src/sankofa_fu/__init__.py` containing `__version__ = "0.1.0"`; empty `tests/__init__.py`.

- [ ] **Step 3: Install and verify**

Run: `python -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/pytest`
Expected: `no tests ran` (exit 5 is fine).

- [ ] **Step 4: Verify SQLite capability**

Run: `.venv/bin/python -c "import sqlite3; print(sqlite3.sqlite_version)"`
Expected: ≥ 3.34.0. If lower, STOP — document blocker.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src tests
git commit -m "chore: scaffold sankofa-fu packages"
```

---

### Task 1: Config (`config.py`)

**Files:**
- Create: `src/sankofa_fu/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_config.py
import textwrap
from sankofa_fu.config import IndexConfig

YAML = textwrap.dedent("""\
    name: "RM manuscripts"
    code_column: shelfmark
    scheme: archival
    description_columns: [title, date]
    normalise:
      abbreviations: {"ms": "MS"}
      interchangeable_delimiters: [".", "/", "-", " "]
      numeric_padding: strip
    scoring:
      numeric_gate: veto
      weights: {prefix: 2.0, alpha: 1.0}
""")

def test_load_yaml(tmp_path):
    p = tmp_path / "repo.yaml"
    p.write_text(YAML)
    cfg = IndexConfig.from_yaml(p)
    assert cfg.name == "RM manuscripts"
    assert cfg.code_column == "shelfmark"
    assert cfg.scheme == "archival"
    assert cfg.id_column is None          # default: row number
    assert cfg.abbreviations == {"ms": "MS"}
    assert cfg.interchangeable_delimiters == [".", "/", "-", " "]
    assert cfg.numeric_padding == "strip"
    assert cfg.numeric_gate == "veto"
    assert cfg.weights == {"prefix": 2.0, "alpha": 1.0}

def test_roundtrip_json():
    cfg = IndexConfig(name="x", code_column="c")
    assert IndexConfig.from_json(cfg.to_json()) == cfg

def test_defaults():
    cfg = IndexConfig(name="x", code_column="c")
    assert cfg.scheme == "archival"
    assert cfg.numeric_gate == "veto"
    assert cfg.ocr_confusables is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL `ModuleNotFoundError: sankofa_fu.config`

- [ ] **Step 3: Implement**

```python
# src/sankofa_fu/config.py
"""Per-index configuration. JSON round-trip is used to snapshot the
config into the index's meta table so query-time normalisation always
matches index-time (spec §4.3)."""
from __future__ import annotations
import dataclasses, json
from dataclasses import dataclass, field
from pathlib import Path
import yaml

@dataclass(frozen=True)
class IndexConfig:
    name: str
    code_column: str
    id_column: str | None = None
    scheme: str = "archival"
    description_columns: tuple[str, ...] = ()
    abbreviations: dict[str, str] = field(default_factory=dict)
    interchangeable_delimiters: list[str] = field(
        default_factory=lambda: [".", "/", "-", " "])
    numeric_padding: str = "strip"          # "strip" | "pad:N"
    numeric_gate: str = "veto"              # "veto" | "penalty:N"
    weights: dict[str, float] = field(
        default_factory=lambda: {"prefix": 2.0, "alpha": 1.0})
    ocr_confusables: bool = True

    def __post_init__(self):
        object.__setattr__(self, "description_columns",
                           tuple(self.description_columns))

    @classmethod
    def from_dict(cls, d: dict) -> "IndexConfig":
        flat = {k: v for k, v in d.items() if k not in ("normalise", "scoring")}
        flat |= d.get("normalise", {}) | d.get("scoring", {})
        names = {f.name for f in dataclasses.fields(cls)}
        unknown = set(flat) - names
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        return cls(**flat)

    @classmethod
    def from_yaml(cls, path: Path | str) -> "IndexConfig":
        return cls.from_dict(yaml.safe_load(Path(path).read_text()))

    def to_json(self) -> str:
        d = dataclasses.asdict(self)
        d["description_columns"] = list(self.description_columns)
        return json.dumps(d, sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "IndexConfig":
        return cls(**json.loads(s))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/sankofa_fu/config.py tests/test_config.py
git commit -m "feat: IndexConfig with YAML load and JSON snapshot round-trip"
```

---

### Task 2: Normalisation (`normalise.py`)

Spec §3.1. Every dirty spelling of the same code must converge to one canonical string. Applied identically at index and query time.

**Files:**
- Create: `src/sankofa_fu/normalise.py`
- Test: `tests/test_normalise.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_normalise.py
import pytest
from sankofa_fu.config import IndexConfig
from sankofa_fu.normalise import normalise

CFG = IndexConfig(name="t", code_column="c",
                  abbreviations={"ms": "MS", "add": "ADD"})

# mechanism: #formatting — all must collapse to identical canonical form
@pytest.mark.parametrize("dirty", [
    "MS 12345", "ms 12345", "Ms. 12345", "MS.12345",
    "MS/12345", "MS-12345", "MS  12345", "MS\u00a012345",  # NBSP
    "MS 012345",                                            # padding
])
def test_formatting_variants_converge(dirty):
    assert normalise(dirty, CFG) == "MS 12345"

def test_unicode_nfkc():
    # fullwidth digits + ligature fold under NFKC  #formatting
    assert normalise("ＭＳ １２３", CFG) == "MS 123"

def test_case_fold_diacritics():
    assert normalise("Códex 5", CFG) == "CÓDEX 5"

def test_abbreviation_map_word_boundary():
    assert normalise("Add. 4to 9", CFG) == "ADD 4TO 9"
    # "add" inside a word must NOT be replaced
    assert normalise("Madder 1", CFG) == "MADDER 1"

def test_idempotent():
    once = normalise("Ms./00123-a", CFG)
    assert normalise(once, CFG) == once

def test_pad_policy():
    cfg = IndexConfig(name="t", code_column="c", numeric_padding="pad:5")
    assert normalise("MS 42", cfg) == "MS 00042"

def test_distinct_items_stay_distinct():
    # mechanism: #distinct-item — normalisation must NOT merge these
    assert normalise("MS 12345", CFG) != normalise("MS 12346", CFG)
    assert normalise("RM c.502.p.1 (1)", CFG) != normalise("RM c.502.p.1 (11)", CFG)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_normalise.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/sankofa_fu/normalise.py
"""Canonicalisation pipeline (spec §3.1). Order matters:
NFKC → casefold → whitespace → delimiters → abbreviations → padding."""
from __future__ import annotations
import re, unicodedata
from .config import IndexConfig

_WS = re.compile(r"\s+")

def normalise(text: str, cfg: IndexConfig) -> str:
    s = unicodedata.normalize("NFKC", text)
    s = s.upper()                                   # single case; upper keeps Ó
    s = s.replace("\u00a0", " ")
    # interchangeable delimiters -> single space (canonical separator)
    for d in cfg.interchangeable_delimiters:
        if d != " ":
            s = s.replace(d, " ")
    s = _WS.sub(" ", s).strip()
    # abbreviations on word boundaries (keys matched case-insensitively;
    # a trailing "." in input already became a space above)
    for src, dst in cfg.abbreviations.items():
        s = re.sub(rf"\b{re.escape(src.upper())}\b", dst.upper(), s)
    # numeric padding policy on every digit-run
    if cfg.numeric_padding == "strip":
        s = re.sub(r"\b0+(\d)", r"\1", s)
    elif cfg.numeric_padding.startswith("pad:"):
        width = int(cfg.numeric_padding.split(":", 1)[1])
        s = re.sub(r"\d+", lambda m: m.group().zfill(width), s)
    else:
        raise ValueError(f"bad numeric_padding: {cfg.numeric_padding!r}")
    return s
```

Note: parenthesised suffixes like `(11)` are untouched here — `(` `)` are not
interchangeable delimiters; grammar (Task 3) handles them as boundaries.
`"(1)"` vs `"(11)"` therefore stay distinct through both layers.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_normalise.py -v`
Expected: all PASS. If `test_formatting_variants_converge[MS.12345]` fails because `.` handling collides with abbreviation `Ms.` — the delimiter pass runs before abbreviations by design; debug there, don't reorder without re-running the whole file.

- [ ] **Step 5: Commit**

```bash
git add src/sankofa_fu/normalise.py tests/test_normalise.py
git commit -m "feat: config-driven canonicalisation pipeline"
```

---

### Task 3: Component grammar (`grammar.py` + `schemes/archival.py`)

Spec §3.2–3.3. Canonical string → ordered typed components. Scheme registry for future Dewey/LC.

**Files:**
- Create: `src/sankofa_fu/grammar.py`, `src/sankofa_fu/schemes/__init__.py`, `src/sankofa_fu/schemes/archival.py`
- Test: `tests/test_grammar.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_grammar.py
import pytest
from sankofa_fu.grammar import tokenise, Component

def comps(s):  # helper: (kind, value) tuples
    return [(c.kind, c.value) for c in tokenise(s, "archival")]

def test_archival_tokenise():
    # canonical form of "RM c.801.k.5"
    assert comps("RM C 801 K 5") == [
        ("ALPHA", "RM"), ("ALPHA", "C"), ("NUM", 801),
        ("ALPHA", "K"), ("NUM", 5)]

def test_letter_digit_boundary_split():
    assert comps("MS123B") == [("ALPHA", "MS"), ("NUM", 123), ("ALPHA", "B")]

def test_parenthesised_item_suffix():
    # "(1)" vs "(11)" — #distinct-item guard lives in NUM values
    assert comps("RM C 502 P 1 (1)")[-1] == ("NUM", 1)
    assert comps("RM C 502 P 1 (11)")[-1] == ("NUM", 11)

def test_num_is_int():
    c = tokenise("MS 42", "archival")[1]
    assert c.kind == "NUM" and c.value == 42

def test_raw_scheme_single_component():
    assert comps_raw("ANYTHING AT ALL") == [("RAW", "ANYTHING AT ALL")]

def comps_raw(s):
    return [(c.kind, c.value) for c in tokenise(s, "raw")]

def test_unknown_scheme():
    with pytest.raises(KeyError):
        tokenise("X 1", "nope")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_grammar.py -v` — Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/sankofa_fu/grammar.py
"""Typed-component tokeniser + scheme registry (spec §3.2–3.3).
Components serialise to JSON arrays like [["ALPHA","RM"],["NUM",801]]
for storage in records.components."""
from __future__ import annotations
import json
from dataclasses import dataclass
from .schemes import SCHEMES

@dataclass(frozen=True)
class Component:
    kind: str          # "ALPHA" | "NUM" | "RAW"
    value: str | int

def tokenise(canonical: str, scheme: str) -> list[Component]:
    return SCHEMES[scheme].tokenise(canonical)

def to_json(components: list[Component]) -> str:
    return json.dumps([[c.kind, c.value] for c in components])

def from_json(s: str) -> list[Component]:
    return [Component(k, v) for k, v in json.loads(s)]
```

```python
# src/sankofa_fu/schemes/__init__.py
"""Scheme registry. A scheme provides tokenise() and may override
per-component scoring rules (spec §3.3). Future: dewey, lc, lccn, oclc."""
from . import archival

class _Raw:
    @staticmethod
    def tokenise(canonical):
        from ..grammar import Component
        return [Component("RAW", canonical)]

SCHEMES = {"archival": archival, "raw": _Raw}
```

```python
# src/sankofa_fu/schemes/archival.py
"""Generic archival grammar: split on spaces, parens, and
letter/digit boundaries; digit runs become integer NUM components."""
from __future__ import annotations
import re

_PART = re.compile(r"[A-Z\u00C0-\u024F]+|\d+")

def tokenise(canonical: str):
    from ..grammar import Component
    out = []
    for m in _PART.finditer(canonical):
        tok = m.group()
        if tok.isdigit():
            out.append(Component("NUM", int(tok)))
        else:
            out.append(Component("ALPHA", tok))
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_grammar.py -v` — Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/sankofa_fu/grammar.py src/sankofa_fu/schemes tests/test_grammar.py
git commit -m "feat: component grammar with pluggable scheme registry"
```

---

### Task 4: Component-aware scorer (`scoring.py`)

Spec §5. The heart of the tool: numeric gate, Jaro–Winkler prefix, Damerau–Levenshtein elsewhere, OCR confusables, per-component evidence.

**Files:**
- Create: `src/sankofa_fu/scoring.py`
- Test: `tests/test_scoring.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scoring.py
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_scoring.py -v` — Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/sankofa_fu/scoring.py
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
            weighted += 0.0; weights += w
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
        elif q.kind != c.kind:                 # ALPHA vs NUM
            sim, detail = 0.0, "kind mismatch"
        else:                                  # ALPHA vs ALPHA (or RAW)
            sim = _text_sim(str(q.value), str(c.value), first=(i == 0))
            detail = "text fuzzy"
        evidence.append(Evidence(q.value, c.value, round(sim, 3), detail))
        weighted += sim * w; weights += w
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
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_scoring.py -v`
Expected: all PASS. Threshold assertions (`> 80`, `< 40`) are empirical — if one fails by a small margin, verify manually with a REPL, adjust the *test threshold* only if behaviour is correct; never bend the veto/distinct-item assertions.

- [ ] **Step 5: Commit**

```bash
git add src/sankofa_fu/scoring.py tests/test_scoring.py
git commit -m "feat: component-aware scorer with numeric gate and evidence"
```

---

### Task 5: Index builder (`index.py`)

Spec §4. CSV → `authority.db` with records, FTS5 trigram, meta snapshot, rejects.csv.

**Files:**
- Create: `src/sankofa_fu/index.py`, `tests/fixtures/catalogue.csv`
- Test: `tests/test_index.py`

- [ ] **Step 1: Create fixture CSV**

```csv
record_id,shelfmark,title,date
r1,RM c.801.k.5,Letters of X,1832
r2,RM c.801.k.15,Diary of Y,1840
r3,RM c.502.p.1 (1),Deed bundle,1701
r4,RM c.502.p.1 (11),Deed bundle,1702
r5,MS 12345,Codex A,1500
r6,MS 12346,Codex B,1501
r7,Egerton 3025,Charter,1210
r8,,Missing code,1900
```

Save as `tests/fixtures/catalogue.csv` (row r8 exercises the reject path).

- [ ] **Step 2: Write failing tests**

```python
# tests/test_index.py
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
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/pytest tests/test_index.py -v` — Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 4: Implement**

```python
# src/sankofa_fu/index.py
"""Build authority.db from CSV (spec §4.3). Bad rows go to
<out>.rejects.csv with a reason; never silently dropped (spec §7)."""
from __future__ import annotations
import csv, json, sqlite3, sys
from dataclasses import dataclass
from pathlib import Path
from .config import IndexConfig
from .grammar import to_json, tokenise
from .normalise import normalise

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
            canonical = normalise(raw, cfg)
            try:
                comps = tokenise(canonical, cfg.scheme)
            except ValueError as e:
                rej_writer.writerow({**row, "reason": f"unparseable: {e}"})
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
    db.commit(); db.close()
    print(f"indexed {stats.indexed}, rejected {stats.rejected} "
          f"(see {rejects_path.name})", file=sys.stderr)
    return stats
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/pytest tests/test_index.py -v` — Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/sankofa_fu/index.py tests/test_index.py tests/fixtures/catalogue.csv
git commit -m "feat: SQLite index builder with FTS5 trigram, meta snapshot, rejects"
```

---

### Task 6: Blocking (`blocking.py`)

Spec §2 flow. `Blocker` protocol so spellfix1/sqlite-vec adapters can slot in later; v1 ships trigram-FTS blocker.

**Files:**
- Create: `src/sankofa_fu/blocking.py`
- Test: `tests/test_blocking.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_blocking.py
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_blocking.py -v` — Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/sankofa_fu/blocking.py
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
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_blocking.py -v` — Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/sankofa_fu/blocking.py tests/test_blocking.py
git commit -m "feat: Blocker protocol + FTS5 trigram candidate generation"
```

---

### Task 7: Engine facade (`engine.py`)

Spec §2 query-time flow: normalise → exact short-circuit → block → score → rank.

**Files:**
- Create: `src/sankofa_fu/engine.py`
- Test: `tests/test_engine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_engine.py
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_engine.py -v` — Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/sankofa_fu/engine.py
"""Facade: Engine(db).match(raw) -> ranked Candidates.
Config is read from the index's meta snapshot (spec §4.3) so query-time
normalisation always matches index-time."""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from .blocking import TrigramBlocker
from .config import IndexConfig
from .normalise import normalise
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
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_engine.py -v`
Expected: all PASS. `test_numeric_veto`: r6 scores 0 → filtered by MIN_SCORE → absent; assertion allows both.

- [ ] **Step 5: Commit**

```bash
git add src/sankofa_fu/engine.py tests/test_engine.py
git commit -m "feat: Engine facade — normalise, exact short-circuit, block, score, rank"
```

---

### Task 8: ISBN/ISSN schemes (`schemes/isbn.py`)

Spec §3.3: validate check digits, canonical form, exact match only — never fuzzed.

**Files:**
- Create: `src/sankofa_fu/schemes/isbn.py`
- Modify: `src/sankofa_fu/schemes/__init__.py` (register `isbn`, `issn`)
- Test: `tests/test_isbn.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_isbn.py
import pytest
from sankofa_fu.schemes.isbn import canonical_isbn, canonical_issn
from sankofa_fu.grammar import tokenise

def test_isbn10_converts_to_13():
    # "0-306-40615-2" (valid ISBN-10) -> 9780306406157
    assert canonical_isbn("0-306-40615-2") == "9780306406157"

def test_isbn13_passthrough():
    assert canonical_isbn("978-0-306-40615-7") == "9780306406157"

def test_isbn_bad_check_digit():
    with pytest.raises(ValueError, match="check digit"):
        canonical_isbn("0-306-40615-3")

def test_isbn10_x_check():
    assert canonical_isbn("097522980X") == "9780975229804"

def test_issn_valid():
    assert canonical_issn("0378-5955") == "0378-5955"

def test_issn_bad_check():
    with pytest.raises(ValueError, match="check digit"):
        canonical_issn("0378-5954")

def test_isbn_scheme_single_component():
    comps = tokenise("9780306406157", "isbn")
    assert [(c.kind, c.value) for c in comps] == [("ID", "9780306406157")]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_isbn.py -v` — Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/sankofa_fu/schemes/isbn.py
"""ISBN/ISSN: validate + canonicalise (spec §3.3). ID components compare
exact-only in scoring: kind 'ID' is not ALPHA and not NUM, so any
mismatch is a kind/value mismatch -> no fuzzing."""
from __future__ import annotations
import re

def _digits(s: str) -> str:
    return re.sub(r"[\s\-]", "", s).upper()

def canonical_isbn(raw: str) -> str:
    d = _digits(raw)
    if len(d) == 10:
        total = sum((10 - i) * (10 if ch == "X" else int(ch))
                    for i, ch in enumerate(d))
        if total % 11 != 0:
            raise ValueError(f"ISBN-10 check digit invalid: {raw!r}")
        core = "978" + d[:9]
        return core + _ean13_check(core)
    if len(d) == 13 and d.isdigit():
        if _ean13_check(d[:12]) != d[12]:
            raise ValueError(f"ISBN-13 check digit invalid: {raw!r}")
        return d
    raise ValueError(f"not an ISBN: {raw!r}")

def _ean13_check(first12: str) -> str:
    s = sum(int(ch) * (1 if i % 2 == 0 else 3)
            for i, ch in enumerate(first12))
    return str((10 - s % 10) % 10)

def canonical_issn(raw: str) -> str:
    d = _digits(raw)
    if len(d) != 8:
        raise ValueError(f"not an ISSN: {raw!r}")
    total = sum((8 - i) * (10 if ch == "X" else int(ch))
                for i, ch in enumerate(d))
    if total % 11 != 0:
        raise ValueError(f"ISSN check digit invalid: {raw!r}")
    return f"{d[:4]}-{d[4:]}"

class _IsbnScheme:
    canonicalise = staticmethod(canonical_isbn)
    @staticmethod
    def tokenise(canonical):
        from ..grammar import Component
        return [Component("ID", canonical)]

class _IssnScheme(_IsbnScheme):
    canonicalise = staticmethod(canonical_issn)
```

```python
# src/sankofa_fu/schemes/__init__.py  (full replacement)
"""Scheme registry (spec §3.3). Future: dewey, lc, lccn, oclc."""
from . import archival
from .isbn import _IsbnScheme, _IssnScheme

class _Raw:
    @staticmethod
    def tokenise(canonical):
        from ..grammar import Component
        return [Component("RAW", canonical)]

SCHEMES = {"archival": archival, "raw": _Raw,
           "isbn": _IsbnScheme, "issn": _IssnScheme}
```

- [ ] **Step 4: Wire ID rejection into index + scoring**

In `index.py`, inside the row loop after `canonical = normalise(...)`: if the scheme module has a `canonicalise` attribute, call it on `raw` instead — catching `ValueError` and writing the row to rejects with `reason=str(e)`:

```python
            scheme_mod = __import__("sankofa_fu.schemes",
                                    fromlist=["SCHEMES"]).SCHEMES[cfg.scheme]
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
```

In `scoring.py`, the existing `q.kind != c.kind` / else branches already handle `ID`: two `ID` components hit the else branch (text fuzzy) — add a guard **above** it:

```python
        elif q.kind == "ID" or c.kind == "ID":
            sim = 1.0 if (q.kind == c.kind and q.value == c.value) else 0.0
            detail = "id exact" if sim else "id mismatch"
            if sim == 0.0:
                vetoed = True
```

In `engine.py`, query-time must use the scheme's canonicaliser too — a dirty
`0-306-40615-2` query must become `9780306406157` before matching. At the top
of `Engine.match`, replace the `canonical = normalise(...)` line:

```python
        from .schemes import SCHEMES
        scheme_mod = SCHEMES[self.cfg.scheme]
        if hasattr(scheme_mod, "canonicalise"):
            try:
                canonical = scheme_mod.canonicalise(raw_query)
            except ValueError:
                return []          # invalid check digit -> no match (spec §7)
        else:
            canonical = normalise(raw_query, self.cfg)
```

(Spec §7 asks for "invalid check digit" evidence on the query; an empty
result can't carry evidence in the Recon API response — the CLI/logs get it
via the ValueError message. Acceptable v1 trade-off, note it in README.)

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/pytest -v` — Expected: all PASS (earlier suites must not regress)

- [ ] **Step 6: Commit**

```bash
git add src/sankofa_fu/schemes tests/test_isbn.py src/sankofa_fu/index.py src/sankofa_fu/scoring.py
git commit -m "feat: ISBN/ISSN schemes — checksum validation, exact-only matching"
```

---

### Task 9: CLI (`cli.py`)

Spec §4.1: `sankofa-fu index catalogue.csv --config repo.yaml --out authority.db`.

**Files:**
- Create: `src/sankofa_fu/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_cli.py
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_cli.py -v` — Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/sankofa_fu/cli.py
from __future__ import annotations
import argparse, sys
from pathlib import Path
from .config import IndexConfig
from .index import build_index

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sankofa-fu")
    sub = parser.add_subparsers(dest="command", required=True)
    p_index = sub.add_parser("index", help="build authority index from CSV")
    p_index.add_argument("csv", type=Path)
    p_index.add_argument("--config", type=Path, required=True)
    p_index.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.config.exists():
        print(f"config not found: {args.config}", file=sys.stderr)
        return 2
    cfg = IndexConfig.from_yaml(args.config)
    build_index(args.csv, cfg, args.out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_cli.py -v` — Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/sankofa_fu/cli.py tests/test_cli.py
git commit -m "feat: sankofa-fu index CLI"
```

---

### Task 10: Datasette plugin (`datasette_sankofa_fu`)

Spec §6. Recon API 0.2: manifest, batch queries, extend, suggest. Protocol shapes modelled on datasette-reconcile (verified compatible with OpenRefine); all matching delegated to `sankofa_fu.engine`.

**Files:**
- Create: `src/datasette_sankofa_fu/__init__.py`
- Test: `tests/test_plugin.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_plugin.py
import json
from pathlib import Path
import pytest
from datasette.app import Datasette
from sankofa_fu.config import IndexConfig
from sankofa_fu.index import build_index

FIX = Path(__file__).parent / "fixtures" / "catalogue.csv"
CFG = IndexConfig(name="RM test", code_column="shelfmark",
                  id_column="record_id", description_columns=("title", "date"))

@pytest.fixture
def ds(tmp_path):
    db = tmp_path / "authority.db"
    build_index(FIX, CFG, db)
    return Datasette([str(db)])

@pytest.mark.asyncio
async def test_manifest(ds):
    r = await ds.client.get("/authority/-/sankofa-fu/reconcile")
    assert r.status_code == 200
    m = r.json()
    assert "0.2" in m["versions"]
    assert m["name"] == "RM test"
    assert r.headers["access-control-allow-origin"] == "*"

@pytest.mark.asyncio
async def test_reconcile_exact(ds):
    queries = json.dumps({"q0": {"query": "rm c.801.k.5"}})
    r = await ds.client.post("/authority/-/sankofa-fu/reconcile",
                             data={"queries": queries})
    result = r.json()["q0"]["result"]
    assert result[0]["id"] == "r1"
    assert result[0]["score"] == 100
    assert result[0]["match"] is True

@pytest.mark.asyncio
async def test_reconcile_fuzzy_not_automatch(ds):
    queries = json.dumps({"q0": {"query": "Egetron 3025"}})
    r = await ds.client.post("/authority/-/sankofa-fu/reconcile",
                             data={"queries": queries})
    result = r.json()["q0"]["result"]
    assert result[0]["id"] == "r7"
    assert result[0]["match"] is False
    assert "description" in result[0]        # evidence surfaced

@pytest.mark.asyncio
async def test_batch(ds):
    queries = json.dumps({"q0": {"query": "MS 12345"},
                          "q1": {"query": "MS 12346"}})
    r = await ds.client.post("/authority/-/sankofa-fu/reconcile",
                             data={"queries": queries})
    body = r.json()
    assert body["q0"]["result"][0]["id"] == "r5"
    assert body["q1"]["result"][0]["id"] == "r6"

@pytest.mark.asyncio
async def test_extend(ds):
    payload = json.dumps({"ids": ["r1", "r7"],
                          "properties": [{"id": "title"}]})
    r = await ds.client.post("/authority/-/sankofa-fu/reconcile",
                             data={"extend": payload})
    rows = r.json()["rows"]
    assert rows["r1"]["title"] == [{"str": "Letters of X"}]
    assert rows["r7"]["title"] == [{"str": "Charter"}]

@pytest.mark.asyncio
async def test_suggest_entity(ds):
    r = await ds.client.get(
        "/authority/-/sankofa-fu/reconcile/suggest/entity?prefix=RM C 801")
    names = [e["name"] for e in r.json()["result"]]
    assert any("801.k.5" in n for n in names)
```

Add `pytest-asyncio` to dev deps in `pyproject.toml`:
`dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "datasette>=0.64"]`
and `[tool.pytest.ini_options]` gains `asyncio_mode = "auto"`.
Re-run `.venv/bin/pip install -e ".[dev]"`.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_plugin.py -v` — Expected: FAIL (404s / module missing)

- [ ] **Step 3: Implement**

```python
# src/datasette_sankofa_fu/__init__.py
"""Datasette plugin: W3C Reconciliation API 0.2 over a sankofa-fu index.
One endpoint per database: /{db}/-/sankofa-fu/reconcile
Protocol layer only — matching lives in sankofa_fu.engine."""
from __future__ import annotations
import json
from datasette import hookimpl
from datasette.utils.asgi import Response
from sankofa_fu.engine import Engine

MAX_BATCH = 50
_engines: dict[str, Engine] = {}

def _engine(datasette, db_name: str) -> Engine:
    if db_name not in _engines:
        db = datasette.get_database(db_name)
        _engines[db_name] = Engine(db.path)
    return _engines[db_name]

def _json(body, status=200):
    return Response.json(body, status=status,
                         headers={"Access-Control-Allow-Origin": "*"})

def _describe(candidate) -> str:
    return " · ".join(
        f"{e.query}→{e.candidate}: {e.detail} ({e.similarity})"
        for e in candidate.evidence) or "exact canonical match"

async def reconcile(request, datasette):
    db_name = request.url_vars["db_name"]
    try:
        engine = _engine(datasette, db_name)
    except ValueError as e:                   # not a sankofa-fu index
        return _json({"error": str(e)}, status=400)

    post = await request.post_vars()
    queries = post.get("queries") or request.args.get("queries")
    extend = post.get("extend") or request.args.get("extend")

    if queries:
        qs = json.loads(queries)
        if len(qs) > MAX_BATCH:
            return _json({"error": f"max {MAX_BATCH} queries per batch"}, 400)
        out = {}
        for qid, q in qs.items():
            limit = min(int(q.get("limit", 5)), 25)
            out[qid] = {"result": [
                {"id": c.id, "name": c.name, "score": c.score,
                 "match": c.match, "description": _describe(c),
                 "type": [{"id": "record", "name": "Catalogue record"}]}
                for c in engine.match(q["query"], limit=limit)]}
        return _json(out)

    if extend:
        return _json(_extend(engine, json.loads(extend)))

    return _json(_manifest(datasette, db_name, engine))

def _extend(engine, payload):
    ids = payload["ids"]
    props = [p["id"] for p in payload["properties"]]
    rows = {}
    ph = ",".join("?" * len(ids))
    for rid, extra in engine.blocker.db.execute(
            f"select id, extra from records where id in ({ph})", ids):
        data = json.loads(extra)
        rows[rid] = {p: [{"str": str(data.get(p, ""))}] for p in props}
    return {"meta": [{"id": p, "name": p} for p in props], "rows": rows}

def _manifest(datasette, db_name, engine):
    base = datasette.setting("base_url").rstrip("/")
    service = f"{base}/{db_name}/-/sankofa-fu/reconcile"
    return {
        "versions": ["0.1", "0.2"],
        "name": engine.cfg.name,
        "identifierSpace": f"{service}/entity/",
        "schemaSpace": f"{service}/schema/",
        "defaultTypes": [{"id": "record", "name": "Catalogue record"}],
        "view": {"url": f"{base}/{db_name}/records/{{{{id}}}}"},
        "suggest": {"entity": {
            "service_url": "", "service_path":
            f"{service}/suggest/entity"}},
        "extend": {"propose_properties": {
            "service_url": "", "service_path":
            f"{service}/properties"}},
    }

async def suggest_entity(request, datasette):
    db_name = request.url_vars["db_name"]
    engine = _engine(datasette, db_name)
    prefix = request.args.get("prefix", "")
    rows = engine.blocker.db.execute(
        "select id, raw_code from records where canonical like ? limit 10",
        (f"{prefix.upper()}%",))
    return _json({"result": [{"id": r[0], "name": r[1]} for r in rows]})

async def properties(request, datasette):
    db_name = request.url_vars["db_name"]
    engine = _engine(datasette, db_name)
    return _json({"properties": [
        {"id": c, "name": c} for c in engine.cfg.description_columns]})

@hookimpl
def register_routes():
    return [
        (r"^/(?P<db_name>[^/]+)/-/sankofa-fu/reconcile$", reconcile),
        (r"^/(?P<db_name>[^/]+)/-/sankofa-fu/reconcile/suggest/entity$",
         suggest_entity),
        (r"^/(?P<db_name>[^/]+)/-/sankofa-fu/reconcile/properties$",
         properties),
    ]
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_plugin.py -v`
Expected: all PASS. If routes 404: check the plugin is installed via the `[project.entry-points.datasette]` hook (re-run `pip install -e .`).

- [ ] **Step 5: Manual smoke test against OpenRefine (optional but recommended)**

```bash
.venv/bin/sankofa-fu index tests/fixtures/catalogue.csv --config /tmp/repo.yaml --out /tmp/authority.db
.venv/bin/datasette /tmp/authority.db
# OpenRefine: column → Reconcile → Start reconciling → Add standard service:
#   http://127.0.0.1:8001/authority/-/sankofa-fu/reconcile
```

Expected: dirty variants of fixture codes reconcile; exact hits auto-match; fuzzy hits show ranked candidates with evidence in hover description.

- [ ] **Step 6: Commit**

```bash
git add src/datasette_sankofa_fu tests/test_plugin.py pyproject.toml
git commit -m "feat: Datasette plugin speaking Reconciliation API 0.2"
```

---

### Task 11: Quality harness (labelled pairs)

Spec §8: labelled dirty→canonical fixture set; CI asserts recall/precision floor. Pairs tagged by variance mechanism (similarity-modifier discipline) so every mechanism class is covered.

**Files:**
- Create: `tests/fixtures/labelled_pairs.csv`
- Test: `tests/test_quality.py`

- [ ] **Step 1: Create labelled pairs fixture**

```csv
dirty,expected_id,mechanism,expect_match
rm C/801/K/5,r1,formatting,rank1
MS  012345,r5,formatting,rank1
Ms. 12345,r5,formatting,rank1
Egetron 3025,r7,typo,rank1
EGERTN 3025,r7,typo,rank1
MS I2345,r5,ocr-artifact,rank1
RM c.502.p.1 (1),r3,distinct-item,rank1
RM c.502.p.1 (11),r4,distinct-item,rank1
MS 12345,r6,distinct-item,absent
RM c.801.k.5,r2,distinct-item,absent
```

Save as `tests/fixtures/labelled_pairs.csv`. Columns: `expect_match` is `rank1` (expected_id must be top result) or `absent` (expected_id must NOT appear with score > 0 for this dirty input — false-positive guard).

- [ ] **Step 2: Write failing test**

```python
# tests/test_quality.py
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
```

- [ ] **Step 3: Run to verify current behaviour**

Run: `.venv/bin/pytest tests/test_quality.py -v`
Expected: all PASS if Tasks 1–8 are correct. Any failure here is a real quality bug — use superpowers:systematic-debugging, do not loosen the fixture.

- [ ] **Step 4: Full suite + commit**

Run: `.venv/bin/pytest -v` — Expected: all PASS

```bash
git add tests/fixtures/labelled_pairs.csv tests/test_quality.py
git commit -m "test: mechanism-tagged quality harness with false-positive guards"
```

---

## Post-plan notes

- **Seed more fixtures from real data:** the `openrefine-classmark-clustering/` screenshots contain real UberShelfmark patterns (`RM c.801.S.1`, `RM c.500.t.1 (11)` etc.) — extend `catalogue.csv` and `labelled_pairs.csv` with them once real exports are available.
- **README:** after v1 tasks complete, write README covering install, `sankofa-fu index`, Datasette serving, OpenRefine setup. Not blocking.
- **Upgrade paths** (spec §10) intentionally have no tasks here: Blocker adapters, MARC/EAD, Dewey/LC schemes, Splink calibration, standalone FastAPI are follow-on plans.


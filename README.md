# sankofa-fú

Catalogue-backed reconciliation of classmarks, shelfmarks and other
structured identifiers. Protect the numerics, forgive the formatting.

Generic fuzzy matching merges `RM c.502.p.1 (1)` with `RM c.502.p.1 (11)`
(distinct items) while missing that `rm C/801/K/5` and `RM c.801.k.5` are
the same thing. sankofa-fú parses identifiers into typed components,
canonicalises the formatting away, and only fuzzes the parts where human
error actually happens — never the numbers.

It ships as two packages in one repo:

- **`sankofa_fu`** — core library: normalisation, component grammar,
  scoring, SQLite index, CLI.
- **`datasette_sankofa_fu`** — a [Datasette](https://datasette.io/) plugin
  exposing the index as a [W3C Reconciliation Service API
  0.2](https://www.w3.org/community/reports/reconciliation/) endpoint, so
  OpenRefine can reconcile against your catalogue.

## How matching works

```
raw query ──► NORMALISE ──► BLOCK ──► SCORE ──► ranked candidates
```

1. **Normalise** — NFKC, case-fold, interchangeable delimiters
   (`./-/space`) collapse to one form, abbreviations expand, leading zeros
   strip. `rm C/801/K/5` and `RM c.801.k.05` become the same canonical
   string.
2. **Block** — SQLite FTS5 trigram index proposes candidates; no full
   scan.
3. **Score** — the canonical string is tokenised into typed components
   (`ALPHA` / `NUM` / `ID`). Alpha components get fuzzy similarity
   (Jaro–Winkler on the prefix, Damerau–Levenshtein elsewhere). Numeric
   components must match exactly — a mismatch vetoes the candidate
   (configurable to a penalty instead). OCR confusables (`O`→`0`,
   `I`/`L`→`1`) get a second chance at the canonical-string level.
4. **Review** — `match: true` is returned **only** for a unique exact
   canonical hit. Fuzzy candidates are ranked with per-component evidence,
   never auto-matched. A human decides.

## Install

Requires Python ≥ 3.11 and SQLite ≥ 3.34 (for trigram FTS — the CLI
checks and tells you).

```bash
pip install -e ".[datasette]"     # or: uv pip install -e ".[datasette]"
```

For development:

```bash
uv venv .venv
uv pip install -p .venv/bin/python -e ".[dev]"
.venv/bin/pytest
```

## Build an index

Write a config per index:

```yaml
# repo.yaml
name: RM catalogue
code_column: shelfmark          # CSV column holding the identifier
id_column: record_id            # stable record id (optional; row number otherwise)
scheme: archival                # archival | raw | isbn | issn
description_columns: [title, date]   # carried into results / data extension
abbreviations:
  ms: MS
```

Then:

```bash
sankofa-fu index catalogue.csv --config repo.yaml --out authority.db
```

Rows that can't be indexed (empty code, invalid ISBN check digit, …) are
written to `authority.rejects.csv` with a reason — never silently
dropped. The config is snapshotted inside the index, so query-time
normalisation always matches index-time; you don't ship the YAML with the
database.

### Config reference

| Key | Default | Meaning |
|-----|---------|---------|
| `name` | — | Service name shown in the Recon manifest |
| `code_column` | — | CSV column containing the identifier |
| `id_column` | row number | Stable record id column |
| `scheme` | `archival` | Component grammar: `archival`, `raw`, `isbn`, `issn` |
| `description_columns` | `[]` | Columns stored for display and data extension |
| `abbreviations` | `{}` | Expansions applied on word boundaries (`ms` → `MS`) |
| `interchangeable_delimiters` | `. / - space` | Delimiters collapsed during normalisation |
| `numeric_padding` | `strip` | `strip` leading zeros, or `pad:N` to zero-fill |
| `numeric_gate` | `veto` | Numeric mismatch: `veto` (score 0) or `penalty:N` (cap at N%) |
| `weights` | `prefix: 2.0, alpha: 1.0` | Component weights in the score |
| `ocr_confusables` | `true` | Retry with `O→0`, `I/L→1` translation |

`normalise:` and `scoring:` nesting is accepted and flattened.

### Schemes

- **`archival`** (default) — alternating letter/number runs; fits
  shelfmarks like `RM c.801.k.5`, `MS 12345`, `Egerton 3025`.
- **`raw`** — whole string as one component; exact-ish fallback.
- **`isbn` / `issn`** — check digits validated; ISBN-10 converts to
  ISBN-13. Exact match only, never fuzzed. A query with an invalid check
  digit returns no candidates (the reason appears in CLI/rejects output;
  the Recon API can't carry evidence on an empty result — known v1
  trade-off).

Future schemes (Dewey, LC, LCCN, OCLC) register in
`sankofa_fu.schemes.SCHEMES`.

## Serve the Reconciliation API

```bash
datasette authority.db
```

The plugin registers one endpoint per database:

```
http://127.0.0.1:8001/authority/-/sankofa-fu/reconcile
```

- `GET` → service manifest (versions 0.1 and 0.2)
- `POST queries={...}` → batch reconciliation (max 50 per batch)
- `POST extend={...}` → data extension over `description_columns`
- `.../reconcile/suggest/entity?prefix=RM C 801` → type-ahead suggest
- `.../reconcile/properties` → extendable properties

CORS is open (`Access-Control-Allow-Origin: *`) so browser-based clients
work.

### Use from OpenRefine

1. Select the identifier column → **Reconcile → Start reconciling…**
2. **Add standard service** →
   `http://127.0.0.1:8001/authority/-/sankofa-fu/reconcile`
3. Exact canonical hits auto-match; fuzzy hits appear ranked, with the
   per-component evidence in each candidate's hover description
   (e.g. `EGETRON→EGERTON: text fuzzy (0.943) · 3025→3025: num exact`).

## Library use

```python
from sankofa_fu.engine import Engine

engine = Engine("authority.db")          # config comes from the snapshot
for c in engine.match("rm C/801/K/5"):
    print(c.id, c.name, c.score, c.match, c.evidence)
```

## Testing

```bash
.venv/bin/pytest
```

`tests/test_quality.py` is a labelled-pairs harness: every dirty→expected
pair in `tests/fixtures/labelled_pairs.csv` is tagged with its variance
mechanism (`formatting`, `typo`, `ocr-artifact`, `distinct-item`), and
`distinct-item` rows include *absent* guards asserting that near-identical
but distinct items do **not** surface. Extend it with pairs from your own
catalogue exports — if a new pair fails, that's a real quality bug, not a
fixture to loosen.

## Design docs

- `docs/2026-07-02-SPEC-sankofa-fu-design.md` — approved design
- `docs/2026-07-02-PLAN-sankofa-fu.md` — implementation plan
- `docs/research-notes.md` — background research

## Name

*Sankofa* — "go back and get it": return to the record you already hold.
*Fú* (符) — a tally or matching token, split in two and rejoined to prove
identity.	

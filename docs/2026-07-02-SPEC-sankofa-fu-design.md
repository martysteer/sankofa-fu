# sankofa-fu — Design Spec
### Catalogue-backed reconciliation of classmarks, shelfmarks & bibliographic identifiers

*Approved design, 2026-07-02. Derived from `docs/research-notes.md` and brainstorming session. Name: **sankofa-fu** (Sankofa "go back and fetch it" + 符 fú, the tally split into matching halves).*

---

## 1. Problem & scope

Messy reference codes (wrong case, transposed characters, inconsistent delimiters, padded vs unpadded numbers, abbreviated prefixes) must be linked to the catalogue records they actually refer to. Generic fuzzy matching fails here: codes are short, structured, and carry numeric fields whose exact value is the whole point — OpenRefine's built-in clustering merges `RM c.502.p.1 (1)` with `RM c.502.p.1 (11)` (distinct items) and builds 47-value junk clusters (see `openrefine-classmark-clustering/` screenshots).

**v1 scope decisions:**

| Decision | Choice |
|---|---|
| Operating mode | Authority matching only — clean catalogue as authority in SQLite, dirty codes matched against it. Dirty-to-dirty clustering out of scope for v1. |
| Ingest | CSV/TSV. Schema designed hierarchy-ready so EAD/MARC ingest can land later without migration. |
| Scale | Optimise for tens of thousands of records; architecture provisions for 100k+ and millions via swappable blocking layer. |
| Interface | W3C Reconciliation Service API 0.2 only, surfaced as a Datasette plugin (user's existing workflow). No custom OpenRefine extension. |
| Configuration | One config file per index (YAML); snapshot embedded in the index. |
| Stack | Python + SQLite (FTS5 trigram). RapidFuzz for string metrics. No compiled SQLite extensions in v1 (no spellfix1 dependency). |

**Non-goals for v1:** dirty-to-dirty reconciliation, embeddings/`sqlite-vec`, Splink/Fellegi–Sunter calibration, MARC/EAD ingest, standalone FastAPI service, custom OpenRefine extension. All have provisioned upgrade paths (§10).

---

## 2. Architecture

Two packages, one repo:

```
sankofa-fu/                     # core library + CLI, zero web deps
  normalise.py                  # canonicalisation pipeline (config-driven)
  grammar.py                    # component tokeniser: code → typed components
  index.py                      # build SQLite index from CSV (CLI: sankofa-fu index)
  blocking.py                   # candidate generation (Blocker interface;
                                #   v1 impl: FTS5 trigram + canonical exact)
  scoring.py                    # component-aware scorer
  engine.py                     # facade: match(query, config) → ranked candidates

datasette-sankofa-fu/           # thin Datasette plugin
  Recon API 0.2 endpoint via register_routes()
  protocol layer cribbed from datasette-reconcile
  delegates ALL matching to sankofa_fu.engine
```

Query-time flow:

```
dirty code → normalise (same pipeline as index build)
          → exact match on canonical form? → score 100, done
          → else: trigram blocking → ~50–200 candidates
          → component-aware scoring → ranked list + per-component evidence
          → Recon API JSON (score, match flag, evidence)
```

**Key boundary:** core knows nothing about HTTP/Datasette; plugin knows nothing about matching. Engine is testable with plain pytest against fixture SQLite files.

**Why not datasette-reconcile as-is:** verified from source — it scores with `fuzz.ratio` on raw lowercased strings (no normalisation, no numeric protection; `MS 12345` vs `MS 12346` ≈ 96) and has no extension hooks for scoring or normalisation. Its protocol layer is sound and is the model for ours.

---

## 3. Normalisation + component grammar

Two stages, config-driven, applied **identically at index time and query time** (asymmetric normalisation kills the exact-match rate).

### 3.1 Normalise (string → canonical string)

1. Unicode NFKC, then case-fold
2. Whitespace: collapse runs, trim, NBSP → space
3. Abbreviation map from config: `Ms.`/`ms` → `MS`, `Add.` → `ADD`, `fol.`/`f.` → `F` (per-repository table)
4. Delimiter policy: configured interchangeable delimiters (`.` `/` `-` space) collapse to one canonical separator
5. Numeric padding policy: strip leading zeros (config alternative: pad to width N)

Goal: every spelling of the *same* code converges to one canonical string, so most links resolve by exact match with no fuzzy scoring at all. Fuzzy matching handles only the residue (genuine typos, OCR errors, transpositions).

### 3.2 Tokenise (canonical string → typed components)

```
"RM c.801.k.5"  →  [ALPHA "RM"] [ALPHA "C"] [NUM 801] [ALPHA "K"] [NUM 5]
```

- Split on canonical separator and letter/digit boundaries
- Types: `ALPHA` (prefix/textual), `NUM` (stored as integer value, not string)
- Order preserved; components compared pairwise in order at scoring time

### 3.3 Scheme registry (extensibility)

Grammar is a pluggable **scheme**: a named module providing tokenise rules and per-component-type scoring overrides.

- v1 ships: `archival` (generic grammar above), `isbn`, `issn`, `raw` (no parsing; whole-string fuzzy)
- Provisioned: `dewey`, `lc` (LC classification — Cutter-number segment gets phonetic comparison), `lccn`, `oclc`, and other classmark standards as future scheme modules
- Bibliographic identifier schemes (`isbn`, `issn`) validate check digits and convert to canonical form (ISBN-10 → ISBN-13); **exact match only, never fuzzed**

### 3.4 Hierarchy readiness

The component list *is* the hierarchical path. When EAD ingest lands, components map to fonds/series/file/item levels and the grammar gains optional per-level labels. Components stored as a JSON array now, so no schema migration.

Stored per record: raw code (never overwritten), canonical string, component JSON.

---

## 4. Index build, SQLite schema, config file

### 4.1 CLI

```
sankofa-fu index catalogue.csv --config repo.yaml --out authority.db
```

### 4.2 Config file (`repo.yaml`, one per index)

```yaml
name: "RM manuscripts"
id_column: record_id          # default: row number
code_column: shelfmark
scheme: archival              # archival | dewey | lc | isbn | issn | raw
description_columns: [title, date]   # carried into index for preview/extend
normalise:
  abbreviations: {"ms": "MS", "add": "ADD"}
  interchangeable_delimiters: [".", "/", "-", " "]
  numeric_padding: strip      # strip | pad:N
scoring:                      # optional overrides, defaults sane
  numeric_gate: veto          # veto | penalty:N
  weights: {prefix: 2.0, alpha: 1.0}
```

### 4.3 Schema (`authority.db`)

```sql
records(id TEXT PRIMARY KEY,
        raw_code TEXT,            -- original, never overwritten
        canonical TEXT,
        components TEXT,          -- JSON typed-component array
        scheme TEXT,
        extra TEXT);              -- JSON of description_columns
CREATE INDEX idx_canonical ON records(canonical);
CREATE VIRTUAL TABLE records_fts USING fts5(canonical, content=records, tokenize="trigram");
-- meta(key, value): config snapshot, scheme, build time, source hash
```

- Config snapshot embedded in `meta` → query-time normalisation always matches index-time even if the yaml drifts; warn on mismatch and use the snapshot.
- Datasette serves this same file directly — browsing/audit UI for free.
- Requires SQLite ≥ 3.34 (trigram tokenizer); capability-checked at startup and index build.

---

## 5. Scoring

Input: query components vs candidate components (typed lists). Output: 0–100 score + per-component evidence.

**Alignment.** Components compared pairwise in order. Unequal lengths → greedy alignment by type-sequence (sequences are short, 2–8 components). Unmatched trailing components incur a configurable penalty — an extra `(11)` item-suffix matters; `RM c.502.p.1 (1)` and `RM c.502.p.1 (11)` must not merge.

**Per-type comparison:**

| Component type | Rule |
|---|---|
| `NUM` | Exact integer equality → 1.0. Unequal → **gate** (default `veto`: whole match scores 0; config `penalty:N` softens). Padding differences are normalised away before this point. |
| `ALPHA` prefix (first component) | Jaro–Winkler (RapidFuzz) — prefix-weighted, the classic record-linkage metric |
| `ALPHA` other | Normalised Damerau–Levenshtein similarity (RapidFuzz) — catches transpositions (`Egetron` → `Egerton`) |
| OCR confusables | Substitution table on ALPHA↔NUM ambiguity (`O`↔`0`, `l`/`I`↔`1`): if a NUM mismatch resolves under the confusable mapping, score as ALPHA-fuzzy instead of veto. Config on/off. |

**Combine.** Weighted mean of component scores × numeric gate. Weights from config (default: prefix 2.0, others 1.0). Exact canonical match short-circuits at 100 before the scorer runs.

**Evidence.** The scorer returns a per-component breakdown (e.g. `prefix: exact · num 801: exact · alpha k→t: 0.0`). Surfaced to reviewers via the Recon API candidate `description` so adjudication is fast (research notes §9.5).

Scheme modules may override per-type rules (e.g. LC Cutter segment → phonetic compare).

---

## 6. Datasette plugin (`datasette-sankofa-fu`)

- `register_routes()` → `/{db}/-/sankofa-fu/reconcile` — one endpoint per database (the index db is the unit, not the table)
- Implements Recon API **0.2**: service manifest, batch `queries` POST, `extend` (pulls `extra` columns back into OpenRefine), `suggest/entity` (prefix search on canonical). Protocol shapes modelled on datasette-reconcile, which is proven against OpenRefine.
- Plugin config in `datasette.yaml` covers serving concerns only; all matching config comes from the `meta` table inside the index db. No duplicate config.
- Manifest advertises `view.url` → Datasette row page doubles as record preview from OpenRefine.
- Batch queries handled per query within the batch; payload capped (default 50 queries).
- Score mapping: engine 0–100 → Recon `score` as-is. `match: true` **only** on unique exact-canonical hit. OpenRefine auto-matches only on `match: true`, so fuzzy hits always go to human review — "proposed, not auto-applied".
- CORS: `Access-Control-Allow-Origin: *` (required by OpenRefine's client).

---

## 7. Error handling

| Failure | Behaviour |
|---|---|
| Bad ingest row (empty code, unparseable under scheme) | Logged to `rejects.csv` with reason; build continues; summary count at end. Never silently dropped. |
| Unparseable query code (grammar fails) | Fall back to whole-string fuzzy on canonical (degraded, never a 500); evidence flags `parse_failed`. |
| Config/index mismatch (yaml drifted from `meta` snapshot) | Loud warning; snapshot wins. |
| SQLite < 3.34 / no trigram tokenizer | Hard fail at index build and plugin startup with a clear message. |
| ISBN/ISSN checksum failure | Ingest: row → `rejects.csv`. Query: no match; evidence says `invalid check digit`. |

---

## 8. Testing

TDD throughout.

- **Unit** — normalise (unicode/diacritic/NBSP cases; idempotence: `normalise(x) == normalise(normalise(x))`), grammar per scheme, scorer (table-driven: `MS 12345` ≠ `MS 12346` veto; `RM c.502.p.1 (1)` ≠ `RM c.502.p.1 (11)`; transposition catch; OCR confusable; padding collapse)
- **Integration** — build index from fixture CSV (~200 rows incl. RM-style codes seeded from the screenshot patterns) → golden tests through `engine.match`
- **Protocol** — plugin under the Datasette test client: manifest shape, batch queries, extend. Optionally validate against the W3C reconciliation test bench later.
- **Quality harness** — small labelled dirty→canonical fixture set; CI asserts recall/precision don't regress.

---

## 9. Human-in-the-loop principles

- Fuzzy matches are proposed, never auto-applied (`match: true` reserved for unique exact hits)
- Raw code always kept alongside the matched identifier; nothing overwritten in place
- Every candidate carries component-level evidence so a curator can adjudicate quickly

---

## 10. Provisioned upgrade paths (explicitly not v1)

| Future need | Path |
|---|---|
| 100k+–millions of records | `Blocker` is an interface; spellfix1 (numeric-protecting `editdist3` cost table) or `sqlite-vec` adapters slot in without touching scorer or plugin |
| MARC/EAD ingest, hierarchy | New ingest readers; component JSON already models the hierarchical path; grammar gains per-level labels |
| Dewey / LC / other classmark standards | New scheme modules in the grammar registry |
| Calibrated probabilities | Replace weighted-mean combine with Fellegi–Sunter weights (Splink as engine or as model to borrow) |
| Descriptive-metadata fallback (embeddings) | `sqlite-vec` over `extra` fields as a secondary signal only |
| Standalone (non-Datasette) service | Core is web-free; thin FastAPI adapter over `engine.match` |
| Dirty-to-dirty clustering | Separate sub-project; reuses normalise/grammar/scoring, adds transitive clustering |

---

## References

See `docs/research-notes.md` §References for full citations (Recon API spec, SQLite FTS5/spellfix1, RapidFuzz, Splink, Christen 2012, datasette-reconcile).

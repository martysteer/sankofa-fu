# sankofa-fu-refine: OpenRefine extension design

Date: 2026-07-08
Status: approved by user (brainstorming session)

## Purpose

An OpenRefine extension that reconciles/clusters/aligns a column of reference
codes (classmarks, shelfmarks, structured identifiers) against an external
"data spine", with a UX modeled on OpenRefine's Cluster & Edit dialog. It
combines sankofa-fú's component-aware classmark matching with the familiar
clustering workflow, and works across projects — something core clustering
cannot do.

The Python sankofa-fú package remains the canonical engine and continues to
serve the Datasette / Reconciliation API path. This extension is a JVM port of
the matching core plus a new clustering-style UI.

## Decisions made

| Question | Decision |
|---|---|
| Engine location | Port matching core to Clojure/JVM inside the extension (loupe-style) |
| Spine source (now) | A column in another OpenRefine project; also same-project columns (same picker) |
| Spine source (deferred) | Existing sankofa-fú SQLite index exposed via Reconciliation API (Datasette plugin already exists) — design for it, do not build |
| UX model | Clustering-style dialog (like Edit cells → Cluster), not recon judgments on cells |
| Algorithms | Sankofa component-scoring (schemes: archival/isbn/issn/raw) + classic methods (fingerprint key collision, Levenshtein nearest-neighbour) |
| Packaging | Separate extension repo, loupe used as structural template |
| Apply outputs | All four, user-selectable in dialog: spine ID → new column, spine code → new column, replace cell in place, score/evidence → new column |
| Scale target | Up to ~50k rows each side, in-memory blocking, no persistent index |
| Backend mechanism | Custom Commands + custom undoable Operation (Approach A) |
| Preview | Sample preview (limit=20 distinct values) recomputed on knob change |

## §1 Architecture & repo layout

New repo (working name `sankofa-fu-refine`), structure copied from loupe:

```
sankofa-fu-refine/
├── project.clj                    # Leiningen, AOT, targets OpenRefine 3.10.x
├── Makefile                       # jar → extension → install → zip (copy loupe's)
├── src/sankofa_fu/
│   ├── normalise.clj              # port of normalise.py
│   ├── grammar.clj                # tokeniser → typed components
│   ├── schemes.clj                # archival / isbn / issn / raw
│   ├── scoring.clj                # per-component scoring, numeric gate, evidence
│   ├── blocking.clj               # in-memory: canonical-exact map + trigram map
│   ├── classic.clj                # fingerprint key-collision, Levenshtein NN
│   └── engine.clj                 # facade: spine + query column + params → clusters
├── src/java/  (only if needed)    # Command/Operation may need Java or gen-class
├── extension/module/
│   ├── MOD-INF/
│   │   ├── module.properties
│   │   ├── controller.js          # load jar, register commands + operation + assets
│   │   └── lib/sankofa-fu.jar
│   ├── scripts/
│   │   ├── menu.js                # column menu: "Reconcile codes against spine…"
│   │   ├── match-dialog.js/.html  # clustering-style dialog
│   └── styles/match-dialog.css
└── test/sankofa_fu/               # clojure.test, fixtures shared with Python repo
```

- Backend: pure Clojure functions; `gen-class` (or thin Java) for classes
  extending `com.google.refine.commands.Command` and the Operation class,
  registered via controller.js using loupe's dynamic-classloader pattern.
- String metrics: Jaro–Winkler + Damerau–Levenshtein from
  `org.apache.commons:commons-text` (bundled in jar if not already on
  OpenRefine's classpath).
- Python sankofa-fú stays canonical spec. The Clojure port must pass the same
  mechanism-tagged fixture set (`formatting`, `typo`, `ocr-artifact`,
  `distinct-item`).

## §2 Engine port

Same pipeline as Python, minus persistence (no SQLite/FTS5 on the JVM side):

```
spine column  → normalise → tokenise → in-memory index
                                        {canonical→records, trigram→records}
query column  → distinct values (under current facets) → normalise → tokenise
              → block (exact canonical hit? else trigram overlap top-N)
              → score per-component
              → clusters
```

Cluster JSON shape (one per distinct query value):

```json
{
  "queryValue": "rm C/801/K/5",
  "count": 12,
  "candidates": [
    {"spineId": "r-00042", "spineCode": "RM c.801.k.5",
     "score": 100, "evidence": ["exact canonical"], "exact": true}
  ]
}
```

- Config knobs are dialog parameters, not YAML: scheme, numeric gate
  (veto | penalty), component weights, OCR-confusables toggle, delimiter set,
  padding mode (strip | pad:N), abbreviation map (textarea, `ms=MS` lines),
  minimum score, max candidates per value.
- Exact canonical match short-circuits at 100. A single exact hit is
  auto-ticked in the UI; multiple exact hits are proposed unticked (same rule
  as the Python engine).
- Numeric components: exact equality or gate (default veto → score 0;
  alternative penalty cap). ALPHA prefix: Jaro–Winkler. Other ALPHA:
  normalised Damerau–Levenshtein. ID (ISBN/ISSN): exact only. Unmatched
  trailing components penalised (guards `(1)` vs `(11)` distinct items).
- Classic methods (fingerprint key collision, Levenshtein NN) emit the same
  cluster JSON shape, so the dialog renders identically for every method.
- Scale: blocking caps candidates per query value (~200); ~50k×50k runs in
  memory in one pass.
- Spine adapter boundary in `engine.clj`:
  `(defprotocol Spine (records [this]))` — project-column implementation now,
  reconciliation-service implementation later. This is the only abstraction
  pre-bought for the deferred path.

## §3 Commands, data flow, apply

Commands registered in controller.js at `/command/sankofa-fu/<name>`:

1. `compute-matches` (POST)
   - Params: `project` (query project id), `column`, `spineProject`,
     `spineColumn`, `method` (`sankofa | fingerprint | levenshtein`), method
     params (scheme, gate, weights, ocr, delimiters, padding, abbreviations,
     minScore, maxCandidates), `engine` (facet-filter JSON — respected like
     the Cluster dialog), optional `limit` (used by preview).
   - Reads both projects via `ProjectManager`; the spine project does not
     need to be open in a browser tab.
   - Returns: cluster array (§2 shape) + summary stats
     (`nDistinct`, `nMatched`, `nExact`).
2. `apply-matches` (POST) — wraps `ApplyMatchesOperation` (below).

Project/column pickers need no new commands: core `get-all-project-metadata`
lists projects; core `get-models` gives columns of the chosen spine project.

`ApplyMatchesOperation` — one custom, undoable Operation (single history
entry):

- Input: accepted matches `[{queryValue, spineId, spineCode, score}]`, output
  flags `{idColumn?, codeColumn?, replaceInPlace?, scoreColumn?}`, new-column
  names, `engine` facet JSON.
- Execution: for each row whose cell value is in the accepted set (respecting
  facets), write the selected outputs. New columns created if missing.
- History description, e.g.: `Match 312 values in "shelfmark" against spine
  "RM catalogue"."shelfmark" (sankofa/archival)`.

Flow:

```
column menu → dialog opens
→ pick spine project + column, method, knobs
→ (knob change, debounced) POST compute-matches limit=20 → preview pane
→ Recompute → full compute-matches → cluster table
→ user ticks/unticks, picks candidates
→ choose outputs → Apply → apply-matches → one history entry
```

Error handling:

- Spine project deleted / column missing → HTTP 400 with message rendered in
  dialog.
- Empty selection → Apply button disabled.
- Per-value scoring exception → value flagged `"error"` in results, never
  silently dropped.

## §4 Dialog UX

Modeled on Cluster & Edit:

- Top bar: spine project dropdown, spine column dropdown, method dropdown,
  method-specific knobs area, Recompute button.
- Preview pane (under knobs): sample results for first 20 distinct values,
  recomputed (debounced) on any knob/method change, with quick stats
  ("14/20 matched, 6 exact"). Full table only after explicit Recompute.
- Main table: one row per distinct query value —
  `count | query value | candidates | accept checkbox`.
  Candidates rendered as radio list: `code — id — score`, with per-component
  evidence in a tooltip/expando (e.g. `EGETRON→EGERTON: fuzzy 0.94 · 3025:
  num exact`). Best candidate preselected; single exact hits auto-ticked.
- Footer: output checkboxes (ID column / code column / replace in place /
  score column) with name fields for new columns; select-all-above-score
  slider; Apply / Close.
- Facet-aware: computation covers only rows visible under current facets.

## §5 Testing

- clojure.test on each ported module (normalise, grammar, schemes, scoring,
  blocking, classic).
- Fixture parity: copy `tests/fixtures/catalogue.csv` and the labelled
  dirty→canonical pairs from the Python repo. Assert: expected ID at rank 1
  for `formatting`/`typo`/`ocr-artifact` cases; `distinct-item` cases must
  NOT surface as candidates.
- One integration test on the engine facade: spine list + dirty list →
  expected clusters.
- Command/Operation classes exercised manually against a local
  OpenRefine 3.10 (no OpenRefine test harness; matches loupe's practice).

## §6 Deferred: Reconciliation API spine

Not built now; designed for:

- Spine picker later gains a third type: "Reconciliation service (URL)".
- `compute-matches` would call the service's batch `/reconcile` endpoint and
  map responses into the same cluster JSON. Dialog and cluster shape
  unchanged — only a new `Spine` implementation behind the engine facade.
- The Datasette sankofa-fú plugin already serves this API over a SQLite
  index, so the server side already exists.

## Out of scope

- Writing OpenRefine recon judgments onto cells.
- Persistent JVM-side indexes (SQLite/FTS5).
- Hundreds-of-thousands-row spines (use the deferred recon path).
- Modifying the Python package (other than sharing test fixtures).

# Fuzzy Reconciliation of Classmarks, Shelfmarks & Bibliographic Identifiers
### Research & design notes for a catalogue-backed reconciliation tool

*Working context for speccing an OpenRefine-compatible reconciliation tool that builds a searchable SQLite index from library/archive catalogues and links messy reference codes against it.*

---

## 1. TL;DR — the load-bearing insights

1. **This is a record-linkage / entity-resolution problem on *structured identifiers*, not a free-text fuzzy-search problem.** Treat it as such and most design decisions follow.
2. **Canonicalise first; fuzzy-match only on the residue.** A normalisation pipeline removes the large majority of "typo / capitalisation / spacing" variance *deterministically*, which both raises recall and — crucially — cuts false positives. Edit distance on raw strings is the wrong default.
3. **Numeric / sequential components of a reference code are semantically load-bearing.** `MS 12345` and `MS 12346` are edit-distance 1 apart but are *different items*. Any scoring scheme must protect the numbers (exact match or near-zero tolerance) while staying forgiving on prefixes and textual parts.
4. **The shape of the problem differs by mode.** Matching a dirty list against a *clean authority list* (your catalogue) is materially easier than reconciling two dirty lists to each other. The catalogue-as-authority case is the one to optimise for.
5. **You may not need an OpenRefine *extension* at all.** The W3C **Reconciliation Service API** is a documented standard that vanilla OpenRefine already speaks. A backend that exposes that API plugs straight into OpenRefine — and into other clients — with no custom Java extension. (See §9.)
6. **SQLite already ships most of the fuzzy primitives you need** — FTS5 trigram tokenizer for substring/similarity matching and the `spellfix1` extension for SymSpell-style fuzzy lookup with *configurable* per-character edit costs. The cost-table feature is the natural place to encode rule #3. (See §6.)

---

## 2. Problem framing

The task: given a reference code as it appears in a messy spreadsheet (wrong case, transposed characters, inconsistent delimiters, padded vs unpadded numbers, abbreviated prefixes), find the catalogue record it *actually* refers to, and do so at scale without an analyst eyeballing every row.

This is **entity resolution / record linkage**, a well-studied field (the standard reference is Peter Christen, *Data Matching*, Springer 2012). Framing it generically buys you a mature vocabulary and toolset: *canonicalisation, blocking, comparison/scoring, classification, clerical review.*

Two operating modes, which the tool should distinguish explicitly:

- **Authority matching (1-to-many against a clean target).** The catalogue is the authority. Each dirty input is matched to at most one canonical record. This is the primary use case and the easier problem — you can pre-index the authority and do fast candidate lookup per query.
- **Dirty-to-dirty reconciliation (many-to-many).** Two or more messy lists with no clean reference, deduped/linked against each other. Harder; needs transitive clustering and is where OpenRefine's own clustering currently lives.

**Why generic fuzzy text matching underperforms here:** ordinary string similarity treats the code as undifferentiated text and is blind to its grammar. Reference codes are short, highly structured, delimiter-separated, often hierarchical, and carry numeric fields whose exact value is the whole point. Off-the-shelf "fuzzy match" will happily merge adjacent, unrelated items and miss genuine variants that differ only in formatting.

---

## 3. The core pipeline

A reliable reconciliation flow has four stages. Most of the quality comes from the first.

```
NORMALISE  →  BLOCK  →  SCORE  →  REVIEW
(canonical    (cheap     (weighted   (clerical
 form)         candidate  component-  confirmation,
               generation) aware       human-in-loop)
               at scale)   similarity)
```

The governing rule throughout: **protect the numerics, forgive the formatting.** Split each code into structural components and apply different tolerances per component — exact (or check-digit-validated) on numeric/sequential fields, fuzzy on prefixes and textual tokens.

---

## 4. Normalisation / canonicalisation (highest-leverage layer)

Do as much as possible deterministically *before* any similarity scoring. A canonicalisation pipeline typically includes:

- **Case folding** to a single case.
- **Unicode normalisation** — apply NFC or NFKC. This matters disproportionately in archives: diacritics, ligatures (æ, œ), compatibility characters, and visually-identical lookalikes are common and silently break exact matching. NFKC also folds things like full-width characters and some typographic variants.
- **Whitespace normalisation** — collapse runs, trim, standardise non-breaking spaces.
- **Delimiter normalisation** — slashes, dots, spaces, and hyphens are frequently interchangeable *within the same code*. Pick a canonical separator (or strip them and tokenise on component boundaries).
- **Prefix / abbreviation normalisation** — map known variants to a canonical token: `Ms.` / `ms` / `MS`, `Add.` / `Additional`, `f.` / `fol.` / `folio`, `vol.` / `v.`, etc. A small controlled vocabulary of repository-specific abbreviations pays off.
- **Numeric padding policy** — decide once whether `MS 5`, `MS 005`, and `MS 5` collapse. Either zero-pad to a fixed width or strip leading zeros; be consistent.
- **Tokenise on delimiters and compare component-by-component** rather than treating the code as one blob. This is what unlocks per-component tolerances later.

A useful mental model: normalisation should converge every spelling of the *same* code to one canonical string, so that a large fraction of links resolve by **exact match on the canonical form** — no fuzzy scoring needed at all. Fuzzy matching is then only for the residue that normalisation can't fully tame (genuine typos, OCR errors, transpositions).

---

## 5. Similarity & distance metrics

When you do need fuzzy comparison, the metric should fit the *component* being compared. Grouped by family:

| Family | Metrics | Best for | Notes for identifier matching |
|---|---|---|---|
| **Character edit** | Levenshtein; **Damerau–Levenshtein**; Hamming | Human typos, OCR errors | Damerau–Levenshtein adds *transpositions* (`Egetron`→`Egerton`) and is usually the better default. Hamming only works on equal-length strings — rarely useful here. |
| **Prefix-weighted** | Jaro; **Jaro–Winkler** | Codes sharing a leading prefix | Jaro–Winkler gives a bonus for common prefixes — a strong fit since shelfmarks almost always share a repository/collection prefix. The classic record-linkage metric. |
| **Set / q-gram** | Jaccard, **Dice/Sørensen**, cosine over character n-grams | Insertions, reordering, partial overlap | Degrades gracefully; underlies most scalable indexes (trigram indexes, MinHash). |
| **Token** | token-sort ratio, token-set ratio | Reordered or partially-overlapping component lists | Apply *after* tokenising the code into parts. The RapidFuzz / `thefuzz` family. |
| **Phonetic** | Soundex, Metaphone / Double Metaphone, NYSIIS | Sound-alike *names* | Mostly a red herring for codes — **except** where a segment encodes an author surname (Cutter numbers in LC classification, Dewey author marks). Apply only to that segment, if at all. |

**Practical libraries** (Python): **RapidFuzz** (fast, maintained successor to fuzzywuzzy), `jellyfish` (edit + phonetic), `textdistance`, `abydos` (very comprehensive), `python-Levenshtein`.

**The key discipline:** don't run one metric over the whole code. Run a forgiving metric (Damerau–Levenshtein, Jaro–Winkler, trigram-Dice) on the *prefix/textual* components and a strict comparison on the *numeric* components, then combine into a weighted score (see §9, scoring).

---

## 6. Blocking & indexing for scale

Naive all-pairs comparison is O(n²) and dies on real catalogues. (Confirmed in the wild: a naive `spellfix1` self-join over ~36k rows runs in minutes, not milliseconds.) You need **blocking** — only compare records that share a cheap key — and an index built for the candidate-generation step.

**General techniques**

- **Blocking keys** — compare only records sharing a normalised prefix, first token, or shared q-gram. Trades a little recall for a massive speed-up.
- **Sorted-neighbourhood** — sort on a key, slide a window, compare within the window.
- **q-gram / trigram inverted index** — index character n-grams; candidates are records sharing enough grams.
- **SymSpell (symmetric-delete)** — precomputes deletions for blazing-fast fuzzy lookup; *ideal when matching a dirty list against a clean authority list* (i.e. your primary mode).
- **BK-trees** — metric trees supporting edit-distance range queries.
- **MinHash + LSH** — approximate Jaccard over q-grams at scale; SimHash for near-duplicate detection.

**SQLite-native implementation (directly relevant — you're building on SQLite)**

SQLite already provides most of the candidate-generation machinery:

- **FTS5 trigram tokenizer** — `CREATE VIRTUAL TABLE … USING fts5(code, tokenize="trigram")`. Treats every 3-character run as a token, giving general **substring matching** plus, by default, **indexed `LIKE` and `GLOB`** pattern matching. This is your fast q-gram blocker for free. Caveats: substrings shorter than 3 chars don't match in full-text-query mode (the community `sqlite-better-trigram` tokenizer handles <3-char tokens); available since SQLite 3.34, with later versions more capable — pin a recent SQLite.
- **`spellfix1` virtual table** — SymSpell-style fuzzy vocabulary lookup combining a phonetic hash with edit distance. Build it over the canonical authority codes and query `WHERE word MATCH ? AND top=N` to get ranked near-matches with distances. This is essentially the authority-matching primitive, built in.
- **`editdist3()` with a custom cost table** — `spellfix1` lets you replace the default fixed-weight edit distance with `editdist3` and an **application-defined per-character cost table** (`edit_cost_table=…`). Defaults are ~100 for insert/delete, ~150 for substitution; setting a cost ≥ 10000 effectively *disables* that transform. **This is exactly where you encode "protect the numerics":** make digit↔digit substitutions (and digit insert/delete) prohibitively expensive so the fuzzy layer never "corrects" `12345` into `12346`, while leaving prefix/letter transforms cheap. You can also down-weight known-equivalent character pairs (e.g. `0`↔`O`, `1`↔`l`/`I`) for OCR-style errors.

So a SQLite-native stack looks like: **FTS5 trigram for fast candidate generation → `spellfix1`/`editdist3` (with a numeric-protecting cost table) for ranked fuzzy scoring → component-aware re-scoring in application code.** The forum-confirmed O(n²) warning is the reason candidate generation (blocking) must come first rather than scoring every pair.

---

## 7. Embeddings — honest assessment

Since vector/embedding approaches came up: **for matching the codes themselves, embeddings are usually the wrong first tool, and can be actively worse than edit distance.** Semantic embeddings are designed to place similar *meanings* close together — which means they'll map `MS 12345` and `MS 12346` to nearly identical vectors. That's catastrophic for identifier matching, where those are different items. Character/subword n-gram embeddings (fastText-style) capture *surface* similarity and are safer, but rarely beat a good q-gram + edit-distance pipeline on short structured codes, while adding an index to maintain.

**Where embeddings earn their place:** the *free-text fields around the codes* — titles, creator names, scope-and-content notes, dates expressed in prose. If reconciliation needs to fall back on descriptive metadata when the code is too mangled to match, semantic similarity over those fields is genuinely useful. Treat it as a secondary signal, not the primary key.

**If you go there, it stays inside SQLite:**

- **`sqlite-vec`** — the current, actively-maintained vector-search extension (pure C, no deps, a Mozilla Builders project; the successor to the now-deprecated `sqlite-vss`). Provides a `vec0` virtual table with KNN search and float/int8/**binary** vector types and multiple distance metrics (incl. Hamming for binary vectors).
- **`sqlite-vector`** (by SQLite AI) — an alternative that stores vectors as **BLOBs in ordinary tables** (no virtual table), with quantization and a low default memory footprint; convenient if you'd rather not introduce virtual tables.
- **Two-stage rerank pattern** — store binary-quantised vectors for a fast Hamming KNN to get ~100 candidates, then rerank those with cosine on the full float vectors. Keeps search broad *and* accurate, and runs comfortably on a laptop for hundreds of thousands of records.

Bottom line: build the deterministic + edit-distance pipeline first; add embeddings only as a descriptive-metadata fallback if measured recall demands it.

---

## 8. Domain-specific canonicalisation

The identifiers in this domain often have *known structure and standards*, which means canonicalise-then-exact-match frequently beats fuzzing.

**Archival reference codes**

- The leading repository portion is typically controlled. UK practice: country code + repository code + local reference (e.g. `GB` + an ARCHON/repository number + the local fonds/series/file/item reference), aligned with **ISIL / ISO 15511** for repository identifiers. Match that leading segment exactly or near-exactly; let the lower levels carry the fuzzy weight.
- Codes are **hierarchical** (fonds → series → file → item), following description standards like **ISAD(G)** and serialised in **EAD** (XML). Reconcile **component-by-component down the hierarchy**, optionally weighting the leaf level differently from the structural path.

**Bibliographic identifiers — canonicalise, then match *exactly*; fuzzing these is almost always a bug**

- **ISBN** — has check digits; ISBN-10 (mod-11, final digit may be `X`) and ISBN-13 (EAN-13, mod-10). Validate, and convert ISBN-10↔13 to a canonical form before comparing.
- **ISSN** — 8 digits, mod-11 check, final digit may be `X`.
- **LCCN** — has a defined *normalised* form; normalise before comparing.
- **OCLC numbers** — bare integers, sometimes carrying `ocm`/`ocn`/`on` prefixes; strip to the integer.

For all of these, exact match on the canonical/validated form is both faster and far safer than any similarity metric.

---

## 9. Architecture & build options

### 9.1 The reconciliation-protocol finding (read this before deciding the form factor)

OpenRefine reconciles against any service implementing the **Reconciliation Service API**, a protocol now stewarded by the **W3C Entity Reconciliation Community Group** (current widely-adopted version 0.2; a 1.0 draft is in progress). Mechanics: the client sends a **query string** (plus optional **type** and **property** constraints, e.g. a bound "date" or "creator" column) and the service returns a **ranked list of candidate entities with scores and identifiers**. Optional endpoints add **suggest**, **preview**, and **data-extension** (pull extra columns from a matched record back into the sheet).

Implication: **a backend that speaks this API is usable from vanilla OpenRefine immediately — no custom Java extension required** — and is simultaneously usable by other clients (Cocoda, scripts, etc.). Reference implementations to crib from: **`reconcile-csv`** (stands up a service from a single CSV) and **`csv-reconcile`** (a more configurable Python port). There's an official **reconciliation test bench** for validating conformance. Public exemplars built this way include VIAF, Wikidata, and ROR reconcilers.

### 9.2 Three build shapes (in order of increasing effort)

1. **Reconciliation service only (recommended MVP).** A small web service over your SQLite index that implements the Reconciliation Service API. Plugs into OpenRefine and others, no extension to maintain, and decouples the matching engine from any one client. Most of the leverage for the least code.
2. **Service + thin OpenRefine extension.** Add a lightweight extension *only* for UX niceties the bare protocol can't express (custom config UI, batch confirmation ergonomics, bespoke per-component tolerance controls).
3. **Full OpenRefine extension.** Justified only if the workflow must live entirely inside OpenRefine with deep UI integration. Highest maintenance burden (Java, version churn).

Worth weighing shape #1 hard before committing to building an extension at all.

### 9.3 Suggested matching pipeline for the tool

```
Ingest catalogues  ─► Normalise (canonical form + component split)  ─► Build SQLite indexes
   (MARC / EAD /        §4 pipeline, per-repository abbrev. table        (FTS5 trigram for blocking;
    CSV exports)                                                          spellfix1 over canonical codes;
                                                                          optional sqlite-vec for descriptive
                                                                          metadata fallback)
        │
        ▼
For each input code:  Normalise input  ─► Block (trigram/spellfix candidate set)  ─►
   Component-aware score (numeric=strict, prefix/text=fuzzy; weighted)  ─►
   Return ranked candidates + confidence  ─►  Clerical review / confirm  ─►  Emit link table
```

### 9.4 Scoring

Model the score as a **weighted combination of per-component similarities**, with the numeric components gated (a numeric mismatch should veto or near-veto the match regardless of how well the prefix matches). For a principled version, look at **probabilistic record linkage (Fellegi–Sunter)** as implemented by **Splink** — it learns per-field match/non-match weights and produces calibrated match probabilities, and runs on embedded engines (DuckDB) that sit comfortably alongside a SQLite workflow. You can either adopt Splink as the scoring engine or borrow its weighting model and implement a simpler version yourself.

### 9.5 Human-in-the-loop

Reconciliation of this kind should be **proposed, not auto-applied** — mirror OpenRefine's clustering UX: the tool surfaces ranked candidates with confidence, a curator confirms/rejects, and confirmations can propagate to identical values. Keep the original code alongside the matched identifier (never overwrite in place) so decisions are auditable and reversible. Surface the *evidence* for each candidate (which components matched, the edit distance, the score) so reviewers can adjudicate quickly.

---

## 10. Prior art worth mining

- **OpenRefine clustering internals** — two method families: *key collision* (fingerprint, n-gram fingerprint, phonetic) and *nearest neighbour* (Levenshtein, PPM/compression distance). Good reference for the dirty-to-dirty mode and for sensible defaults.
- **Splink** — probabilistic (Fellegi–Sunter) record linkage at scale on DuckDB/Spark; the model to emulate for §9.4.
- **`dedupe`** (active-learning record linkage) and the **`recordlinkage`** Python toolkit — for programmatic linkage and a menu of comparison functions.
- **`reconcile-csv` / `csv-reconcile`** — minimal reference reconciliation services to start from (§9.1).
- **The Reconciliation census / list of public endpoints** — examples of real services (VIAF, Wikidata, ROR, Getty ULAN/AAT/TGN) implementing the protocol.
- **Christen, *Data Matching* (Springer, 2012)** — the standard scholarly treatment of blocking, comparison, and classification.

---

## 11. Open questions to resolve during speccing

- **Which catalogue systems, and what export format?** MARC (records/authorities), EAD (archival hierarchy), or flat CSV/TSV dumps? This drives the ingest + normalisation layer and how much hierarchy you can exploit.
- **Primary mode: authority matching, dirty-to-dirty, or both?** Determines whether `spellfix1`-over-authority is sufficient or whether you also need transitive clustering.
- **Scale.** Thousands, hundreds of thousands, or millions of authority records? Sets whether brute-force-in-SQLite suffices or whether blocking must be aggressive (and whether embeddings/`sqlite-vec` are warranted).
- **Online vs batch.** Interactive per-cell reconciliation (favours a hosted service + fast lookup) vs bulk overnight linkage of whole spreadsheets (favours a batch pipeline)?
- **Per-repository configuration.** Each repository's abbreviation conventions, delimiter habits, padding rules, and hierarchy depth differ — how much of this should be configurable vs hard-coded?
- **Confidence thresholds & review policy.** Auto-accept above some calibrated probability? Always require clerical confirmation? What's the audit trail requirement?

---

## References

- OpenRefine — Reconciliation API (technical reference): https://openrefine.org/docs/technical-reference/reconciliation-api
- W3C Entity Reconciliation Community Group — spec (1.0 draft): https://reconciliation-api.github.io/specs/1.0-draft/ ; FINAL 0.1: https://www.w3.org/community/reports/reconciliation/CG-FINAL-specs-0.1-20230321/
- OpenRefine — Reconciling (user manual): https://openrefine.org/docs/manual/reconciling
- SQLite — FTS5 (trigram tokenizer): https://sqlite.org/fts5.html
- SQLite — `spellfix1` virtual table (`editdist3`, cost tables): https://sqlite.org/spellfix1.html
- `sqlite-better-trigram` (handles <3-char tokens): https://github.com/streetwriters/sqlite-better-trigram
- `sqlite-vec` (current vector extension; successor to `sqlite-vss`): https://github.com/asg017/sqlite-vec
- `sqlite-vector` (BLOB-column vectors, quantization): https://github.com/sqliteai/sqlite-vector
- Splink (probabilistic record linkage): https://moj-analytical-services.github.io/splink/
- `reconcile-csv`: http://okfnlabs.org/reconcile-csv/ — and `csv-reconcile` (Python port): https://github.com/gitonthescene/csv-reconcile
- Christen, P. *Data Matching*. Springer, 2012.

*(Links current as of June 2026; verify SQLite extension versions and the reconciliation-API version against your target before building.)*

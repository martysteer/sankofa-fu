# sankofa-fu-refine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An OpenRefine 3.10 extension that matches a column of reference codes against a "spine" column in another (or the same) OpenRefine project, via a clustering-style dialog, using sankofa-fú's component-aware matching ported to Clojure.

**Architecture:** Pure-Clojure matching engine (port of the Python `sankofa_fu` core: normalise → tokenise → block → score), AOT-compiled into a jar. Two thin Java classes (`ComputeMatchesCommand`, `ApplyMatchesOperation` + its command) bridge OpenRefine's servlet/undo machinery to the Clojure engine. Vanilla-JS dialog modeled on Cluster & Edit. Repo structure copied from loupe.

**Tech Stack:** Clojure 1.12, Leiningen, Java (2 small classes), OpenRefine 3.10 extension API (Butterfly module, Commands, Operations, Changes), jQuery-era OpenRefine frontend JS. No external string-metric dependency — Jaro–Winkler and OSA Damerau–Levenshtein implemented in Clojure so the extension ships as one self-contained jar (like loupe).

**Spec:** `docs/superpowers/specs/2026-07-08-sankofa-fu-refine-design.md` (in the sankofa-fú repo).

**New repo location:** `/Users/marty/Devel/sankofa-fu-refine`

**Reference sources (read-only during implementation):**
- Python canonical engine: `/Users/marty/Devel/sankofa-fú/src/sankofa_fu/` (normalise.py, grammar.py, scoring.py, blocking.py, engine.py, schemes/)
- Test fixtures to copy: `/Users/marty/Devel/sankofa-fú/tests/fixtures/catalogue.csv`, `labelled_pairs.csv`
- Extension template: `/Users/marty/Devel/loupe/` (project.clj, Makefile, extension/module/MOD-INF/, scripts/)

**Known API-verification points (check against OpenRefine 3.10 source when you reach Tasks 10–11; the plan flags each):**
1. `org.openrefine:main:3.10.0` availability on Maven Central (fallback documented in Task 1).
2. `com.google.refine.model.changes.MassChange` constructor `(List<? extends Change>, boolean)` (fallback `CompositeChange` provided in Task 11).
3. `EngineDependentCommand.createOperation(Project, HttpServletRequest, JsonNode)` signature.
4. Clojure version bundled with OpenRefine 3.10 (loupe works with 1.12.3 AOT, so 1.12.3 is assumed safe).

---

### Task 1: Scaffold repo + build plumbing

**Files:**
- Create: `/Users/marty/Devel/sankofa-fu-refine/project.clj`
- Create: `/Users/marty/Devel/sankofa-fu-refine/Makefile`
- Create: `/Users/marty/Devel/sankofa-fu-refine/.gitignore`
- Create: `/Users/marty/Devel/sankofa-fu-refine/extension/module/MOD-INF/module.properties`
- Create: `/Users/marty/Devel/sankofa-fu-refine/extension/module/MOD-INF/controller.js`
- Create: `/Users/marty/Devel/sankofa-fu-refine/test/fixtures/catalogue.csv` (copy)
- Create: `/Users/marty/Devel/sankofa-fu-refine/test/fixtures/labelled_pairs.csv` (copy)
- Create: `/Users/marty/Devel/sankofa-fu-refine/test/fixtures/dirty.csv`

- [ ] **Step 1: Create repo and copy fixtures**

```bash
mkdir -p /Users/marty/Devel/sankofa-fu-refine
cd /Users/marty/Devel/sankofa-fu-refine
git init
mkdir -p src/sankofa_fu src/java/com/sankofafu test/sankofa_fu test/fixtures \
  extension/module/MOD-INF/lib extension/module/scripts extension/module/styles
cp "/Users/marty/Devel/sankofa-fú/tests/fixtures/catalogue.csv" test/fixtures/
cp "/Users/marty/Devel/sankofa-fú/tests/fixtures/labelled_pairs.csv" test/fixtures/
```

- [ ] **Step 2: Write `test/fixtures/dirty.csv`** (the dirty column of labelled_pairs, used for manual E2E later)

```csv
shelfmark
rm C/801/K/5
MS  012345
Ms. 12345
Egetron 3025
EGERTN 3025
MS I2345
RM c.502.p.1 (1)
RM c.502.p.1 (11)
MS 12345
RM c.801.k.5
```

- [ ] **Step 3: Write `project.clj`**

```clojure
(defproject com.sankofafu/sankofa-fu-refine "0.1.0"
  :description "OpenRefine extension: match reference-code columns against a data spine"
  :license {:name "CC-BY"}
  :dependencies [[org.clojure/clojure "1.12.3"]
                 [org.openrefine/main "3.10.0" :scope "provided"]
                 [javax.servlet/javax.servlet-api "3.1.0" :scope "provided"]]
  :java-source-paths ["src/java"]
  :source-paths ["src"]
  :test-paths ["test"]
  :target-path "target"
  :aot [sankofa-fu.metrics
        sankofa-fu.normalise
        sankofa-fu.schemes
        sankofa-fu.scoring
        sankofa-fu.blocking
        sankofa-fu.classic
        sankofa-fu.engine]
  :jar-name "sankofa-fu.jar")
```

**Verification point 1:** if `lein deps` fails to resolve `org.openrefine/main 3.10.0`, install it locally from your OpenRefine install:

```bash
mvn install:install-file \
  -Dfile="/path/to/openrefine-3.10/server/target/lib/openrefine-main.jar" \
  -DgroupId=org.openrefine -DartifactId=main -Dversion=3.10.0 -Dpackaging=jar
```

(Exact jar name varies; look for the jar containing `com/google/refine/commands/Command.class`. If Jackson classes are missing at `lein javac` time in Task 10, add `[com.fasterxml.jackson.core/jackson-databind "2.15.0" :scope "provided"]`.)

- [ ] **Step 4: Write `Makefile`** (loupe's, renamed)

```makefile
EXTENSION_DIR = extension/module/MOD-INF/lib
INSTALL_DIR = $(HOME)/Library/Application Support/OpenRefine/extensions/sankofa-fu

.PHONY: jar test extension install clean zip

jar:
	lein jar

test:
	lein test

extension: jar
	mkdir -p $(EXTENSION_DIR)
	cp target/sankofa-fu.jar $(EXTENSION_DIR)/sankofa-fu.jar

install: extension
	rm -rf "$(INSTALL_DIR)"
	mkdir -p "$(INSTALL_DIR)"
	cp -R extension/module/ "$(INSTALL_DIR)/"

clean:
	lein clean
	rm -f $(EXTENSION_DIR)/sankofa-fu.jar

zip: extension
	mkdir -p dist/sankofa-fu
	cp -R extension/module/ dist/sankofa-fu/
	cd dist && zip -r sankofa-fu.zip sankofa-fu
	rm -rf dist/sankofa-fu
```

- [ ] **Step 5: Write `.gitignore`**

```
target/
dist/
extension/module/MOD-INF/lib/*.jar
.lein-*
```

- [ ] **Step 6: Write `extension/module/MOD-INF/module.properties`**

```properties
name = sankofa-fu
module-impl = com.google.butterfly.BasicModuleImpl
requires = core
```

- [ ] **Step 7: Write minimal `extension/module/MOD-INF/controller.js`** (commands/operation registration added in Tasks 10–12; keep placeholders out — this version only registers client assets, which don't exist yet either, so it is an empty init)

```javascript
function init() {
  // Command, operation, and client-asset registration is added in later tasks.
}
```

- [ ] **Step 8: Verify build plumbing**

Run: `cd /Users/marty/Devel/sankofa-fu-refine && lein test`
Expected: `0 tests, 0 assertions, 0 failures` (or "No tests found") — proves lein + deps resolve.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "chore: scaffold sankofa-fu-refine extension (lein, Makefile, module skeleton, fixtures)"
```

---

### Task 2: metrics.clj — Jaro–Winkler + OSA Damerau–Levenshtein

**Files:**
- Create: `src/sankofa_fu/metrics.clj`
- Test: `test/sankofa_fu/metrics_test.clj`

Pure-Clojure ports so the jar has zero runtime deps beyond Clojure (which OpenRefine bundles for its `clojure:` expression language — same assumption loupe relies on).

- [ ] **Step 1: Write the failing test**

```clojure
(ns sankofa-fu.metrics-test
  (:require [clojure.test :refer [deftest is]]
            [sankofa-fu.metrics :as m]))

(defn- approx [a b] (< (Math/abs (- a b)) 0.005))

(deftest jaro-winkler-known-values
  (is (= 1.0 (m/jaro-winkler "MARTHA" "MARTHA")))
  (is (approx 0.961 (m/jaro-winkler "MARTHA" "MARHTA")))
  (is (approx 0.813 (m/jaro-winkler "DIXON" "DICKSONX")))
  (is (approx 0.840 (m/jaro-winkler "DWAYNE" "DUANE")))
  (is (= 0.0 (m/jaro-winkler "ABC" "XYZ"))))

(deftest damerau-normalised
  (is (= 1.0 (m/damerau "EGERTON" "EGERTON")))
  ;; adjacent transposition counts 1: distance 1 over max-len 7
  (is (approx (- 1.0 (/ 1.0 7.0)) (m/damerau "EGETRON" "EGERTON")))
  ;; kitten->sitting distance 3 over 7
  (is (approx (- 1.0 (/ 3.0 7.0)) (m/damerau "kitten" "sitting")))
  (is (= 1.0 (m/damerau "" ""))))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `lein test sankofa-fu.metrics-test`
Expected: FAIL (namespace `sankofa-fu.metrics` not found).

- [ ] **Step 3: Write `src/sankofa_fu/metrics.clj`**

```clojure
(ns sankofa-fu.metrics
  "String similarity metrics, 0.0-1.0. Jaro-Winkler for prefix components
  (matches rapidfuzz JaroWinkler.normalized_similarity), OSA
  Damerau-Levenshtein for other alpha components.")

(defn- jaro [^String a ^String b]
  (let [la (count a) lb (count b)]
    (cond
      (and (zero? la) (zero? lb)) 1.0
      (or (zero? la) (zero? lb)) 0.0
      :else
      (let [window (max 0 (dec (quot (max la lb) 2)))
            b-matched (boolean-array lb)
            a-matches (java.util.ArrayList.)]
        (dotimes [i la]
          (let [lo (max 0 (- i window))
                hi (min (dec lb) (+ i window))]
            (loop [j lo]
              (when (<= j hi)
                (if (and (not (aget b-matched j))
                         (= (.charAt a i) (.charAt b j)))
                  (do (aset b-matched j true)
                      (.add a-matches (.charAt a i)))
                  (recur (inc j)))))))
        (let [m (.size a-matches)]
          (if (zero? m)
            0.0
            (let [b-matches (java.util.ArrayList.)]
              (dotimes [j lb]
                (when (aget b-matched j) (.add b-matches (.charAt b j))))
              (let [t (/ (count (filter true? (map not= a-matches b-matches))) 2.0)]
                (/ (+ (/ m (double la))
                      (/ m (double lb))
                      (/ (- m t) (double m)))
                   3.0)))))))))

(defn jaro-winkler
  "Jaro-Winkler similarity with standard prefix scale 0.1, max prefix 4."
  [^String a ^String b]
  (let [j (jaro a b)
        limit (min 4 (count a) (count b))
        prefix (loop [i 0]
                 (if (and (< i limit) (= (.charAt a i) (.charAt b i)))
                   (recur (inc i))
                   i))]
    (+ j (* prefix 0.1 (- 1.0 j)))))

(defn- osa-distance
  "Optimal string alignment distance (Damerau-Levenshtein with adjacent
  transpositions, no substring re-edit). ponytail: OSA not full DL — every
  fixture transposition is adjacent; upgrade to full DL if a fixture needs it."
  [^String a ^String b]
  (let [la (count a) lb (count b)
        d (make-array Long/TYPE (inc la) (inc lb))]
    (dotimes [i (inc la)] (aset d i 0 (long i)))
    (dotimes [j (inc lb)] (aset d 0 j (long j)))
    (doseq [i (range 1 (inc la))
            j (range 1 (inc lb))]
      (let [cost (if (= (.charAt a (dec i)) (.charAt b (dec j))) 0 1)
            best (min (inc (aget d (dec i) j))
                      (inc (aget d i (dec j)))
                      (+ (aget d (dec i) (dec j)) cost))
            best (if (and (> i 1) (> j 1)
                          (= (.charAt a (dec i)) (.charAt b (- j 2)))
                          (= (.charAt a (- i 2)) (.charAt b (dec j))))
                   (min best (inc (aget d (- i 2) (- j 2))))
                   best)]
        (aset d i j (long best))))
    (aget d la lb)))

(defn damerau
  "Normalised OSA Damerau-Levenshtein similarity."
  [^String a ^String b]
  (let [m (max (count a) (count b))]
    (if (zero? m)
      1.0
      (- 1.0 (/ (osa-distance a b) (double m))))))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `lein test sankofa-fu.metrics-test`
Expected: PASS (2 tests, 9 assertions).

- [ ] **Step 5: Commit**

```bash
git add src/sankofa_fu/metrics.clj test/sankofa_fu/metrics_test.clj
git commit -m "feat: Jaro-Winkler and OSA Damerau-Levenshtein metrics"
```

---

### Task 3: normalise.clj — canonicalisation pipeline

**Files:**
- Create: `src/sankofa_fu/normalise.clj`
- Test: `test/sankofa_fu/normalise_test.clj`

Port of `normalise.py`: NFKC → upper → NBSP → delimiters → whitespace → abbreviations → numeric padding. Config is a plain keyword map (built by `engine/->cfg` in Task 8); this namespace only reads `:delimiters`, `:abbreviations`, `:padding`.

- [ ] **Step 1: Write the failing test**

```clojure
(ns sankofa-fu.normalise-test
  (:require [clojure.test :refer [deftest is]]
            [sankofa-fu.normalise :as n]))

(def cfg {:delimiters ["." "/" "-" " "]
          :abbreviations {"ms" "MS"}
          :padding "strip"})

(deftest delimiters-and-case
  (is (= "RM C 801 K 5" (n/normalise "rm C/801/K/5" cfg)))
  (is (= "RM C 801 K 5" (n/normalise "RM c.801.k.5" cfg))))

(deftest whitespace-and-nbsp
  (is (= "MS 12345" (n/normalise "MS\u00a0 12345" cfg))))

(deftest abbreviations
  (is (= "MS 12345" (n/normalise "Ms. 12345" cfg))))

(deftest padding-strip
  (is (= "MS 12345" (n/normalise "MS  012345" cfg))))

(deftest padding-pad
  (is (= "MS 00001" (n/normalise "MS 1" (assoc cfg :padding "pad:5"))))
  (is (= "MS 12345" (n/normalise "MS 12345" (assoc cfg :padding "pad:5")))))

(deftest bad-padding-throws
  (is (thrown? IllegalArgumentException
               (n/normalise "MS 1" (assoc cfg :padding "wat")))))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `lein test sankofa-fu.normalise-test`
Expected: FAIL (namespace not found).

- [ ] **Step 3: Write `src/sankofa_fu/normalise.clj`**

```clojure
(ns sankofa-fu.normalise
  "Canonicalisation pipeline (Python normalise.py, spec §3.1). Order matters:
  NFKC → upper → NBSP → delimiters → whitespace → abbreviations → padding."
  (:require [clojure.string :as str])
  (:import (java.text Normalizer Normalizer$Form)
           (java.util Locale)
           (java.util.regex Matcher Pattern)))

(defn normalise [^String text cfg]
  (let [s (-> (Normalizer/normalize text Normalizer$Form/NFKC)
              (.toUpperCase Locale/ROOT)
              (str/replace "\u00a0" " "))
        s (reduce (fn [^String s ^String d]
                    (if (= d " ") s (str/replace s d " ")))
                  s (:delimiters cfg))
        s (-> s (str/replace #"\s+" " ") str/trim)
        s (reduce (fn [s [src dst]]
                    (str/replace s
                                 (re-pattern (str "\\b"
                                                  (Pattern/quote (str/upper-case src))
                                                  "\\b"))
                                 (Matcher/quoteReplacement (str/upper-case dst))))
                  s (:abbreviations cfg))
        padding (:padding cfg)]
    (cond
      (= padding "strip")
      (str/replace s #"\b0+(\d)" "$1")

      (str/starts-with? (str padding) "pad:")
      (let [width (Long/parseLong (subs padding 4))]
        (str/replace s #"\d+"
                     (fn [m]
                       (let [pad (- width (count m))]
                         (if (pos? pad)
                           (str (apply str (repeat pad "0")) m)
                           m)))))

      :else
      (throw (IllegalArgumentException. (str "bad padding: " (pr-str padding)))))))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `lein test sankofa-fu.normalise-test`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/sankofa_fu/normalise.clj test/sankofa_fu/normalise_test.clj
git commit -m "feat: canonicalisation pipeline (port of normalise.py)"
```

---

### Task 4: schemes.clj — tokeniser grammars

**Files:**
- Create: `src/sankofa_fu/schemes.clj`
- Test: `test/sankofa_fu/schemes_test.clj`

Port of `grammar.py` + `schemes/`. A component is a 2-vector `[kind value]` where kind ∈ `"ALPHA" "NUM" "ID" "RAW"` (simpler than Python's dataclass; JSON-shaped already). A scheme is a map `{:tokenise fn, :canonicalise fn?}` — `:canonicalise` (isbn/issn only) replaces the normalise pipeline and throws on invalid check digits.

- [ ] **Step 1: Write the failing test**

```clojure
(ns sankofa-fu.schemes-test
  (:require [clojure.test :refer [deftest is]]
            [sankofa-fu.schemes :as s]))

(deftest archival-tokenise
  (is (= [["ALPHA" "RM"] ["ALPHA" "C"] ["NUM" 801] ["ALPHA" "K"] ["NUM" 5]]
         (s/tokenise "RM C 801 K 5" "archival")))
  ;; parens are ignored by the token regex
  (is (= [["ALPHA" "RM"] ["ALPHA" "C"] ["NUM" 502] ["ALPHA" "P"] ["NUM" 1] ["NUM" 1]]
         (s/tokenise "RM C 502 P 1 (1)" "archival")))
  ;; letter/digit boundary splits within a run
  (is (= [["ALPHA" "MS"] ["NUM" 12345]] (s/tokenise "MS12345" "archival"))))

(deftest raw-tokenise
  (is (= [["RAW" "ANYTHING AT ALL"]] (s/tokenise "ANYTHING AT ALL" "raw"))))

(deftest isbn-canonicalise
  ;; known-valid ISBN-10 with its ISBN-13 form
  (is (= "9780306406157" (s/canonical-isbn "0-306-40615-2")))
  (is (= "9780306406157" (s/canonical-isbn "978 0 306 40615 7")))
  (is (thrown? IllegalArgumentException (s/canonical-isbn "0-306-40615-3")))
  (is (thrown? IllegalArgumentException (s/canonical-isbn "12345"))))

(deftest issn-canonicalise
  (is (= "0378-5955" (s/canonical-issn "03785955")))
  (is (thrown? IllegalArgumentException (s/canonical-issn "0378-5954"))))

(deftest id-tokenise
  (is (= [["ID" "9780306406157"]] (s/tokenise "9780306406157" "isbn"))))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `lein test sankofa-fu.schemes-test`
Expected: FAIL (namespace not found).

- [ ] **Step 3: Write `src/sankofa_fu/schemes.clj`**

```clojure
(ns sankofa-fu.schemes
  "Tokeniser grammars (Python grammar.py + schemes/, spec §3.2-3.3).
  Component = [kind value], kind ∈ ALPHA NUM ID RAW."
  (:require [clojure.string :as str]))

(defn- digit-char [ch]
  (Character/digit (char ch) 10))

(defn- digits [s]
  (str/upper-case (str/replace s #"[\s\-]" "")))

(defn- ean13-check [first12]
  (let [total (reduce + (map-indexed
                          (fn [i ch] (* (digit-char ch) (if (even? i) 1 3)))
                          first12))]
    (str (mod (- 10 (mod total 10)) 10))))

(defn canonical-isbn [raw]
  (let [d (digits raw)]
    (cond
      (= 10 (count d))
      (let [total (reduce + (map-indexed
                              (fn [i ch] (* (- 10 i) (if (= ch \X) 10 (digit-char ch))))
                              d))]
        (when-not (zero? (mod total 11))
          (throw (IllegalArgumentException.
                   (str "ISBN-10 check digit invalid: " (pr-str raw)))))
        (let [core (str "978" (subs d 0 9))]
          (str core (ean13-check core))))

      (and (= 13 (count d)) (re-matches #"\d+" d))
      (do (when-not (= (str (nth d 12)) (ean13-check (subs d 0 12)))
            (throw (IllegalArgumentException.
                     (str "ISBN-13 check digit invalid: " (pr-str raw)))))
          d)

      :else
      (throw (IllegalArgumentException. (str "not an ISBN: " (pr-str raw)))))))

(defn canonical-issn [raw]
  (let [d (digits raw)]
    (when-not (= 8 (count d))
      (throw (IllegalArgumentException. (str "not an ISSN: " (pr-str raw)))))
    (let [total (reduce + (map-indexed
                            (fn [i ch] (* (- 8 i) (if (= ch \X) 10 (digit-char ch))))
                            d))]
      (when-not (zero? (mod total 11))
        (throw (IllegalArgumentException.
                 (str "ISSN check digit invalid: " (pr-str raw)))))
      (str (subs d 0 4) "-" (subs d 4)))))

(defn- tokenise-archival [canonical]
  (->> (re-seq #"[A-Z\u00C0-\u024F]+|\d+" canonical)
       (mapv (fn [tok]
               (if (re-matches #"\d+" tok)
                 ["NUM" (Long/parseLong tok)]
                 ["ALPHA" tok])))))

(def schemes
  {"archival" {:tokenise tokenise-archival}
   "raw"      {:tokenise (fn [c] [["RAW" c]])}
   "isbn"     {:tokenise (fn [c] [["ID" c]]) :canonicalise canonical-isbn}
   "issn"     {:tokenise (fn [c] [["ID" c]]) :canonicalise canonical-issn}})

(defn tokenise [canonical scheme]
  ((:tokenise (get schemes scheme)) canonical))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `lein test sankofa-fu.schemes-test`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/sankofa_fu/schemes.clj test/sankofa_fu/schemes_test.clj
git commit -m "feat: tokeniser grammars — archival, isbn, issn, raw"
```

---

### Task 5: scoring.clj — component-aware scoring

**Files:**
- Create: `src/sankofa_fu/scoring.clj`
- Test: `test/sankofa_fu/scoring_test.clj`

Port of `scoring.py`: pairwise in-order alignment, numeric gate (veto | penalty:N), JW for component 0, OSA-DL for later ALPHA components, ID exact-only, unmatched trailing components penalised, OCR-confusable retry at canonical-string level. Evidence entries are string-keyed maps (Jackson-friendly). Reads cfg keys `:numeric-gate :weights :ocr-confusables`.

- [ ] **Step 1: Write the failing test**

```clojure
(ns sankofa-fu.scoring-test
  (:require [clojure.test :refer [deftest is]]
            [sankofa-fu.scoring :as sc]))

(def cfg {:numeric-gate "veto"
          :weights {"prefix" 2.0 "alpha" 1.0}
          :ocr-confusables true})

(deftest identical-components-score-100
  (let [r (sc/score-components [["ALPHA" "RM"] ["NUM" 801]]
                               [["ALPHA" "RM"] ["NUM" 801]] cfg)]
    (is (= 100 (:score r)))
    (is (= 2 (count (:evidence r))))))

(deftest numeric-veto-zeroes-score
  (is (= 0 (:score (sc/score-components [["ALPHA" "RM"] ["NUM" 801]]
                                        [["ALPHA" "RM"] ["NUM" 802]] cfg)))))

(deftest numeric-penalty-caps-score
  (let [r (sc/score-components [["ALPHA" "RM"] ["NUM" 801]]
                               [["ALPHA" "RM"] ["NUM" 802]]
                               (assoc cfg :numeric-gate "penalty:50"))]
    ;; base = (2*1.0 + 1*0.0)/3 = 0.6667, × 0.5 → 33
    (is (= 33 (:score r)))))

(deftest typo-scores-high-not-exact
  (let [r (sc/score-canonical "EGETRON 3025" "EGERTON 3025" "archival" cfg)]
    (is (< 85 (:score r) 100))))

(deftest unmatched-trailing-penalised
  (let [full (sc/score-components [["NUM" 1]] [["NUM" 1]] cfg)
        trail (sc/score-components [["NUM" 1]] [["NUM" 1] ["NUM" 11]] cfg)]
    (is (< (:score trail) (:score full)))))

(deftest id-mismatch-vetoes
  (is (= 0 (:score (sc/score-components [["ID" "A"]] [["ID" "B"]] cfg)))))

(deftest ocr-confusables-rescue
  ;; "MS I2345" tokenises ALPHA MS + ALPHA I + NUM 2345 — shape differs from
  ;; "MS 12345"; translation I→1 makes them identical → 100
  (let [r (sc/score-canonical "MS I2345" "MS 12345" "archival" cfg)]
    (is (= 100 (:score r))))
  ;; disabled → no rescue
  (let [r (sc/score-canonical "MS I2345" "MS 12345" "archival"
                              (assoc cfg :ocr-confusables false))]
    (is (< (:score r) 100))))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `lein test sankofa-fu.scoring-test`
Expected: FAIL (namespace not found).

- [ ] **Step 3: Write `src/sankofa_fu/scoring.clj`**

```clojure
(ns sankofa-fu.scoring
  "Component-aware scoring (Python scoring.py, spec §5). Alignment: pairwise
  in order. Combine: weighted mean × numeric gate. OCR confusables applied at
  canonical-string level because translation can change tokenisation shape."
  (:require [clojure.string :as str]
            [sankofa-fu.metrics :as metrics]
            [sankofa-fu.schemes :as schemes]))

(defn translate-confusables [s]
  (str/escape s {\O "0" \L "1" \I "1"}))

(defn- text-sim [a b first?]
  (if first?
    (metrics/jaro-winkler a b)
    (metrics/damerau a b)))

(defn- evidence-entry [q c sim detail]
  {"query" q "candidate" c
   "similarity" (/ (Math/round (* (double sim) 1000)) 1000.0)
   "detail" detail})

(defn score-components
  "query/cand: vectors of [kind value]. Returns {:score 0-100 :evidence [..]}."
  [query cand cfg]
  (let [n (max (count query) (count cand))
        weights (:weights cfg)]
    (loop [i 0, weighted 0.0, wsum 0.0, vetoed false, gate 1.0, evidence []]
      (if (= i n)
        (let [base (if (pos? wsum) (/ weighted wsum) 0.0)]
          {:score (if vetoed 0 (int (Math/round (* base gate 100))))
           :evidence evidence})
        (let [q (get query i)
              c (get cand i)
              w (double (if (zero? i)
                          (get weights "prefix" 2.0)
                          (get weights "alpha" 1.0)))]
          (if (or (nil? q) (nil? c))
            (recur (inc i) weighted (+ wsum w) vetoed gate
                   (conj evidence (evidence-entry (second q) (second c)
                                                  0.0 "unmatched")))
            (let [[qk qv] q
                  [ck cv] c
                  [sim detail vetoed' gate']
                  (cond
                    (and (= qk "NUM") (= ck "NUM"))
                    (if (= qv cv)
                      [1.0 "num exact" vetoed gate]
                      (if (= (:numeric-gate cfg) "veto")
                        [0.0 "num mismatch (veto)" true gate]
                        [0.0 (str "num mismatch (" (:numeric-gate cfg) ")")
                         vetoed
                         (/ (Long/parseLong
                              (second (str/split (:numeric-gate cfg) #":")))
                            100.0)]))

                    (or (= qk "ID") (= ck "ID"))
                    (if (and (= qk ck) (= qv cv))
                      [1.0 "id exact" vetoed gate]
                      [0.0 "id mismatch" true gate])

                    (not= qk ck)
                    [0.0 "kind mismatch" vetoed gate]

                    :else
                    [(text-sim (str qv) (str cv) (zero? i)) "text fuzzy"
                     vetoed gate])]
              (recur (inc i)
                     (+ weighted (* (double sim) w))
                     (+ wsum w)
                     vetoed' gate'
                     (conj evidence (evidence-entry qv cv sim detail))))))))))

(defn score-canonical
  "Score two canonical strings under a scheme; retry with OCR-confusable
  translation if enabled and it improves the score."
  [q-can c-can scheme cfg]
  (let [base (score-components (schemes/tokenise q-can scheme)
                               (schemes/tokenise c-can scheme) cfg)]
    (if (and (:ocr-confusables cfg) (< (:score base) 100))
      (let [qt (translate-confusables q-can)
            ct (translate-confusables c-can)]
        (if (or (not= qt q-can) (not= ct c-can))
          (let [alt (score-components (schemes/tokenise qt scheme)
                                      (schemes/tokenise ct scheme) cfg)]
            (if (> (:score alt) (:score base))
              {:score (:score alt)
               :evidence (conj (:evidence alt)
                               {"query" q-can "candidate" c-can
                                "similarity" (/ (:score alt) 100.0)
                                "detail" "ocr-confusables applied"})}
              base))
          base))
      base)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `lein test sankofa-fu.scoring-test`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/sankofa_fu/scoring.clj test/sankofa_fu/scoring_test.clj
git commit -m "feat: component-aware scoring with numeric gate and OCR rescue"
```

---

### Task 6: blocking.clj — in-memory candidate generation

**Files:**
- Create: `src/sankofa_fu/blocking.clj`
- Test: `test/sankofa_fu/blocking_test.clj`

Replaces Python's SQLite/FTS5 blocker with an in-memory index: exact map on canonical string + trigram inverted index. Candidates ranked by shared-trigram count (deliberate divergence from FTS5's OR-match — same recall purpose, better ranking). Records are string-keyed maps `{"id" "code" "canonical"}`.

- [ ] **Step 1: Write the failing test**

```clojure
(ns sankofa-fu.blocking-test
  (:require [clojure.test :refer [deftest is]]
            [sankofa-fu.blocking :as b]))

(def records
  [{"id" "r1" "code" "RM c.801.k.5"  "canonical" "RM C 801 K 5"}
   {"id" "r2" "code" "RM c.801.k.15" "canonical" "RM C 801 K 15"}
   {"id" "r5" "code" "MS 12345"      "canonical" "MS 12345"}
   {"id" "r5b" "code" "ms 12345"     "canonical" "MS 12345"}
   {"id" "r7" "code" "Egerton 3025"  "canonical" "EGERTON 3025"}])

(def index (b/build-index records))

(deftest exact-lookup
  (is (= ["r1"] (map #(get % "id") (b/exact index "RM C 801 K 5"))))
  ;; duplicate canonicals both returned (ambiguous exact)
  (is (= #{"r5" "r5b"} (set (map #(get % "id") (b/exact index "MS 12345")))))
  (is (empty? (b/exact index "NOPE"))))

(deftest trigram-candidates-rank-by-overlap
  (let [cands (b/candidates index "EGETRON 3025" 10)]
    ;; r7 shares the most trigrams → first
    (is (= "r7" (get (first cands) "id"))))
  (let [cands (b/candidates index "RM C 801 K 5" 10)]
    (is (contains? (set (map #(get % "id") cands)) "r1"))))

(deftest limit-respected
  (is (<= (count (b/candidates index "M" 2)) 2)))

(deftest no-overlap-no-candidates
  (is (empty? (b/candidates index "ZZZZZZ" 10))))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `lein test sankofa-fu.blocking-test`
Expected: FAIL (namespace not found).

- [ ] **Step 3: Write `src/sankofa_fu/blocking.clj`**

```clojure
(ns sankofa-fu.blocking
  "In-memory candidate generation (replaces Python's SQLite/FTS5 blocker;
  spec §2). Exact map + trigram inverted index, candidates ranked by
  shared-trigram count.")

(defn- trigrams [^String s]
  (if (< (count s) 3)
    #{s}
    (set (map #(subs s % (+ % 3)) (range (- (count s) 2))))))

(defn build-index
  "records: seq of {\"id\" \"code\" \"canonical\"}."
  [records]
  (let [v (vec records)]
    {:records v
     :by-canonical (group-by #(get % "canonical") v)
     :by-trigram (reduce (fn [m [i r]]
                           (reduce (fn [m t] (update m t (fnil conj []) i))
                                   m
                                   (trigrams (get r "canonical"))))
                         {}
                         (map-indexed vector v))}))

(defn exact [index canonical]
  (get (:by-canonical index) canonical []))

(defn candidates
  "Records sharing ≥1 trigram with canonical, ranked by shared-trigram
  count, capped at limit."
  [index canonical limit]
  (let [counts (reduce (fn [m t]
                         (reduce (fn [m i] (update m i (fnil inc 0)))
                                 m
                                 (get-in index [:by-trigram t])))
                       {}
                       (trigrams canonical))]
    (->> counts
         (sort-by (comp - val))
         (take limit)
         (mapv #(nth (:records index) (key %))))))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `lein test sankofa-fu.blocking-test`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/sankofa_fu/blocking.clj test/sankofa_fu/blocking_test.clj
git commit -m "feat: in-memory trigram blocking"
```

---

### Task 7: classic.clj — fingerprint + levenshtein methods

**Files:**
- Create: `src/sankofa_fu/classic.clj`
- Test: `test/sankofa_fu/classic_test.clj`

OpenRefine-style methods for codes that aren't classmark-shaped. Fingerprint = key collision on the classic fingerprint key; levenshtein = normalised OSA-DL similarity as score (labelled "levenshtein" in the UI; uses OSA — close enough, documented).

- [ ] **Step 1: Write the failing test**

```clojure
(ns sankofa-fu.classic-test
  (:require [clojure.test :refer [deftest is]]
            [sankofa-fu.classic :as c]))

(deftest fingerprint-key
  (is (= "cruise tom" (c/fingerprint "  Tom   Cruise ")))
  (is (= "cruise tom" (c/fingerprint "Cruise, Tom.")))
  (is (= "cruise tom" (c/fingerprint "TOM CRUISE tom")))   ; dedupe + sort
  (is (= "" (c/fingerprint "  ,,, "))))

(deftest levenshtein-score
  (is (= 100 (c/levenshtein-score "MS 123" "ms 123")))
  ;; kitten/sitting: 1 - 3/7 = 0.571 → 57
  (is (= 57 (c/levenshtein-score "kitten" "sitting"))))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `lein test sankofa-fu.classic-test`
Expected: FAIL (namespace not found).

- [ ] **Step 3: Write `src/sankofa_fu/classic.clj`**

```clojure
(ns sankofa-fu.classic
  "Classic clustering methods: fingerprint key collision and
  Levenshtein-style nearest neighbour (spec §2)."
  (:require [clojure.string :as str]
            [sankofa-fu.metrics :as metrics]))

(defn fingerprint
  "OpenRefine-style fingerprint key: trim, lowercase, split on
  non-letter/digit, dedupe, sort, join with single spaces."
  [s]
  (->> (str/split (str/lower-case (str/trim (str s))) #"[^\p{L}\p{N}]+")
       (remove str/blank?)
       distinct
       sort
       (str/join " ")))

(defn levenshtein-score
  "Normalised OSA Damerau-Levenshtein similarity as 0-100 score,
  case-insensitive."
  [a b]
  (int (Math/round (* 100 (metrics/damerau (str/lower-case a)
                                           (str/lower-case b))))))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `lein test sankofa-fu.classic-test`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/sankofa_fu/classic.clj test/sankofa_fu/classic_test.clj
git commit -m "feat: classic methods — fingerprint key collision, levenshtein"
```

---

### Task 8: engine.clj — facade + interop entry point

**Files:**
- Create: `src/sankofa_fu/engine.clj`
- Test: `test/sankofa_fu/engine_test.clj`

Facade tying it together (Python engine.py, spec §2–3): builds spine index, matches each distinct query value, emits cluster JSON shape. `compute-clusters-java` is the interop entry point called from Java — accepts `java.util.List`/`java.util.Map` inputs (Clojure `get`/`count`/seq work on them directly) and returns nested string-keyed Clojure maps/vectors, which Jackson serialises as Maps/Lists. `->cfg` converts the string-keyed knobs map from the dialog into the keyword cfg map used by all namespaces, applying defaults.

- [ ] **Step 1: Write the failing test**

```clojure
(ns sankofa-fu.engine-test
  (:require [clojure.test :refer [deftest is]]
            [sankofa-fu.engine :as e]))

(def spine
  [{"id" "r1" "code" "RM c.801.k.5"}
   {"id" "r2" "code" "RM c.801.k.15"}
   {"id" "r7" "code" "Egerton 3025"}])

(deftest cfg-defaults
  (let [cfg (e/->cfg {})]
    (is (= "archival" (:scheme cfg)))
    (is (= "veto" (:numeric-gate cfg)))
    (is (= 30 (:min-score cfg)))
    (is (true? (:ocr-confusables cfg)))))

(deftest cfg-overrides
  (let [cfg (e/->cfg {"scheme" "raw" "minScore" 50 "ocrConfusables" false})]
    (is (= "raw" (:scheme cfg)))
    (is (= 50 (:min-score cfg)))
    (is (false? (:ocr-confusables cfg)))))

(deftest exact-match-auto-ticked
  (let [r (e/compute-clusters-java spine [{"value" "rm C/801/K/5" "count" 3}]
                                   "sankofa" {})
        cl (first (get r "clusters"))
        cand (first (get cl "candidates"))]
    (is (= "rm C/801/K/5" (get cl "queryValue")))
    (is (= 3 (get cl "count")))
    (is (= "r1" (get cand "spineId")))
    (is (= 100 (get cand "score")))
    (is (true? (get cand "exact")))))

(deftest typo-ranked-first-not-exact
  (let [r (e/compute-clusters-java spine [{"value" "Egetron 3025" "count" 1}]
                                   "sankofa" {})
        cand (first (get (first (get r "clusters")) "candidates"))]
    (is (= "r7" (get cand "spineId")))
    (is (false? (get cand "exact")))
    (is (< 85 (get cand "score") 100))))

(deftest ambiguous-exact-proposed-unticked
  (let [spine2 (conj spine {"id" "dup" "code" "RM C 801 K 5"})
        r (e/compute-clusters-java spine2 [{"value" "RM c.801.k.5" "count" 1}]
                                   "sankofa" {})
        cands (get (first (get r "clusters")) "candidates")]
    (is (= 2 (count cands)))
    (is (every? #(false? (get % "exact")) cands))
    (is (every? #(= 100 (get % "score")) cands))))

(deftest blank-value-no-candidates
  (let [r (e/compute-clusters-java spine [{"value" "   " "count" 1}] "sankofa" {})]
    (is (empty? (get (first (get r "clusters")) "candidates")))))

(deftest fingerprint-method
  (let [r (e/compute-clusters-java [{"id" "a" "code" "Tom Cruise"}]
                                   [{"value" "cruise, TOM" "count" 1}]
                                   "fingerprint" {})
        cand (first (get (first (get r "clusters")) "candidates"))]
    (is (= "a" (get cand "spineId")))
    (is (true? (get cand "exact")))))

(deftest levenshtein-method
  (let [r (e/compute-clusters-java [{"id" "a" "code" "kitten"}]
                                   [{"value" "sitten" "count" 1}]
                                   "levenshtein" {})
        cand (first (get (first (get r "clusters")) "candidates"))]
    (is (= "a" (get cand "spineId")))
    (is (= 83 (get cand "score")))))    ; 1 - 1/6 → 83

(deftest stats
  (let [r (e/compute-clusters-java spine
                                   [{"value" "rm C/801/K/5" "count" 1}
                                    {"value" "ZZZ 999" "count" 1}]
                                   "sankofa" {})]
    (is (= {"nDistinct" 2 "nMatched" 1 "nExact" 1} (get r "stats")))))

(deftest java-collections-accepted
  (let [spine-j (java.util.ArrayList.
                  [(java.util.HashMap. {"id" "r1" "code" "RM c.801.k.5"})])
        queries-j (java.util.ArrayList.
                    [(java.util.HashMap. {"value" "RM c.801.k.5" "count" 1})])
        knobs-j (java.util.HashMap. {"minScore" 30})
        r (e/compute-clusters-java spine-j queries-j "sankofa" knobs-j)]
    (is (= "r1" (get (first (get (first (get r "clusters")) "candidates"))
                     "spineId")))))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `lein test sankofa-fu.engine-test`
Expected: FAIL (namespace not found).

- [ ] **Step 3: Write `src/sankofa_fu/engine.clj`**

```clojure
(ns sankofa-fu.engine
  "Facade: spine records + query values + method/knobs → cluster JSON shape
  (spec §2-3). compute-clusters-java is the Java interop entry point.
  Spine adapter boundary for the deferred recon-API path: anything that
  yields {\"id\" \"code\"} maps can be a spine."
  (:require [clojure.string :as str]
            [sankofa-fu.blocking :as blocking]
            [sankofa-fu.classic :as classic]
            [sankofa-fu.normalise :as norm]
            [sankofa-fu.schemes :as schemes]
            [sankofa-fu.scoring :as scoring]))

(def ^:private blocking-cap 200)

(defn ->cfg
  "String-keyed knobs map (from dialog JSON / Java) → keyword cfg map with
  defaults. Tolerates java.util.Map input."
  [m]
  (let [g (fn [k d] (let [v (get m k)] (if (nil? v) d v)))]
    {:scheme          (g "scheme" "archival")
     :delimiters      (vec (g "delimiters" ["." "/" "-" " "]))
     :abbreviations   (into {} (g "abbreviations" {}))
     :padding         (g "padding" "strip")
     :numeric-gate    (g "numericGate" "veto")
     :weights         (into {} (g "weights" {"prefix" 2.0 "alpha" 1.0}))
     :ocr-confusables (boolean (g "ocrConfusables" true))
     :min-score       (long (g "minScore" 30))
     :max-candidates  (long (g "maxCandidates" 5))}))

(defn- canonicaliser [method cfg]
  (case method
    "sankofa"
    (let [scheme (get schemes/schemes (:scheme cfg))]
      (if-let [c (:canonicalise scheme)]
      ;; isbn/issn: invalid check digit → nil canonical → no candidates
        (fn [raw] (try (c raw) (catch Exception _ nil)))
        (fn [raw] (norm/normalise raw cfg))))
    "fingerprint" classic/fingerprint
    "levenshtein" (fn [raw] (str/lower-case (str/trim raw)))))

(defn- scorer [method cfg]
  (case method
    "sankofa"
    (fn [q c] (scoring/score-canonical q c (:scheme cfg) cfg))
    "fingerprint"
    (fn [q c] {:score (if (= q c) 100 0)
               :evidence [{"query" q "candidate" c "detail" "fingerprint key"}]})
    "levenshtein"
    (fn [q c] {:score (classic/levenshtein-score q c)
               :evidence [{"query" q "candidate" c "detail" "levenshtein"}]})))

(defn- evidence->str [e]
  (str (get e "query") "→" (get e "candidate") ": " (get e "detail")
       (when-let [s (get e "similarity")] (str " (" s ")"))))

(defn- candidate-json [r score evidence exact]
  {"spineId" (get r "id") "spineCode" (get r "code")
   "score" score "evidence" evidence "exact" exact})

(defn- match-one [index canonical method cfg score-fn]
  (let [ex (blocking/exact index canonical)]
    (cond
      (= 1 (count ex))
      [(candidate-json (first ex) 100 ["exact canonical"] true)]

      (seq ex)                        ; ambiguous exact: propose all, no auto
      (mapv #(candidate-json % 100 ["exact canonical (ambiguous)"] false) ex)

      :else
      (let [cands (blocking/candidates index canonical blocking-cap)
            cands (if (and (= method "sankofa") (:ocr-confusables cfg))
                    (let [alt (scoring/translate-confusables canonical)]
                      (if (= alt canonical)
                        cands
                        (into cands
                              (concat (blocking/candidates index alt blocking-cap)
                                      (blocking/exact index alt)))))
                    cands)
            uniq (vals (into {} (map (juxt #(get % "id") identity)) cands))]
        (->> uniq
             (keep (fn [r]
                     (let [{:keys [score evidence]}
                           (score-fn canonical (get r "canonical"))]
                       (when (>= score (:min-score cfg))
                         (candidate-json r score
                                         (mapv evidence->str evidence) false)))))
             (sort-by #(- (get % "score")))
             (take (:max-candidates cfg))
             vec)))))

(defn compute-clusters [spine queries method cfg]
  (let [canon (canonicaliser method cfg)
        score-fn (scorer method cfg)
        spine* (into []
                     (keep (fn [r]
                             (let [c (try (canon (str (get r "code")))
                                          (catch Exception _ nil))]
                               (when-not (or (nil? c) (str/blank? c))
                                 {"id" (str (get r "id"))
                                  "code" (str (get r "code"))
                                  "canonical" c}))))
                     spine)
        index (blocking/build-index spine*)
        clusters
        (mapv (fn [q]
                (let [value (str (get q "value"))
                      n (get q "count")]
                  (try
                    (let [canonical (canon value)]
                      {"queryValue" value "count" n
                       "candidates" (if (or (nil? canonical)
                                            (str/blank? canonical))
                                      []
                                      (match-one index canonical method cfg
                                                 score-fn))})
                    (catch Exception ex
                      ;; per-value failure flagged, never silently dropped
                      {"queryValue" value "count" n "candidates" []
                       "error" (str (.getMessage ex))}))))
              queries)]
    {"clusters" clusters
     "stats" {"nDistinct" (count clusters)
              "nMatched" (count (filter #(seq (get % "candidates")) clusters))
              "nExact" (count (filter (fn [cl]
                                        (some #(get % "exact")
                                              (get cl "candidates")))
                                      clusters))}}))

(defn compute-clusters-java
  "Interop entry point for the Java command. spine: List of Maps
  {id, code}; queries: List of Maps {value, count}; method: string;
  knobs: string-keyed Map. Returns Jackson-serialisable nested structures."
  [spine queries method knobs]
  (compute-clusters spine queries method (->cfg knobs)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `lein test sankofa-fu.engine-test`
Expected: PASS (10 tests).

- [ ] **Step 5: Run the full suite**

Run: `lein test`
Expected: PASS, 0 failures across all namespaces.

- [ ] **Step 6: Commit**

```bash
git add src/sankofa_fu/engine.clj test/sankofa_fu/engine_test.clj
git commit -m "feat: engine facade — cluster computation + Java interop entry point"
```

---

### Task 9: Fixture parity with the Python engine

**Files:**
- Test: `test/sankofa_fu/quality_test.clj`
- Uses: `test/fixtures/catalogue.csv`, `test/fixtures/labelled_pairs.csv` (copied in Task 1)

The mechanism-tagged harness: same labelled pairs the Python engine passes. `rank1` = expected id must be the top candidate; `absent` = expected id must not appear at all (false-positive guard for distinct items). CSV parsing is a two-line split — the fixtures contain no quoted commas.

- [ ] **Step 1: Write the test (it should pass immediately if Tasks 2–8 are correct — this is a verification gate, not TDD)**

```clojure
(ns sankofa-fu.quality-test
  "Mechanism-tagged parity harness. Fixtures shared with the Python repo
  (tests/fixtures/). Mechanisms: formatting, typo, ocr-artifact,
  distinct-item."
  (:require [clojure.string :as str]
            [clojure.test :refer [deftest is testing]]
            [sankofa-fu.engine :as engine]))

(defn- parse-csv
  "Naive CSV: fixtures contain no quoted commas."
  [path]
  (let [[header & rows] (str/split-lines (slurp path))
        cols (str/split header #",")]
    (mapv #(zipmap cols (str/split % #"," -1)) rows)))

(def spine
  (into []
        (keep (fn [r]
                (when-not (str/blank? (get r "shelfmark"))
                  {"id" (get r "record_id") "code" (get r "shelfmark")})))
        (parse-csv "test/fixtures/catalogue.csv")))

(def knobs {"abbreviations" {"ms" "MS"}})

(deftest labelled-pairs
  (doseq [{:strs [dirty expected_id mechanism expect_match]}
          (parse-csv "test/fixtures/labelled_pairs.csv")]
    (let [result (engine/compute-clusters-java
                   spine [{"value" dirty "count" 1}] "sankofa" knobs)
          cands (get (first (get result "clusters")) "candidates")]
      (testing (str mechanism ": " dirty " → " expected_id " (" expect_match ")")
        (case expect_match
          "rank1"  (is (= expected_id (get (first cands) "spineId")))
          "absent" (is (not-any? #(= expected_id (get % "spineId")) cands)))))))
```

- [ ] **Step 2: Run it**

Run: `lein test sankofa-fu.quality-test`
Expected: PASS — 1 test, 10 assertions (one per labelled pair).

If any pair fails, debug against the Python engine's behaviour (`/Users/marty/Devel/sankofa-fú`, run `pytest tests/test_quality.py` there to confirm the canonical result), then fix the Clojure port — the fixtures are the contract, do not edit them.

- [ ] **Step 3: Commit**

```bash
git add test/sankofa_fu/quality_test.clj
git commit -m "test: mechanism-tagged parity harness against shared fixtures"
```

---

### Task 10: ComputeMatchesCommand (Java) + module wiring

**Files:**
- Create: `src/java/com/sankofafu/ComputeMatchesCommand.java`
- Modify: `extension/module/MOD-INF/controller.js`

No unit-test harness for OpenRefine commands (matches loupe's practice) — this task ends with a curl smoke test against a running OpenRefine.

**Classloader note (why the static block below exists):** OpenRefine bundles Clojure (it powers the `clojure:` expression language), so Clojure's runtime classes live in the core classloader and its namespace registry is shared. But `require` resolves namespaces via the *thread context* classloader, which during requests is the core one and cannot see this extension's jar. Fix: force-load the AOT `__init` class through the *module* classloader (which Butterfly builds from `MOD-INF/lib/*.jar`) with the context classloader temporarily swapped so the ns-form's internal `require`s of sibling namespaces also resolve.

- [ ] **Step 1: Write `src/java/com/sankofafu/ComputeMatchesCommand.java`**

```java
package com.sankofafu;

import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import com.google.refine.ProjectManager;
import com.google.refine.browsing.Engine;
import com.google.refine.browsing.FilteredRows;
import com.google.refine.browsing.RowVisitor;
import com.google.refine.commands.Command;
import com.google.refine.model.Column;
import com.google.refine.model.Project;
import com.google.refine.model.Row;
import com.google.refine.util.ParsingUtilities;

import clojure.java.api.Clojure;
import clojure.lang.IFn;

public class ComputeMatchesCommand extends Command {

    static {
        // Force-load the AOT'd engine through the module classloader; see
        // classloader note in the implementation plan.
        ClassLoader moduleCL = ComputeMatchesCommand.class.getClassLoader();
        Thread t = Thread.currentThread();
        ClassLoader old = t.getContextClassLoader();
        try {
            t.setContextClassLoader(moduleCL);
            Class.forName("sankofa_fu.engine__init", true, moduleCL);
        } catch (ClassNotFoundException e) {
            throw new RuntimeException("sankofa-fu: engine namespace not loadable", e);
        } finally {
            t.setContextClassLoader(old);
        }
    }

    @Override
    public void doPost(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {
        try {
            Project project = getProject(request);
            Engine engine = getEngine(request, project);
            String columnName = request.getParameter("column");
            Column qCol = project.columnModel.getColumnByName(columnName);
            if (qCol == null) {
                badRequest(response, "Column not found: " + columnName);
                return;
            }

            long spineProjectId = Long.parseLong(request.getParameter("spineProject"));
            Project spineProject = ProjectManager.singleton.getProject(spineProjectId);
            if (spineProject == null) {
                badRequest(response, "Spine project not found (deleted?)");
                return;
            }
            String spineColumn = request.getParameter("spineColumn");
            Column sCol = spineProject.columnModel.getColumnByName(spineColumn);
            if (sCol == null) {
                badRequest(response, "Spine column not found: " + spineColumn);
                return;
            }
            String spineIdColumn = request.getParameter("spineIdColumn");
            int idIdx = -1;
            if (spineIdColumn != null && !spineIdColumn.isEmpty()) {
                Column idCol = spineProject.columnModel.getColumnByName(spineIdColumn);
                if (idCol == null) {
                    badRequest(response, "Spine ID column not found: " + spineIdColumn);
                    return;
                }
                idIdx = idCol.getCellIndex();
            }

            String method = request.getParameter("method");
            String paramsJson = request.getParameter("params");
            @SuppressWarnings("unchecked")
            Map<String, Object> knobs = paramsJson == null || paramsJson.isEmpty()
                    ? new HashMap<>()
                    : ParsingUtilities.mapper.readValue(paramsJson, Map.class);
            String limitStr = request.getParameter("limit");
            int limit = (limitStr == null || limitStr.isEmpty())
                    ? -1 : Integer.parseInt(limitStr);

            // spine records: {"id", "code"}; id defaults to row number
            int sIdx = sCol.getCellIndex();
            List<Map<String, Object>> spine = new ArrayList<>();
            for (int r = 0; r < spineProject.rows.size(); r++) {
                Row row = spineProject.rows.get(r);
                Object v = row.getCellValue(sIdx);
                if (v == null || v.toString().isEmpty()) continue;
                Map<String, Object> rec = new HashMap<>();
                rec.put("code", v.toString());
                Object id = idIdx >= 0 ? row.getCellValue(idIdx) : null;
                rec.put("id", id == null ? String.valueOf(r) : id.toString());
                spine.add(rec);
            }

            // distinct query values (respecting facets), insertion-ordered
            final int qIdx = qCol.getCellIndex();
            final LinkedHashMap<String, Integer> distinct = new LinkedHashMap<>();
            FilteredRows fr = engine.getAllFilteredRows();
            fr.accept(project, new RowVisitor() {
                @Override public void start(Project p) {}
                @Override public boolean visit(Project p, int rowIndex, Row row) {
                    Object v = row.getCellValue(qIdx);
                    if (v != null) {
                        String s = v.toString();
                        if (!s.isEmpty()) distinct.merge(s, 1, Integer::sum);
                    }
                    return false;
                }
                @Override public void end(Project p) {}
            });

            List<Map<String, Object>> queries = new ArrayList<>();
            for (Map.Entry<String, Integer> e : distinct.entrySet()) {
                if (limit >= 0 && queries.size() >= limit) break;
                Map<String, Object> q = new HashMap<>();
                q.put("value", e.getKey());
                q.put("count", e.getValue());
                queries.add(q);
            }

            IFn compute = Clojure.var("sankofa-fu.engine", "compute-clusters-java");
            Object result = compute.invoke(spine, queries, method, knobs);
            respondJSON(response, result);
        } catch (Exception e) {
            respondException(response, e);
        }
    }

    private static void badRequest(HttpServletResponse response, String msg)
            throws IOException {
        response.setStatus(400);
        Map<String, String> err = new HashMap<>();
        err.put("code", "error");
        err.put("message", msg);
        respondJSON(response, err);
    }
}
```

**Verification point 3-adjacent:** if `respondJSON` / `respondException` / `getEngine` signatures differ in 3.10, check `main/src/com/google/refine/commands/Command.java` in the OpenRefine source and adapt — they are `protected static` helpers on `Command` in all 3.x releases.

- [ ] **Step 2: Compile**

Run: `lein javac && lein jar`
Expected: compiles clean; `target/sankofa-fu.jar` contains `com/sankofafu/ComputeMatchesCommand.class` and `sankofa_fu/engine__init.class` (check with `unzip -l target/sankofa-fu.jar | grep -E 'Command|engine__init'`).

- [ ] **Step 3: Register the command in `extension/module/MOD-INF/controller.js`** (replace file contents)

```javascript
var RefineServlet = Packages.com.google.refine.RefineServlet;

function init() {
  RefineServlet.registerCommand(
    module, "compute-matches",
    new Packages.com.sankofafu.ComputeMatchesCommand());
  // apply-matches command + operation registered in Task 11;
  // client assets registered in Task 12.
}
```

- [ ] **Step 4: Smoke test against a running OpenRefine**

```bash
make install
# start OpenRefine 3.10 (e.g. open the app, or ./refine from a source checkout)
```

In the OpenRefine UI: create project "spine-test" from `test/fixtures/catalogue.csv`, and project "dirty-test" from `test/fixtures/dirty.csv`. Note both project IDs from their URLs (`project?project=<ID>`).

```bash
curl -s "http://127.0.0.1:3333/command/sankofa-fu/compute-matches" \
  --data-urlencode "project=<DIRTY_ID>" \
  --data-urlencode "column=shelfmark" \
  --data-urlencode "spineProject=<SPINE_ID>" \
  --data-urlencode "spineColumn=shelfmark" \
  --data-urlencode "spineIdColumn=record_id" \
  --data-urlencode "method=sankofa" \
  --data-urlencode 'params={"abbreviations":{"ms":"MS"}}' \
  --data-urlencode 'engine={"facets":[],"mode":"row-based"}' | python3 -m json.tool
```

Expected: JSON with `clusters` (10 entries; `rm C/801/K/5` has candidate `r1` score 100 exact true) and `stats`. Also verify the 400 path: repeat with `spineColumn=nope` → `{"code":"error","message":"Spine column not found: nope"}`.

- [ ] **Step 5: Commit**

```bash
git add src/java/com/sankofafu/ComputeMatchesCommand.java extension/module/MOD-INF/controller.js
git commit -m "feat: compute-matches command bridging OpenRefine to the Clojure engine"
```

---

### Task 11: ApplyMatchesOperation + apply-matches command

**Files:**
- Create: `src/java/com/sankofafu/ApplyMatchesOperation.java`
- Create: `src/java/com/sankofafu/ApplyMatchesCommand.java`
- Modify: `extension/module/MOD-INF/controller.js`

One undoable history entry writing the user-selected outputs. Manual verification (no harness).

- [ ] **Step 1: Write `src/java/com/sankofafu/ApplyMatchesOperation.java`**

```java
package com.sankofafu;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

import com.google.refine.browsing.Engine;
import com.google.refine.browsing.EngineConfig;
import com.google.refine.browsing.FilteredRows;
import com.google.refine.browsing.RowVisitor;
import com.google.refine.history.Change;
import com.google.refine.history.HistoryEntry;
import com.google.refine.model.Cell;
import com.google.refine.model.Column;
import com.google.refine.model.Project;
import com.google.refine.model.Row;
import com.google.refine.model.changes.CellAtRow;
import com.google.refine.model.changes.CellChange;
import com.google.refine.model.changes.ColumnAdditionChange;
import com.google.refine.model.changes.MassCellChange;
import com.google.refine.model.changes.MassChange;
import com.google.refine.operations.EngineDependentOperation;

public class ApplyMatchesOperation extends EngineDependentOperation {

    final protected String _columnName;
    // queryValue -> {spineId, spineCode, score}
    final protected Map<String, Map<String, Object>> _matches;
    final protected String _idColumn;      // null = don't write
    final protected String _codeColumn;
    final protected String _scoreColumn;
    final protected boolean _replaceInPlace;

    @JsonCreator
    public ApplyMatchesOperation(
            @JsonProperty("engineConfig") EngineConfig engineConfig,
            @JsonProperty("columnName") String columnName,
            @JsonProperty("matches") Map<String, Map<String, Object>> matches,
            @JsonProperty("idColumn") String idColumn,
            @JsonProperty("codeColumn") String codeColumn,
            @JsonProperty("scoreColumn") String scoreColumn,
            @JsonProperty("replaceInPlace") boolean replaceInPlace) {
        super(engineConfig);
        _columnName = columnName;
        _matches = matches;
        _idColumn = emptyToNull(idColumn);
        _codeColumn = emptyToNull(codeColumn);
        _scoreColumn = emptyToNull(scoreColumn);
        _replaceInPlace = replaceInPlace;
    }

    private static String emptyToNull(String s) {
        return (s == null || s.isEmpty()) ? null : s;
    }

    @JsonProperty("columnName")
    public String getColumnName() { return _columnName; }
    @JsonProperty("matches")
    public Map<String, Map<String, Object>> getMatches() { return _matches; }
    @JsonProperty("idColumn")
    public String getIdColumn() { return _idColumn; }
    @JsonProperty("codeColumn")
    public String getCodeColumn() { return _codeColumn; }
    @JsonProperty("scoreColumn")
    public String getScoreColumn() { return _scoreColumn; }
    @JsonProperty("replaceInPlace")
    public boolean getReplaceInPlace() { return _replaceInPlace; }

    @Override
    protected String getBriefDescription(Project project) {
        return "Match " + _matches.size() + " values in column " + _columnName
                + " against spine";
    }

    @Override
    protected HistoryEntry createHistoryEntry(Project project, long historyEntryID)
            throws Exception {
        Engine engine = createEngine(project);
        Column column = project.columnModel.getColumnByName(_columnName);
        if (column == null) {
            throw new Exception("No column named " + _columnName);
        }
        final int cellIndex = column.getCellIndex();

        final List<CellChange> cellChanges = new ArrayList<>();
        final List<CellAtRow> idCells = new ArrayList<>();
        final List<CellAtRow> codeCells = new ArrayList<>();
        final List<CellAtRow> scoreCells = new ArrayList<>();

        FilteredRows fr = engine.getAllFilteredRows();
        fr.accept(project, new RowVisitor() {
            @Override public void start(Project p) {}
            @Override public boolean visit(Project p, int rowIndex, Row row) {
                Object v = row.getCellValue(cellIndex);
                if (v == null) return false;
                Map<String, Object> m = _matches.get(v.toString());
                if (m == null) return false;
                if (_replaceInPlace) {
                    cellChanges.add(new CellChange(rowIndex, cellIndex,
                            row.getCell(cellIndex),
                            new Cell((String) m.get("spineCode"), null)));
                }
                if (_idColumn != null) {
                    idCells.add(new CellAtRow(rowIndex,
                            new Cell((String) m.get("spineId"), null)));
                }
                if (_codeColumn != null) {
                    codeCells.add(new CellAtRow(rowIndex,
                            new Cell((String) m.get("spineCode"), null)));
                }
                if (_scoreColumn != null) {
                    scoreCells.add(new CellAtRow(rowIndex,
                            new Cell(((Number) m.get("score")).intValue(), null)));
                }
                return false;
            }
            @Override public void end(Project p) {}
        });

        List<Change> changes = new ArrayList<>();
        int insertAt = project.columnModel.columns.size();
        if (_idColumn != null) {
            changes.add(new ColumnAdditionChange(_idColumn, insertAt++, idCells));
        }
        if (_codeColumn != null) {
            changes.add(new ColumnAdditionChange(_codeColumn, insertAt++, codeCells));
        }
        if (_scoreColumn != null) {
            changes.add(new ColumnAdditionChange(_scoreColumn, insertAt++, scoreCells));
        }
        if (_replaceInPlace) {
            changes.add(new MassCellChange(
                    cellChanges.toArray(new CellChange[0]), _columnName, false));
        }

        return new HistoryEntry(historyEntryID, project,
                getBriefDescription(project), this, new MassChange(changes, false));
    }
}
```

**Verification point 2:** confirm `com.google.refine.model.changes.MassChange` exists in 3.10 with constructor `(List<? extends Change>, boolean)`. If it does not, add this fallback class to the extension and use it instead of `MassChange` (persistence format mirrors core's composite changes):

```java
package com.sankofafu;

import java.io.IOException;
import java.io.LineNumberReader;
import java.io.Writer;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;

import com.google.refine.history.Change;
import com.google.refine.model.Project;
import com.google.refine.util.Pool;

public class CompositeChange implements Change {
    final protected List<Change> _changes;

    public CompositeChange(List<Change> changes) { _changes = changes; }

    @Override
    public void apply(Project project) {
        for (Change c : _changes) c.apply(project);
    }

    @Override
    public void revert(Project project) {
        for (int i = _changes.size() - 1; i >= 0; i--) _changes.get(i).revert(project);
    }

    @Override
    public void save(Writer writer, Properties options) throws IOException {
        writer.write("count=" + _changes.size() + '\n');
        for (Change c : _changes) {
            writer.write(c.getClass().getName() + '\n');
            c.save(writer, options);
        }
        writer.write("/ec/\n");
    }

    static public Change load(LineNumberReader reader, Pool pool) throws Exception {
        String line = reader.readLine();
        int count = Integer.parseInt(line.substring("count=".length()));
        List<Change> changes = new ArrayList<>(count);
        for (int i = 0; i < count; i++) {
            String className = reader.readLine();
            Class<?> klass = Class.forName(className, true,
                    CompositeChange.class.getClassLoader());
            java.lang.reflect.Method load =
                    klass.getMethod("load", LineNumberReader.class, Pool.class);
            changes.add((Change) load.invoke(null, reader, pool));
        }
        reader.readLine(); // /ec/
        return new CompositeChange(changes);
    }
}
```

- [ ] **Step 2: Write `src/java/com/sankofafu/ApplyMatchesCommand.java`**

```java
package com.sankofafu;

import java.util.Map;

import javax.servlet.http.HttpServletRequest;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;

import com.google.refine.browsing.EngineConfig;
import com.google.refine.commands.EngineDependentCommand;
import com.google.refine.model.AbstractOperation;
import com.google.refine.model.Project;
import com.google.refine.util.ParsingUtilities;

public class ApplyMatchesCommand extends EngineDependentCommand {

    @Override
    protected AbstractOperation createOperation(Project project,
            HttpServletRequest request, JsonNode engineConfig) throws Exception {
        Map<String, Map<String, Object>> matches = ParsingUtilities.mapper.readValue(
                request.getParameter("matches"),
                new TypeReference<Map<String, Map<String, Object>>>() {});
        return new ApplyMatchesOperation(
                EngineConfig.reconstruct(engineConfig),
                request.getParameter("column"),
                matches,
                request.getParameter("idColumn"),
                request.getParameter("codeColumn"),
                request.getParameter("scoreColumn"),
                "true".equals(request.getParameter("replaceInPlace")));
    }
}
```

**Verification point 3:** check `EngineDependentCommand.createOperation`'s exact signature in 3.10 (`JsonNode` vs `JSONObject` engine config, and `EngineConfig.reconstruct` argument type) and adapt. `EngineDependentCommand.doPost` handles CSRF validation and process submission — do not add either here.

- [ ] **Step 3: Compile**

Run: `lein javac && lein jar`
Expected: clean compile.

- [ ] **Step 4: Register command + operation in `controller.js`** (replace `init` body)

```javascript
var RefineServlet = Packages.com.google.refine.RefineServlet;
var OperationRegistry = Packages.com.google.refine.operations.OperationRegistry;

function init() {
  RefineServlet.registerCommand(
    module, "compute-matches",
    new Packages.com.sankofafu.ComputeMatchesCommand());
  RefineServlet.registerCommand(
    module, "apply-matches",
    new Packages.com.sankofafu.ApplyMatchesCommand());
  OperationRegistry.registerOperation(
    module, "apply-matches",
    Packages.com.sankofafu.ApplyMatchesOperation);
  // client assets registered in Task 12.
}
```

- [ ] **Step 5: Manual verification**

```bash
make install   # restart OpenRefine
```

Get a CSRF token, then apply two matches against the dirty-test project:

```bash
TOKEN=$(curl -s "http://127.0.0.1:3333/command/core/get-csrf-token" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s "http://127.0.0.1:3333/command/sankofa-fu/apply-matches?csrf_token=$TOKEN" \
  --data-urlencode "project=<DIRTY_ID>" \
  --data-urlencode "column=shelfmark" \
  --data-urlencode 'matches={"rm C/801/K/5":{"spineId":"r1","spineCode":"RM c.801.k.5","score":100},"Egetron 3025":{"spineId":"r7","spineCode":"Egerton 3025","score":96}}' \
  --data-urlencode "idColumn=shelfmark spine id" \
  --data-urlencode "codeColumn=shelfmark spine code" \
  --data-urlencode "scoreColumn=shelfmark match score" \
  --data-urlencode "replaceInPlace=true" \
  --data-urlencode 'engine={"facets":[],"mode":"row-based"}'
```

Expected: `{"code":"ok"}` (or a process pending response). In the UI verify:
1. Three new columns exist with values only on the two matched rows.
2. The two matched cells were replaced in place.
3. Undo/Redo shows ONE entry: "Match 2 values in column shelfmark against spine".
4. Clicking undo restores everything (columns gone, cells restored).

- [ ] **Step 6: Commit**

```bash
git add src/java/com/sankofafu/ApplyMatchesOperation.java src/java/com/sankofafu/ApplyMatchesCommand.java extension/module/MOD-INF/controller.js
git commit -m "feat: undoable apply-matches operation writing selected outputs"
```

---

### Task 12: Frontend — column menu + match dialog

**Files:**
- Create: `extension/module/scripts/menu.js`
- Create: `extension/module/scripts/match-dialog.html`
- Create: `extension/module/scripts/match-dialog.js`
- Create: `extension/module/styles/match-dialog.css`
- Modify: `extension/module/MOD-INF/controller.js`

Dialog modeled on Cluster & Edit (spec §4): pickers, method knobs, debounced 20-value preview, full cluster table, output checkboxes, one-click apply. No build step — plain files served by Butterfly.

- [ ] **Step 1: Write `extension/module/scripts/menu.js`**

```javascript
DataTableColumnHeaderUI.extendMenu(function (column, columnHeaderUI, menu) {
  menu.push({});   // separator
  menu.push({
    id: "sankofa-fu/match-spine",
    label: "Match against spine…",
    click: function () { new SankofaMatchDialog(column); }
  });
});
```

- [ ] **Step 2: Write `extension/module/scripts/match-dialog.html`**

```html
<div class="dialog-frame sankofa-match-dialog">
  <div class="dialog-header">Match against spine: <span bind="columnName"></span></div>
  <div class="dialog-body">
    <div class="sankofa-controls">
      <label>Spine project:
        <select bind="spineProjectSelect"></select>
      </label>
      <label>Spine column:
        <select bind="spineColumnSelect"></select>
      </label>
      <label>Spine ID column:
        <select bind="spineIdColumnSelect"></select>
      </label>
      <label>Method:
        <select bind="methodSelect" class="sankofa-knob">
          <option value="sankofa" selected>Sankofa (component-aware)</option>
          <option value="fingerprint">Fingerprint key collision</option>
          <option value="levenshtein">Levenshtein nearest neighbour</option>
        </select>
      </label>
      <button class="button" bind="computeButton">Compute matches</button>
    </div>

    <div class="sankofa-knobs" bind="sankofaKnobs">
      <label>Scheme:
        <select bind="schemeSelect" class="sankofa-knob">
          <option value="archival" selected>archival</option>
          <option value="isbn">isbn</option>
          <option value="issn">issn</option>
          <option value="raw">raw</option>
        </select>
      </label>
      <label>Numeric gate:
        <select bind="gateSelect" class="sankofa-knob">
          <option value="veto" selected>veto</option>
          <option value="penalty:50">penalty:50</option>
          <option value="penalty:25">penalty:25</option>
        </select>
      </label>
      <label><input type="checkbox" bind="ocrCheck" class="sankofa-knob" checked />
        OCR confusables (O→0, L/I→1)</label>
      <label>Delimiters:
        <input type="text" bind="delimitersInput" class="sankofa-knob" value="./- " size="6" />
      </label>
      <label>Padding:
        <select bind="paddingSelect" class="sankofa-knob">
          <option value="strip" selected>strip zeros</option>
          <option value="pad:5">pad to 5</option>
          <option value="pad:8">pad to 8</option>
        </select>
      </label>
      <label>Min score:
        <input type="number" bind="minScoreInput" class="sankofa-knob" value="30" size="4" />
      </label>
      <label>Max candidates:
        <input type="number" bind="maxCandInput" class="sankofa-knob" value="5" size="3" />
      </label>
      <label>Abbreviations (one per line, e.g. <code>ms=MS</code>):
        <textarea bind="abbreviationsInput" class="sankofa-knob" rows="2" cols="20"></textarea>
      </label>
    </div>

    <div class="sankofa-preview" bind="previewPane"></div>
    <div class="sankofa-status" bind="statusText"></div>

    <div class="sankofa-results-container">
      <table class="sankofa-table">
        <thead>
          <tr><th>Accept</th><th>Rows</th><th>Value</th><th>Candidates (code — id — score)</th></tr>
        </thead>
        <tbody bind="resultsBody"></tbody>
      </table>
    </div>

    <div class="sankofa-footer">
      <label><input type="checkbox" bind="idColCheck" checked />
        ID → <input type="text" bind="idColName" size="20" /></label>
      <label><input type="checkbox" bind="codeColCheck" />
        Code → <input type="text" bind="codeColName" size="20" /></label>
      <label><input type="checkbox" bind="scoreColCheck" />
        Score → <input type="text" bind="scoreColName" size="20" /></label>
      <label><input type="checkbox" bind="replaceCheck" /> Replace cell values in place</label>
      <span class="sankofa-select-above">
        <input type="number" bind="selectAboveInput" value="90" size="4" />
        <button class="button" bind="selectAboveButton">Select all ≥ score</button>
      </span>
      <button class="button button-primary" bind="applyButton">Apply</button>
      <button class="button" bind="closeButton">Close</button>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Write `extension/module/scripts/match-dialog.js`**

```javascript
function SankofaMatchDialog(column) {
  this._column = column;
  this._clusters = null;      // [{data, accepted, chosen}]
  this._previewTimer = null;
  this._createDialog();
}

SankofaMatchDialog.prototype._createDialog = function () {
  var self = this;
  var frame = $(DOM.loadHTML("sankofa-fu", "scripts/match-dialog.html"));
  this._elmts = DOM.bind(frame);
  this._elmts.columnName.text(this._column.name);
  this._elmts.idColName.val(this._column.name + " spine id");
  this._elmts.codeColName.val(this._column.name + " spine code");
  this._elmts.scoreColName.val(this._column.name + " match score");

  $.getJSON("command/core/get-all-project-metadata", function (data) {
    var sel = self._elmts.spineProjectSelect;
    sel.empty().append($("<option>").attr("value", "").text("— select project —"));
    $.each(data.projects, function (id, meta) {
      var label = meta.name + (String(id) === String(theProject.id) ? " (this project)" : "");
      sel.append($("<option>").attr("value", id).text(label));
    });
  });

  this._elmts.spineProjectSelect.change(function () { self._loadSpineColumns(); });
  this._elmts.methodSelect.change(function () { self._toggleKnobs(); });
  frame.find(".sankofa-knob").on("change keyup", function () { self._onKnobChange(); });
  frame.on("change keyup", "select[bind=spineColumnSelect]", function () { self._onKnobChange(); });

  this._elmts.computeButton.click(function () { self._compute(-1); });
  this._elmts.selectAboveButton.click(function () { self._selectAbove(); });
  this._elmts.applyButton.click(function () { self._apply(); });
  this._elmts.closeButton.click(function () { DialogSystem.dismissUntil(self._level - 1); });

  this._level = DialogSystem.showDialog(frame);
  this._toggleKnobs();
};

SankofaMatchDialog.prototype._loadSpineColumns = function () {
  var self = this;
  var id = this._elmts.spineProjectSelect.val();
  if (!id) return;
  $.post("command/core/get-models", { project: id }, function (data) {
    var cols = data.columnModel.columns;
    var colSel = self._elmts.spineColumnSelect.empty();
    var idSel = self._elmts.spineIdColumnSelect.empty()
      .append($("<option>").attr("value", "").text("(row number)"));
    $.each(cols, function (i, c) {
      colSel.append($("<option>").attr("value", c.name).text(c.name));
      idSel.append($("<option>").attr("value", c.name).text(c.name));
    });
    self._onKnobChange();
  }, "json");
};

SankofaMatchDialog.prototype._toggleKnobs = function () {
  this._elmts.sankofaKnobs.toggle(this._elmts.methodSelect.val() === "sankofa");
  this._onKnobChange();
};

SankofaMatchDialog.prototype._knobs = function () {
  var abbrev = {};
  this._elmts.abbreviationsInput.val().split("\n").forEach(function (line) {
    var m = line.split("=");
    if (m.length === 2 && m[0].trim()) abbrev[m[0].trim()] = m[1].trim();
  });
  return {
    scheme: this._elmts.schemeSelect.val(),
    numericGate: this._elmts.gateSelect.val(),
    ocrConfusables: this._elmts.ocrCheck.is(":checked"),
    delimiters: this._elmts.delimitersInput.val().split(""),
    padding: this._elmts.paddingSelect.val(),
    abbreviations: abbrev,
    minScore: parseInt(this._elmts.minScoreInput.val(), 10) || 30,
    maxCandidates: parseInt(this._elmts.maxCandInput.val(), 10) || 5
  };
};

SankofaMatchDialog.prototype._onKnobChange = function () {
  var self = this;
  clearTimeout(this._previewTimer);
  this._previewTimer = setTimeout(function () { self._compute(20); }, 500);
};

SankofaMatchDialog.prototype._compute = function (limit) {
  var self = this;
  var spineProject = this._elmts.spineProjectSelect.val();
  var spineColumn = this._elmts.spineColumnSelect.val();
  if (!spineProject || !spineColumn) return;
  var isPreview = limit > 0;
  this._elmts.statusText.text(isPreview ? "Previewing…" : "Computing…");
  $.post("command/sankofa-fu/compute-matches", {
    project: theProject.id,
    column: this._column.name,
    spineProject: spineProject,
    spineColumn: spineColumn,
    spineIdColumn: this._elmts.spineIdColumnSelect.val() || "",
    method: this._elmts.methodSelect.val(),
    params: JSON.stringify(this._knobs()),
    engine: JSON.stringify(ui.browsingEngine.getJSON()),
    limit: limit
  }, function (data) {
    if (data.code === "error") { self._elmts.statusText.text(data.message); return; }
    if (isPreview) { self._renderPreview(data); } else { self._setClusters(data); }
  }, "json").fail(function (xhr) {
    var msg = "Request failed";
    try { msg = JSON.parse(xhr.responseText).message || msg; } catch (e) {}
    self._elmts.statusText.text(msg);
  });
};

SankofaMatchDialog.prototype._renderPreview = function (data) {
  var s = data.stats;
  var lines = data.clusters.slice(0, 5).map(function (cl) {
    var best = cl.candidates[0];
    return cl.queryValue + " → " +
      (best ? best.spineCode + " (" + best.score + ")" : "no match");
  });
  this._elmts.previewPane.text(
    "Preview (" + s.nDistinct + " sampled): " + s.nMatched + " matched, " +
    s.nExact + " exact. " + lines.join(" · "));
  this._elmts.statusText.text("");
};

SankofaMatchDialog.prototype._setClusters = function (data) {
  this._clusters = data.clusters.map(function (cl) {
    var exactSingle = cl.candidates.length === 1 && cl.candidates[0].exact;
    return { data: cl, accepted: exactSingle,
             chosen: cl.candidates.length ? 0 : -1 };
  });
  var s = data.stats;
  this._elmts.statusText.text(
    s.nDistinct + " distinct values · " + s.nMatched + " with candidates · " +
    s.nExact + " exact");
  this._renderRows();
};

SankofaMatchDialog.prototype._renderRows = function () {
  var tbody = this._elmts.resultsBody.empty();
  (this._clusters || []).forEach(function (state, i) {
    var cl = state.data;
    var tr = $("<tr>");
    var accept = $('<input type="checkbox">')
      .prop("checked", state.accepted)
      .prop("disabled", state.chosen < 0)
      .change(function () { state.accepted = this.checked; });
    tr.append($("<td>").append(accept));
    tr.append($("<td>").text(cl.count));
    tr.append($("<td>").addClass("sankofa-query").text(cl.queryValue));
    var candTd = $("<td>");
    if (cl.error) {
      candTd.append($("<span>").addClass("sankofa-error").text(cl.error));
    }
    cl.candidates.forEach(function (cand, j) {
      var label = $("<label>").addClass("sankofa-candidate")
        .attr("title", (cand.evidence || []).join(" · "));
      var radio = $('<input type="radio">')
        .attr("name", "sankofa-cand-" + i)
        .prop("checked", state.chosen === j)
        .change(function () { state.chosen = j; });
      label.append(radio).append($("<span>").text(
        cand.spineCode + " — " + cand.spineId + " — " + cand.score));
      if (cand.exact) label.addClass("sankofa-exact");
      candTd.append(label);
    });
    tr.append(candTd);
    tbody.append(tr);
  });
};

SankofaMatchDialog.prototype._selectAbove = function () {
  var threshold = parseInt(this._elmts.selectAboveInput.val(), 10) || 100;
  (this._clusters || []).forEach(function (state) {
    if (state.chosen >= 0 &&
        state.data.candidates[state.chosen].score >= threshold) {
      state.accepted = true;
    }
  });
  this._renderRows();
};

SankofaMatchDialog.prototype._apply = function () {
  var self = this;
  var matches = {};
  (this._clusters || []).forEach(function (state) {
    if (state.accepted && state.chosen >= 0) {
      var cand = state.data.candidates[state.chosen];
      matches[state.data.queryValue] = {
        spineId: cand.spineId, spineCode: cand.spineCode, score: cand.score
      };
    }
  });
  if ($.isEmptyObject(matches)) {
    this._elmts.statusText.text("Nothing accepted — tick some matches first.");
    return;
  }
  Refine.postProcess("sankofa-fu", "apply-matches", {}, {
    column: this._column.name,
    matches: JSON.stringify(matches),
    idColumn: this._elmts.idColCheck.is(":checked") ? this._elmts.idColName.val() : "",
    codeColumn: this._elmts.codeColCheck.is(":checked") ? this._elmts.codeColName.val() : "",
    scoreColumn: this._elmts.scoreColCheck.is(":checked") ? this._elmts.scoreColName.val() : "",
    replaceInPlace: this._elmts.replaceCheck.is(":checked"),
    engine: JSON.stringify(ui.browsingEngine.getJSON())
  }, { modelsChanged: true }, {
    onDone: function () { DialogSystem.dismissUntil(self._level - 1); }
  });
};
```

**Verification point:** `Refine.postProcess(moduleName, command, params, body, updateOptions, callbacks)` handles the CSRF token in 3.10 — if the apply request 403s, wrap the call in `Refine.wrapCSRF(function(token){ ... })` and add `csrf_token: token` to the body.

- [ ] **Step 4: Write `extension/module/styles/match-dialog.css`**

```css
.sankofa-match-dialog { width: 900px; }
.sankofa-controls label, .sankofa-knobs label { margin-right: 12px; }
.sankofa-knobs { margin: 8px 0; padding: 6px; background: #f6f6f6; }
.sankofa-preview { margin: 6px 0; font-style: italic; color: #555; }
.sankofa-status { margin: 6px 0; font-weight: bold; }
.sankofa-results-container { max-height: 350px; overflow-y: auto; }
.sankofa-table { width: 100%; border-collapse: collapse; }
.sankofa-table th, .sankofa-table td {
  border-bottom: 1px solid #ddd; padding: 4px 6px; text-align: left;
  vertical-align: top;
}
.sankofa-query { font-family: monospace; }
.sankofa-candidate { display: block; font-family: monospace; }
.sankofa-exact { background: #e6f4e6; }
.sankofa-error { color: #a00; }
.sankofa-footer { margin-top: 8px; }
.sankofa-footer label { margin-right: 10px; }
```

- [ ] **Step 5: Register client assets in `controller.js`** (add to the end of `init()`)

```javascript
  var ClientSideResourceManager = Packages.com.google.refine.ClientSideResourceManager;
  ClientSideResourceManager.addPaths(
    "project/scripts", module,
    ["scripts/match-dialog.js", "scripts/menu.js"]);
  ClientSideResourceManager.addPaths(
    "project/styles", module,
    ["styles/match-dialog.css"]);
```

(`match-dialog.js` before `menu.js`: the menu references `SankofaMatchDialog`.)

- [ ] **Step 6: Manual verification**

`make install`, restart OpenRefine, open dirty-test project:
1. Column menu on `shelfmark` shows "Match against spine…"; dialog opens.
2. Pick spine-test / `shelfmark` / ID column `record_id` — preview appears within ~1s of picking (debounced), shows "10 sampled … exact" stats.
3. Change method to fingerprint — sankofa knobs hide, preview recomputes.
4. Back to sankofa; add abbreviation line `ms=MS`; preview shows `Ms. 12345 → MS 12345 (100)`.
5. Compute matches — full table; `rm C/801/K/5` auto-ticked (green); `Egetron 3025` unticked with r7 at ~96.
6. "Select all ≥ 90" ticks the typo rows.
7. Tick all four outputs, Apply — dialog closes, three columns appear, cells replaced, ONE history entry, undo works.

- [ ] **Step 7: Commit**

```bash
git add extension/module/scripts extension/module/styles extension/module/MOD-INF/controller.js
git commit -m "feat: clustering-style match dialog with preview and configurable outputs"
```

---

### Task 13: E2E checklist, README, distribution zip

**Files:**
- Create: `README.md`

- [ ] **Step 1: Run the full E2E checklist and record results**

1. `lein test` — all green.
2. `make install`, restart OpenRefine.
3. Full dialog flow (Task 12 Step 6) passes.
4. Facet-awareness: add a text facet on the dirty project excluding some rows, reopen dialog, Compute — excluded values absent from table; Apply — only visible rows written.
5. Error path: delete spine-test project, reopen dialog with stale selection, Compute — dialog shows "Spine project not found (deleted?)", no crash.
6. Same-project spine: pick dirty-test as its own spine — works (every value matches itself exact).

- [ ] **Step 2: Write `README.md`**

```markdown
# sankofa-fu-refine

OpenRefine extension that matches a column of reference codes (classmarks,
shelfmarks, ISBNs…) against a "spine" column in another OpenRefine project —
a cross-project Cluster & Edit for structured identifiers.

Port of the [sankofa-fú](../sankofa-fú) matching engine (normalise →
tokenise → block → score, numeric-gate protected) to Clojure, wrapped in a
clustering-style dialog. The Python package remains the canonical engine and
serves the Reconciliation API path via Datasette.

## Install

Requires OpenRefine 3.10.x and Leiningen.

    make install    # builds jar, copies module to the OpenRefine extensions dir

Restart OpenRefine. A "Match against spine…" entry appears in every column
menu.

## Use

1. Open the project with the dirty codes, open the column menu → Match
   against spine…
2. Pick spine project, spine column, optional spine ID column.
3. Pick method (sankofa / fingerprint / levenshtein) and tune knobs — a
   20-value preview updates as you type.
4. Compute matches, review candidates (hover for per-component evidence),
   tick accepts.
5. Choose outputs (ID / code / score columns, in-place replace) and Apply.
   One undoable history step.

## Dev

    lein test     # engine unit tests + fixture parity with the Python engine
    make zip      # distributable dist/sankofa-fu.zip

## Deferred

Reconciliation-service spines (the existing sankofa-fú Datasette plugin) —
the engine's spine boundary is designed for it; see the design spec in the
sankofa-fú repo: docs/superpowers/specs/2026-07-08-sankofa-fu-refine-design.md
```

- [ ] **Step 3: Build the distribution zip**

Run: `make zip`
Expected: `dist/sankofa-fu.zip` containing the module with the jar.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README — install, usage, dev, deferred recon path"
```

---

## Self-review notes (done at plan-writing time)

- **Spec coverage:** §1 layout → Task 1; §2 engine/pipeline/knobs/classic → Tasks 2–8; exact/ambiguous-exact rules → Task 8 tests; fixture parity → Task 9; §3 commands/apply/flow/errors → Tasks 10–11; §4 dialog + preview → Task 12; §5 testing → Tasks 2–9 + manual steps; §6 deferred recon spine → engine docstring notes the spine boundary, nothing built (per spec). Out-of-scope items untouched.
- **Deliberate deviations from spec, both agreed in session or forced by port:** (1) optional spine ID column picker added (row-number fallback) — spine IDs are useless for later joins without it; (2) OSA instead of full Damerau-Levenshtein, and trigram-overlap ranking instead of FTS5 OR-match — marked `ponytail:` in code comments with upgrade paths.
- **Type consistency:** component = `[kind value]` everywhere; cfg keyword map produced only by `engine/->cfg`; records/cluster JSON string-keyed everywhere; knob names (`numericGate`, `ocrConfusables`, `minScore`, `maxCandidates`) identical in dialog JS, `->cfg`, and tests.

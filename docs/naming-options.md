# Naming Options & Cultural Notes
### A discussion document for choosing the tool's name

*Working title: `sankofa-fu` (placeholder). This document collects naming candidates — with origins, meanings, fit, and honest caveats — so the team can choose deliberately. Nothing here is decided.*

---

## What the name needs to fit

The tool builds a searchable index from library/archive catalogues and links messy reference codes (classmarks, shelfmarks, archival/bibliographic identifiers) against it — *reconciling* dirty inputs to canonical records. So the most apt names cluster around three images:

1. **Matching two halves** — a tally; the closest figure for authority-matching (matching a dirty code to its canonical counterpart).
2. **Confluence / joining / linking** — bringing separate records or streams together.
3. **Harmony / accord / reconciliation** — agreement between things.

A fourth, archive-specific image is worth noting: **retrieval from the past** — reaching back into the catalogue to recover the right identity.

## How to judge a candidate

- **Aptness** — does it evoke one of the images above, or is it just exotic?
- **Sayability & string** — short, pronounceable, unambiguous; clean lowercase ASCII handle for PyPI/GitHub.
- **Availability** — free (or qualifiable) on PyPI, GitHub, and the OpenRefine extensions list.
- **Cultural weight** — is the word neutral/everyday, or sacred/legally/politically loaded? The latter isn't disqualifying, but demands care and a genuine connection.

---

## Candidates by region

### East Asia

- **符 — fú** *(Chinese)* — a **tally**, historically a token split into two halves. The bronze tiger tallies (**虎符 hǔfú**) were broken in two so that the matching halves authenticated a military command. Reconciliation *is* matching a half to its counterpart, which makes this the most precise metaphor in the list — and **符合 (fúhé)** literally means "to match / correspond." *Caveat:* `fu` alone is a crowded, homophone-heavy string (and "kung-fu" associations); better as **hefu** or paired (your placeholder `reconciliation-fu` already nods to it).
- **合わせ — awase** *(Japanese)* — "matching / joining." **貝合わせ (kai-awase)** was a Heian-era game of pairing the two halves of the same clam shell — a near-perfect image for finding a record's matching half. *Caveat:* less internationally legible; `awase` reads fine as a handle.
- **結び — musubi** *(Japanese)* — "tying / binding / connection." Excellent for *linking* records; carries a Shinto sense of a generative connecting force. *Caveat:* fashionable lately (featured prominently in the film *Your Name*), so slightly less distinctive.
- **和 — wa** *(Japanese / Chinese)* — "harmony, accord, peace." Semantically clean. *Caveat:* extremely short and heavily used as a morpheme.

### South Asia

- **संधि — sandhi** *(Sanskrit)* — "junction, joining, union," and also "treaty, reconciliation." Its everyday meaning in linguistics is the rule by which adjacent sounds *combine and transform at boundaries* — which resonates strikingly with normalising and joining reference-code components at their delimiters. Deep, multi-layered fit; low cultural-weight (a technical/everyday term). **Top pick.**
- **संगम — sangam / sangama** *(Sanskrit)* — "confluence," the meeting of rivers. A beautiful figure for bringing data streams together, and widely recognised internationally. Clean and easy to say. **Top pick.**
- **समन्वय — samanvaya** *(Sanskrit)* — "reconciliation / synthesis / harmonisation." Almost on-the-nose semantically (used philosophically for reconciling differing viewpoints). *Caveat:* longer, less familiar outside India.
- **सेतु — setu** *(Sanskrit)* — "bridge." Clean if a little generic.

### West & Central Asia / Middle East

- **پیوند — paywand / peyvand** *(Persian)* — "link, bond, joining, graft" (used for everything from a splice to a transplant to a human connection). Clean, pronounceable, and literally about *linking* — a strong, low-weight choice. **Top pick.**
- **وصل — wasl** *(Arabic)* — "connection, joining, union"; also the term for the *joining of letters* in Arabic script (and union in Sufi thought). A graceful parallel to joining components, with lighter baggage than *sulh*.
- **صلح — sulh** *(Arabic)* — "reconciliation, amicable settlement." The most literal match. *Caveat:* carries legal/religious weight in Islamic jurisprudence — use knowingly, with a genuine connection.
- **اتفاق — ittifaq** *(Arabic)* — plainly "agreement, accord, concord." Neutral and apt.
- **هماهنگی — hamahangi** *(Persian)* — "harmony, coordination" (roughly "being of one melody"). Apt but long for a handle.

### Africa

- **Nkonsonkonson** *(Akan / Twi, Ghana)* — the adinkra symbol of the **chain link**: unity and interdependence ("we are linked in life and death"). Thematically bang-on for a *record-linking* tool. *Caveat:* long as a name.
- **Sankofa** *(Akan / Twi, Ghana)* — "go back and fetch it" — the backward-looking bird that retrieves what was left behind. Thematically gorgeous for an *archives* tool specifically (reconciliation as reaching back into the catalogue to recover identity). *Caveat:* a meaningful heritage concept, not a neutral word — higher cultural weight; treat with respect.
- **Pamoja / Umoja** *(Swahili)* — "together" / "unity." Simple and clear. *Caveat:* fairly generic and already used by various organisations.

---

## Summary table

| Name | Origin | Meaning | Why it fits | Cultural weight | Suggested handle |
|---|---|---|---|---|---|
| **Sandhi** | Sanskrit | junction/joining; also reconciliation; linguistic boundary-combination | joining + reconciliation + boundary resonance | Low | `sandhi` |
| **Paywand** | Persian | link, bond, graft, joining | literally *linking* records | Low | `paywand` |
| **Fú / Hefu** | Chinese | tally split into matching halves | reconciliation = matching halves | Low | `hefu` |
| **Sangam** | Sanskrit | confluence of rivers | bringing streams together | Low | `sangam` |
| **Awase** | Japanese | matching/joining (shell-matching game) | pairing the matching half | Low | `awase` |
| **Wasl** | Arabic | connection; joining of letters | joining components | Low–Med | `wasl` |
| **Musubi** | Japanese | tying, binding, connection | linking records | Low (trendy) | `musubi` |
| **Ittifaq** | Arabic | agreement, accord | accord/concord | Low | `ittifaq` |
| **Eoullim** | Korean | harmonising/matching well together | things that match/fit | Low | `eoullim` |
| **Samanvaya** | Sanskrit | reconciliation, synthesis | reconciliation (literal) | Low | `samanvaya` |
| **Nkonsonkonson** | Akan | chain link; unity | linking records | Med | `nkonson` |
| **Sankofa** | Akan | go back and fetch it | archives: retrieve identity | Med–High | `sankofa` |
| **Sulh** | Arabic | reconciliation, settlement | reconciliation (literal) | High | `sulh` |

*(Korean **어울림 eoullim** — "harmonising / fitting well together," from *eoulli-da*, to match/suit — is included in the table; a lovely, under-used native Korean word for things that go together.)*

---

## Shortlist (judged on aptness, not novelty)

- **Sandhi** — the deepest fit: joining + reconciliation + the linguistic-boundary resonance with how the tool combines code components. Low cultural weight.
- **Paywand** — clean, pronounceable, literally "link/bond." Low risk, high aptness.
- **Fú / Hefu** — reconciliation-as-matching-halves, with a great origin story (the tiger tallies) for the README. Bonus: your placeholder already echoes it.
- **Sangam** — confluence; easy to say, widely recognised, evocative.
- **Sankofa** — the strongest *archives-specific* metaphor, if the team wants to lean into the "reaching back into the record" theme and is comfortable with a higher-weight heritage term.

---

## European options, for comparison

So the team has the full slate in one place, the earlier (European-rooted) candidates:

- **Concordance / Concord** — means *both* "an index of references" *and* "a state of agreement/reconciliation" — doubly apt and domain-resonant. (Common word; the handle will need a qualifier, e.g. `refine-concordance`.)
- **Collate** — a bibliography term: to gather and compare leaves/records. Precise, instrument-like.
- **Accord** — short, clean, "agreement/reconciliation"; easy to claim as a handle.
- **Tessera** — a Roman token split in two halves that had to *match* to verify identity — the European parallel to the Chinese tally. Elegant but obscure.

---

## Choosing respectfully (notes for the discussion)

For any culturally-rooted name, it's worth:

- **Checking connotations with a native speaker.** Several of these (notably *sulh*, *sankofa*) are sacred, legal, or heritage-laden and read very differently in context than a dictionary gloss suggests.
- **Considering the team's relationship to the culture**, so the name lands as homage rather than decoration.
- **Weighting toward lower-weight, everyday/technical terms** (e.g. *sandhi*, *paywand*, *wasl*, *ittifaq*) if the team wants meaning without appropriation risk — versus the higher-weight end (*sulh*, *sankofa*, and *ubuntu* below).
- **Namespace hygiene** — confirm the handle is free (or qualifiable) on PyPI, GitHub, and the OpenRefine extensions list before committing.

## Avoid

- **Ubuntu** — semantically perfect (interconnection; "I am because we are") but *unusable* for software: Canonical's Linux owns the mindshare entirely.
- **Harambee** *(Swahili, "all pull together")* — apt, but now carries an unfortunate meme association (the spelling *Harambe*).
- **Yoga / Sutra** — meaningful (union; thread) but massively overloaded in tech/wellness.
- **"Reconciler" / anything built on "reconcile"** — clashes directly with OpenRefine's own "reconciliation" terminology; will be perpetually confusing in docs and conversation.

---

## Discussion prompts

- Which **image** do we want the name to carry — *matching halves*, *confluence/linking*, *accord*, or the *archives/retrieval* angle?
- Do we prefer a **neutral/technical** word (lower risk) or a **culturally weighty** one we have a real connection to?
- Internationally **legible** (Sangam, Concordance) or a distinctive **deep cut** (Sandhi, Fú, Tessera) we'll explain in the README?
- Does the name need to read well **as a verb** ("concord these," "link these")?

*Cultural meanings here are given in good faith and at a summary level; please sanity-check any shortlisted term with someone who speaks the language before it becomes the name.*

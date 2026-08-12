# decisions.md

Single source of truth for every judgement value in the platform — thresholds, cutoffs,
weights, business rules. Per the MVP build brief: **no judgement value may be inlined as a
magic number in code.** Code references these by ID (e.g. `decisions.CONC_1_SINGLE_STOCK`).

Every entry records: the value, the rationale, and the test that pins it.

## Status legend

- `UNRESOLVED` — needs a decision from the architect. **Code must not implement this yet.**
- `RESOLVED` — decided; code may reference it.
- `STATUTORY` — not a judgement call, but a legal/regulatory fact that must be verified
  against primary source and dated, not recalled from memory.

Nothing below is `RESOLVED`. No leak detector can be completed until the entries it
depends on are.

---

## 1. Ingestion & entity resolution

### ING-1 — Fuzzy match auto-accept threshold
**Status:** UNRESOLVED
**Question:** Above what match score is a parsed scheme name auto-bound to an AMFI scheme
code without asking the user?
**Proposal (not applied):** —
**Rationale needed:** The brief says truncated names are common and the truncated part is
often the plan variant (Direct/Regular), which determines the largest single leak. A
too-loose threshold silently binds the wrong plan and inverts the headline finding.
**Test that pins it:** A table of real truncated names → expected scheme code, including
at least one pair differing only by plan variant, asserting the pair never auto-resolves.

### ING-2 — Fuzzy match reject/ask threshold
**Status:** UNRESOLVED
**Question:** Below what score do we refuse to guess and ask the user to disambiguate?
And what happens in the band between ING-2 and ING-1 — ask, or present ranked candidates?
**Test that pins it:** Cases in the ambiguous band assert `status == NEEDS_USER_INPUT`,
never a bound scheme code.

### ING-3 — String distance metric
**Status:** UNRESOLVED
**Question:** Which metric backs ING-1/ING-2? Token-set ratio, Levenshtein, or a two-stage
(token blocking then edit distance)?
**Why it is not a free choice:** Metrics disagree sharply on truncated strings.
`"HDFC Mid-Cap Opportunities Dir"` vs `"HDFC Mid-Cap Opportunities Direct Growth"` scores
very differently under edit distance than under token-set. ING-1's numeric value is
meaningless without fixing this first.
**Test that pins it:** Same corpus as ING-1, scored under the chosen metric only.

### ING-4 — Plan/option disambiguation policy
**Status:** UNRESOLVED
**Question:** When the plan variant (Direct vs Regular) or option (Growth vs IDCW) is
absent or truncated away entirely, do we always ask, or infer from context?
**Note:** Defaulting here would fabricate the regular-vs-direct drag finding (LEAK-3) in
either direction. Recommend "always ask" but this is the architect's call.

---

## 2. Look-through concentration (LEAK-1)

### CONC-1 — Aggregation unit
**Status:** UNRESOLVED
**Question:** Aggregate at **company** level or **ISIN/security** level?
**Why it matters:** A company can have multiple listed securities (ordinary vs DVR
shares). ISIN-level aggregation undercounts true exposure to a single business.
Company-level requires a security→company mapping the free AMFI feed may not provide.
**Test that pins it:** A fixture where one company is held via two ISINs across two funds;
assert the reported concentration is the combined figure under the chosen rule.

### CONC-2 — Single-stock concentration threshold
**Status:** UNRESOLVED
**Question:** At what percentage of total portfolio value does look-through exposure to
one company become a reported finding?
**Note:** The brief's own example ("34% of your portfolio is in one bank across four
funds") is illustrative of output phrasing, not a threshold specification.
**Test that pins it:** Positive case above threshold, negative below, boundary exactly at.

### CONC-3 — Materiality floor
**Status:** UNRESOLVED
**Question:** Below what weight is an individual underlying holding excluded from
look-through aggregation entirely?
**Why it is needed:** A 40-scheme portfolio has thousands of underlying positions with
long tails at <0.01%. Without a floor, aggregation is dominated by noise and the
disclosure-staleness error exceeds the signal.

### CONC-4 — Sector/theme-level concentration
**Status:** UNRESOLVED
**Question:** Is concentration reported only per company, or also per sector? If sector:
whose classification (AMFI's? GICS-equivalent? AMC-reported sector in the disclosure)?
**Note:** Theme-level is explicitly deferred — see the thematic-taxonomy open question in
`docs/product-architecture.md`; there is no external standard and it needs an owner.

---

## 3. Fund overlap (LEAK-2)

### OVER-1 — Overlap metric definition
**Status:** UNRESOLVED
**Question:** How is pairwise overlap between two schemes defined?
Candidates: weighted common holdings `Σ min(wᵢᴬ, wᵢᴮ)`; Jaccard on holding identity
ignoring weight; count of common names.
**Why it is not a free choice:** These produce materially different numbers for the same
two funds, and the threshold in OVER-2 is meaningless until this is fixed.
**Test that pins it:** Two hand-built fund holding sets with a hand-computed overlap under
the chosen definition.

### OVER-2 — "Significant overlap" threshold
**Status:** UNRESOLVED
**Question:** What overlap value makes a fund pair a reported finding?

### OVER-3 — Cluster detection method and cutoff
**Status:** UNRESOLVED
**Question:** The brief asks for "clusters of funds sharing holdings," not just pairs.
Method (threshold graph + connected components? hierarchical clustering?) and its cutoff.
**Note:** Connected components on a threshold graph chains transitively — A–B and B–C
overlapping puts A and C in one cluster even if A and C share nothing. Whether that is
desired behaviour is a product decision, not an implementation detail.

---

## 4. Regular vs direct plan drag (LEAK-3)

### DRAG-1 — TER source and history
**Status:** UNRESOLVED
**Question:** Compute drag from *current* TER applied across the holding period, or from
*historical* TER as it actually varied?
**Why it matters:** TER changes over time. Current-TER is an approximation and, per the
citation rule, must be reported as such with its as-of date. Historical TER may not be
freely available in structured form — needs verification before this detector can claim
a rupee figure rather than an estimate.

### DRAG-2 — Compounding treatment
**Status:** UNRESOLVED
**Question:** Is the drag simple (`ΔTER × value × years`) or compounded on the foregone
growth?
**Why it matters:** Over a multi-year holding period these differ substantially. The
compounded figure is larger and arguably more truthful; the simple figure is more
defensible as a floor. Either is fine — but it must be a stated decision, and the output
wording must match which one was computed.

### DRAG-3 — Reporting materiality floor
**Status:** UNRESOLVED
**Question:** Below what rupee amount is drag not surfaced as a finding?

---

## 5. Category redundancy (LEAK-4)

### REDUN-1 — Redundancy definition
**Status:** UNRESOLVED
**Question:** Is redundancy defined by shared SEBI scheme category, by holdings overlap
(which would duplicate LEAK-2), or by both jointly?

### REDUN-2 — Count threshold
**Status:** UNRESOLVED
**Question:** How many schemes in the same category constitutes redundancy — 2 or more,
3 or more?
**Note:** Two funds in one category is a defensible diversification choice for some
investors; calling it a leak at n=2 may generate findings the user disagrees with, which
costs trust. Genuinely a judgement call.

---

## 6. Closet indexing (LEAK-5)

### CLOSET-0 — Benchmark constituent weights: availability blocker
**Status:** UNRESOLVED — **may block this detector from the MVP entirely**
**Question:** Active share requires the benchmark's constituent weights. Index constituent
weights are generally licensed products of the index provider (NSE Indices / BSE), not
free public data. That appears to conflict directly with the brief's constraint 5 ("do not
build anything in the MVP that depends on licensed price data").
**Decision needed:** Defer LEAK-5 to a later phase, license the index data, or substitute
a proxy measure that uses only free inputs.
**This must be answered before CLOSET-1/2 are worth answering.**

### CLOSET-1 — Active share formula
**Status:** UNRESOLVED
**Question:** Confirm `0.5 × Σ |w_fund,i − w_bench,i|` and the treatment of holdings
outside the benchmark, cash, and derivatives.

### CLOSET-2 — Closet indexing threshold
**Status:** UNRESOLVED
**Question:** Below what active share is a fund labelled a closet indexer?
**Note:** There are widely cited figures in the academic literature. I have deliberately
not written one here — the brief's rule is that the architect picks the value, and a
number carried in from a US large-cap study may not transfer to Indian mid/small-cap
funds.

---

## 7. Style drift (LEAK-6)

### DRIFT-1 — Market-cap classification source
**Status:** UNRESOLVED
**Question:** Confirm AMFI's periodic large/mid/small-cap stock classification list as the
source, and its refresh cadence.
**Note:** This list is published periodically, so a holding's cap classification has its
own as-of date — a fund can "drift" purely because AMFI reclassified a stock, with no
action by the manager. Whether that counts as drift is a product decision.

### DRIFT-2 — Drift measured against SEBI mandate or against stated style
**Status:** UNRESOLVED
**Question:** SEBI's categorisation rules impose minimum allocations per equity category.
Is drift a breach of that statutory minimum (in which case the threshold is given, not
invented), or a softer deviation from the fund's stated style?
**Recommended framing:** measuring against the SEBI mandate avoids inventing a number.
Still the architect's call.
**Depends on:** STAT-2.

### DRIFT-3 — Tolerance band
**Status:** UNRESOLVED — only if DRIFT-2 chooses the softer definition.

---

## 8. Tax leaks (LEAK-7)

### TAX-0 — Regime is date-dependent, not current-state
**Status:** UNRESOLVED — **design-shaping, please read**
**Issue:** Indian capital gains treatment of mutual funds changed materially more than
once in recent years, including changes to debt-fund taxation and to capital gains rates
and holding-period definitions. A holding's correct tax treatment therefore depends on
**when it was purchased**, not only on what the rules are today.
**Consequence:** a tax-leak detector that applies today's rules uniformly to a portfolio
containing older purchases will produce confidently wrong numbers — the worst possible
failure for this product, since it is stated as fact with a citation.
**Decision needed:** Confirm the platform models tax rules as a dated ruleset (rule
versions with effective-from dates), not a single current ruleset.

### STAT-1 — Capital gains rules, per regime period
**Status:** STATUTORY — must be verified against the Finance Act / CBDT primary source and
recorded here with effective dates. **I have not written values from memory, deliberately.**
Required per period: equity-oriented STCG rate, LTCG rate, LTCG exemption amount, holding
period boundary, and the equivalent for non-equity schemes.

### STAT-2 — SEBI scheme categorisation minimums
**Status:** STATUTORY — must be verified against the SEBI categorisation circular and
recorded here. Required: the minimum allocation per equity category. Feeds DRIFT-2.

### TAX-1 — "Approaching" the ST/LT boundary
**Status:** UNRESOLVED
**Question:** How many days before a holding crosses the short-term/long-term boundary do
we flag it?
**Note:** This is the one tax finding closest to a recommendation. Flagging "sell after
date X to pay less tax" is arguably advice. Phrasing must stay factual — "this holding
crosses the long-term boundary on [date]" — and this constraint should be recorded
alongside the value.

### TAX-2 — Exit load data source
**Status:** UNRESOLVED
**Question:** Exit load structures live in scheme documents. Is a structured, free source
available, or is this per-AMC parsing? If unavailable, LEAK-7's exit-load component may
need to defer.

### TAX-3 — Unharvested loss materiality floor
**Status:** UNRESOLVED
**Question:** Below what rupee loss is harvesting not surfaced?

---

## 9. Cross-cutting

### X-1 — Disclosure staleness ceiling
**Status:** UNRESOLVED
**Question:** AMC portfolio disclosures are monthly. Beyond what age is a disclosure too
stale to compute look-through findings from — or is it never suppressed, only cited with
its date?

### X-2 — Confidence and suppression policy
**Status:** UNRESOLVED
**Question:** When inputs are stale or partially resolved, is the finding suppressed,
or shown with a caveat? The brief's "no silent fallbacks" rule requires this be explicit.

### X-3 — Pipeline version tagging scheme
**Status:** UNRESOLVED
**Question:** Confirm the version identifier format and the rule for re-scoring history on
change. The brief requires never comparing scores across pipeline versions.

---

## Open dependency — not a decision, an input I cannot obtain

**Eval corpus.** The brief specifies ~200 real portfolio screenshots with hand-labelled
expected parse output. I cannot source these. They must be supplied.

Two things to settle when they are:
1. **PII.** Real screenshots contain account numbers and names. The brief mandates
   discarding uploads after extraction and never persisting them — a committed eval corpus
   of 200 real screenshots is in direct tension with that rule. Redaction or synthetic
   regeneration needs to be decided before the corpus lands in the repo.
2. **Storage.** Whether the corpus lives in this repository or outside it.

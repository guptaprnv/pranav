# Data Architecture

Companion to [`product-architecture.md`](../product-architecture.md), Section 7. Detailed design for the data layer: what gets stored, how entities are modeled and linked across domains, and how staleness is tracked and surfaced rather than hidden.

## Storage

Six categories of data, each with different storage requirements — not one undifferentiated database:

1. **Reference/entity data** — the entity graph (ISIN-linked company/fund identities), sector classification, the theme taxonomy.
2. **Time-series market data** — price history, MF NAV history, macro variable history (oil, repo rate, USD-INR) — needed for alpha/beta/VaR/correlation and factor-beta regressions.
3. **Holdings snapshots** — user direct positions, plus MF look-through holdings.
4. **Computed quant primitives** — alpha, beta, VaR, correlation, drift, concall language-signal scores, factor exposures, blended exposure, confidence scores.
5. **Unstructured source documents** — concall transcripts, filings, news.
6. **The reasoning/audit trail** — tool-call logs, claims tables, published theses, Explanation Layer outputs.

Five decisions follow from that split:

**Time-series data is fine on Postgres + a time-series extension (e.g. TimescaleDB) at Phase 1 scale.** A few thousand tracked instruments with daily data is not a big-data problem. Reaching for a dedicated time-series database before there's a measured reason to is the same mistake as over-engineering the LLM call for a Tier 0 lookup.

**The entity graph is a relational model, not necessarily a graph database.** The relationships involved — company ↔ ISIN ↔ fund holding ↔ user position — are bounded and shallow (see Entity Graph, below), not deep recursive traversal. Well-indexed join tables in the same Postgres instance are simpler to keep consistent than operating a second storage technology. "Graph" describes the conceptual model, not a technology requirement.

**Holdings snapshots must be versioned by as-of-date, never overwritten.** Required by two things already decided elsewhere: the freshness-mismatch citation principle (a query joining monthly-stale MF holdings with near-real-time prices has to cite which as-of date it used) and the Mutual Funds domain's backward-traced-performance requirement, which needs historical holdings, not just current ones.

**Computed primitives need `value`, `computed_at`, `pipeline_version`, and `input_as_of` as first-class schema fields.** This is what makes the citation and auditability mechanisms in the main doc real at the storage layer — a citation like "alpha 1.2, computed [date]" only works if that timestamp and version are attached to the stored value, not reconstructed after the fact.

**The audit trail is a genuinely separate, append-only store from operational "current state" — not the same table with history bolted on.** "Current alpha for stock X" is a value that gets replaced; "what the platform knew and said on date T" cannot ever be replaced. Conflating the two is the concrete way the auditability principle gets quietly broken in practice.

One more point worth carrying forward: compute-once-per-entity has a security/privacy benefit beyond cost — the expensive per-entity computation never touches user PII at all; only the final per-user lookup step does. A smaller, more containable surface to secure.

## Entity Graph

The core identifier problem is one level messier than "just use ISIN." ISIN is issued at the instrument level, not the economic-entity level — a company can have multiple ISINs (ordinary shares vs. DVR shares), and a mutual fund scheme has a separate ISIN per plan (growth/dividend, direct/regular). Concentration and exposure reasoning needs to happen at the **Company** and **Fund** level, not the instrument level, or "concentration in Reliance" would undercount a user holding both the ordinary and DVR ISIN.

So the graph needs two layers: a Security/Share-Class layer (ISIN-level, matches what data vendors and holdings disclosures actually reference) rolling up to a Company/Fund layer (the level everything else — concentration, theme tags, concall history — actually attaches to).

**Structure:**
- `Security(ISIN) → belongs_to → Company`
- `FundShareClass(ISIN) → belongs_to → Fund`
- `Fund → holds → Security` (dated, weighted — the look-through edge, versioned per Storage above)
- `User → holds → Security` and `User → holds → FundShareClass` (direct positions)
- `Company → tagged_with → Theme`, `Company → classified_as → Sector`, `Company → has → Concall` (dated), `Company → referenced_in → News` (dated)

Concrete test case for why this doesn't need a graph database: "which funds this user holds also hold this stock" is a two-hop join (`User→Fund`, `Fund→Security`) — well within plain relational SQL.

**The hard part is resolution, not storage.** MF holdings disclosures list positions by company name — sometimes with ISIN, often not, and not always spelled consistently. Mapping "Reliance Industries Ltd" from a fund's monthly disclosure PDF to the canonical Company node is a fuzzy-matching problem. This needs its own small pipeline (name + ISIN matching, a review queue for ambiguous matches) and a defined failure behavior: an unresolved holding is flagged and excluded from computed aggregates with a visible caveat, never silently guessed into the nearest match — the same confidence/graceful-degradation principle used throughout the reasoning layer, applied to entity resolution.

**Corporate actions mean the graph needs validity periods, not static identity.** Renames, mergers, delistings, spin-offs — "Company X was known as Company Y before date D" has to be representable, or backward-traced performance and historical citations break the moment a company changes name. New listings are the opposite edge case: the Company node has to exist from day one even though every downstream computation on it starts out low-confidence for lack of history.

**Sourcing** ties back to the still-open equity data vendor decision (`product-architecture.md`, Section 7, Data sources) rather than being a separate problem — a commercial data vendor typically bundles the security/company master alongside prices. AMFI (already resolved) covers the fund-side master.

**User holdings stay a separate, access-controlled store that references the graph, not part of it.** The shared graph (company, fund, theme, concall linkages) has no PII in it at all; only the `User → holds` edges are sensitive, and those live in a more tightly controlled store — see the Phase 1 build note below for how this is being deferred in the first build.

## Entity Caching & Staleness

Two different things get called "caching" here, and they have different answers.

**A dedicated cache layer (Redis or similar) is probably premature at Phase 1 scale.** LLM prompt caching (`product-architecture.md`, Section 7, Optimizing reasoning) is separate and definitely needed — not reprocessing the same grounded context tokens across repeated queries about the same entity. A data-layer cache for computed primitives is a different thing, and at a few thousand entities, an indexed "latest value" lookup on Postgres is already fast without a second storage technology. Add a cache layer when a measurement says the database is the bottleneck, not because "caching" is on the list of things to build.

**Staleness is the real design problem, and it varies by primitive type — there's no single threshold:**
- Price-derived primitives (beta, VaR): should refresh close to daily.
- MF-look-through-derived primitives (blended exposure, concentration): structurally bounded by the monthly disclosure cadence. Not a caching bug to fix — it's the data-freshness ceiling already named as a bottleneck in the main doc.
- Concall-derived signals: event-driven, fresh as of the last call, stale until the next one.

The citation layer needs an as-of date **per primitive**, not one freshness stamp for a whole answer.

**Invalidation should be event-driven, not TTL-based expiry.** Recompute is triggered by the event that changed the underlying input — new price close, new concall transcript, new MF disclosure — the same pattern the Concall Monitor already uses, extended to prices and holdings.

**Cascading staleness through the entity graph is the genuinely hard part.** When a fund's monthly holdings disclosure updates, that doesn't just affect the fund's own primitives — it affects every blended-exposure and concentration computation for every user holding that fund, because those were derived from the fund's look-through edge. This needs a dependency/lineage mechanism: knowing which downstream computed values depend on which upstream fact, so one update can correctly flag or recompute everything derived from it. Different from pipeline versioning, which tracks "the method changed" — this tracks "the input changed but the method didn't," and both are necessary.

**During the window between new data arriving and recompute finishing, serve the stale value with an explicit staleness flag rather than blocking the query.** The same graceful-degradation instinct used for grounding-gate failures and low confidence — but it needs to be a conscious, written-down choice, not a default nobody decided.

**User holdings sync is a separate staleness axis from entity-level data, and easy to overlook.** "Does this stock need review" is only as good as both the entity-level signal's freshness and whether the platform's picture of what the user actually holds is current. See the build note below for how this is scoped in the first build.

## Phase 1 build note: fixture-based user holdings

Initial implementation uses fixture/mock user holdings data rather than a live broker/demat connection, with real integration deferred to a later phase. This simplifies — defers, doesn't eliminate — one specific concern above: user-holdings-sync staleness is moot when holdings are fixtures, since there's no sync to go stale.

It does **not** defer the entity graph, the computed primitives, or the reasoning pipeline — all of that needs to be built and exercised against realistic fixture holdings regardless, since it's the same architecture a live integration will sit on top of later. Worth keeping the fixture data structured exactly as a real broker/demat feed would arrive (same fields, same `User → holds` edge shape) so swapping in a live source later is a data-source change, not a schema change.

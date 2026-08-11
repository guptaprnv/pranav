# Retail Research Platform — Product & Architecture Doc

## 1. Vision

A dynamic research platform that answers *"why does this stock/fund/portfolio look the way it does, right now, given what's happening"* — for both retail investors and research analysts, off one shared reasoning core.

The single most important design constraint, carried over directly from the original sketch: the system explains and reasons about a position **according to a thesis** — it does **not** issue direct buy/sell calls. This is not a hedge, it's the product. It's what differentiates the platform from a tip service, and it's what makes the analyst persona want to use the same core a retail user does — analysts want the reasoning chain, not a verdict.

## 2. Founding thesis: research creates value; management captures it — and erodes it

Research and analysis is where value is *created* — a correct thesis, understood, is worth something before a single rupee moves. Management — the ongoing act of transacting, rebalancing, timing entries and exits — is where that value gets *captured* (turned into realized, monetized outcome) but it's also where it most often *erodes* (fees, mistimed decisions, behavioral mistakes).

That ordering is deliberate, not incidental: the product's core has to be the research/reasoning layer, because that's the actual value-creation engine. Management-as-a-service (RIA-style personalized advice, PMS-style discretionary management) is a second, later layer built *on top of* a proven research core — not the starting point. Building management first, without the research layer being right, just moves the erosion risk earlier.

## 3. Regulatory path: Research Analyst (RA) license, in-house

Resolved: the firm will hold its own **SEBI Research Analyst (RA)** registration, rather than depending on a marketplace of external analysts. This is a deliberate fit, not just a compliance workaround — RA registration's own constraints already match the product's design:

| License | Can do | Constraint |
|---|---|---|
| **RA (chosen for v1)** | Research & analyze stocks + MFs, publish to many | One-to-many only, no personalized advice, subscription-monetized |
| MFD | Recommend mutual funds | No fee (commission only), no personalization |
| RIA *(future scope)* | Personalized advice | No commission — fee/AUM only |
| PMS *(future scope)* | Full discretionary management | High compliance overhead, high investment/net-worth threshold |

Holding the RA license in-house doesn't change what the output looks like — the answer is the same either way, constrained by SEBI's RA rules (one-to-many, no personalized advice). What it changes is *who* is legally allowed to produce and publish that answer: the firm itself, rather than needing to broker third-party analysts. RIA and PMS are explicitly **not** v1 — see Section 10.

## 4. The wedge: lower-fund retail users locked out of research

The initial product-market gap: quality research and analysis is effectively inaccessible to **lower-fund retail users** today. It's either priced for institutional-scale money, or it assumes a level of financial literacy that segment typically doesn't have.

An in-house RA publishing one-to-many strategies solves the *access and economics* half of that gap — one thesis, many users, subscription pricing instead of per-client advisory fees. It does not, by itself, solve the *comprehension* half. That's the actual product to build: a layer that takes an RA-grade thesis and explains it in **lenient, plain terms** — closing the financial-knowledge gap that's the real blocker to this segment acting on research at all, not the absence of research itself.

Done right, this is a genuine win-win, not just a euphemism for "cheap tier": the RA gets distribution leverage (one thesis reaches many subscribers instead of one advisory relationship at a time), and users — especially the lower-fund segment other channels structurally can't serve — get access to real research they can actually understand and act on themselves.

Other wealth/goal segments from the notes (HNI, UHNI, Family Wealth, Business People Money; long-term/liquid-money/passive-income goal types; aggressive vs. conservative return expectations) are real, but not the v1 wedge — they matter more once RIA/PMS layers exist to serve them with something beyond research access.

## 5. Analysis Domains

Four domains, each decomposed into concrete sub-analyses. RA registration covers both Stock and Mutual Fund research equally — domain choice below is about differentiation and reuse, not regulatory scope.

**Stock**
- Valuation
- Buy range
- Forward growth *(needs in-product education — don't assume the concept is understood)*
- Sentiment & trust *(includes a concall transcript-derived signal — see Section 6)*
- Analyst ratings (aggregation, not the platform's own rating)

**Portfolio**
- Drift from target asset allocation
- Concentration risk (position/sector/theme)
- Correlation — across stocks within a portfolio, across industries, and across mutual fund holdings (detecting hidden concentration when multiple funds hold the same underlying names)

**Industry**
- Impact of government policy
- Geopolitical impact

**Mutual Funds**
- Backward-traced portfolio performance (what actually drove the return)
- Fund manager style bets
- Portfolio financial parameters — alpha, beta, VaR
- Fund manager profile *(same concall transcript-signal technique applies to fund manager commentary/interviews, not just company earnings calls)*
- Fund monitoring: how actively a manager rebalances in response to market moves, and what effect that has on the fund

## 6. System Architecture

```
                    ┌─────────────────────────────┐
                    │          Data Layer          │
                    │  Prices · News · Product/     │
                    │  company fundamentals ·       │
                    │  Global events · Supply chains │
                    │  Concall transcripts (text)    │
                    └───────────────┬──────────────┘
                                    │
   ┌───────────────────┐           │
   │  User Query Layer   │──────────┤
   │  Retail: NL query    │          │
   │  Analyst: params     │          ▼
   │  + Holdings/portfolio│  ┌─────────────────────────┐
   └───────────────────┘   │    Intelligence Layer     │
                            │  ┌──────────────────────┐ │
   ┌───────────────────┐   │  │ Quant primitives       │ │
   │   MF-specific        │──▶│ alpha, beta, VaR,      │ │
   │   context: portfolio │   │ correlation, drift,    │ │
   │   changes, past perf,│   │ concall language signal│ │
   │   manager review,    │   └──────────┬─────────────┘ │
   │   rebalance frequency│              │               │
   └───────────────────┘   │              ▼               │
                            │  ┌──────────────────────┐ │
                            │  │ Reasoning agent        │ │
                            │  │ (RA thesis, grounded   │ │
                            │  │  on quant + data)      │ │
                            │  └──────────┬─────────────┘ │
                            └─────────────┼───────────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    ▼                     ▼                     ▼
               Dashboard               Lists              Reasoning / Fund view
          (portfolio health,     (screened stocks/     ("according to this
           at-a-glance)           funds, ranked)         thesis" — not a
                                                          direct suggestion)
                                                                │
                                                                ▼
                                                     Explanation Layer (retail)
                                                     same thesis, lenient terms —
                                                     analyst view stays full-detail
```

*(Concall language signal is now shown directly inside Quant Primitives — it's a first-class primitive, not a footnote. See the paragraph below for why it belongs there rather than in the Reasoning Agent.)*

**Key architectural point from the original sketch, worth keeping explicit:** the Intelligence Layer is two-tiered, not one LLM call. A **quant primitives layer** computes alpha, beta, VaR, correlation, drift, and — as of this round — the concall language-signal score, deterministically/structurally from data — these are numbers, not model output, and must be auditable. A **reasoning layer** (agentic, LLM-driven) sits on top, grounded on those computed numbers plus news/events/policy context, and produces the narrative. This split matters for trust: an analyst (and a regulator) will accept a hallucination-prone LLM explaining *why* a computed VaR is high, but not an LLM inventing the VaR itself. The same test is why the concall signal lives here and not as something the Reasoning Agent free-associates from a transcript on the fly.

**New from this round: the Explanation Layer is a first-class component, not a UX nice-to-have.** It sits between the reasoning agent's output and the retail surface, translating the same one-to-many RA thesis into lenient terms. Analysts see the full reasoning chain directly; retail users see the translated version. This is the layer that actually closes the wedge gap in Section 4 — the RA solves access, the Explanation Layer solves comprehension.

**Revised this round: concall signal comes from the transcript, not the audio.** The previous round proposed acoustic vocal-tone modeling (pitch, hesitation, stress) on the raw call audio. Decision: drop that — the added signal value doesn't justify the added complexity (a dedicated audio ML model, plus the accent/code-switching/speaker-attribution accuracy risk flagged as an open question last round). Instead, the concall's speech-to-text transcript is the input, and the signal is derived from the **text**: language/guidance shifts quarter-over-quarter ("reiterate" vs. "revise" guidance), hedging/uncertainty markers in how questions get answered, and structured extraction of the metrics and forward-looking statements actually discussed. This is still a **Quant Primitives** input, not a Reasoning Agent guess — a structured, versioned score/extraction from a defined NLP pipeline over text, auditable the same way alpha/beta/VaR are, just without the audio-modeling layer. Applies directly to Stock's Sentiment & Trust sub-analysis and to Mutual Funds' Fund Manager Profile (same technique, run on fund manager commentary), and fits the "event impact thesis" query pattern from the original notes — a concall is a discrete, dated event with a text signal to reason over. Sourcing plan for the transcript itself — see open question 5, Section 11.

**The Concall Monitor — this is what turns the signal above into an active capability, not a passive data source.** For every company (and fund) a user holds or follows, the platform tracks the earnings-announcement calendar and, as each concall's transcript becomes available, automatically ingests it and produces a structured overview — summary, key metrics/guidance discussed, and the language-signal score, as one artifact per call. This is the concrete version of a mechanism that showed up in the very first round of notes and was never threaded into the architecture: *"monitoring when they need review, by some static signals of performance."* A concall is exactly that kind of static, dated signal — the Concall Monitor is what makes "does anything I hold need a look" a standing capability instead of something the user has to remember to check for. It's scoped the same way everything else here is: the overview and score are the same one-to-many artifact for every subscriber holding that name, surfaced generally — not "this changed for *you*," which would tip into personalized advice the RA registration doesn't cover.

**Correction from checking the market directly: the raw tracking-and-summary layer is not white space, and shouldn't be built as if it were.** Dedicated concall-tracking products already exist and are cheaply available — Multibagg has a feature literally named "Concall Monitor" (recordings, transcripts, AI summaries, upcoming-result tracking), Earnings Pulse does a concall calendar + transcripts + AI summaries starting around ₹1,799/year, and AlphaStreet, Trendlyne, and StockAdda all cover this ground too. This reframes the buy-vs-build decision from Section 11, open question 5: the calendar-tracking-and-summary layer is commoditized plumbing to license, not a component to build from scratch, and there are now several viable vendors to compare, not just AlphaStreet. What isn't commoditized, and stays the actual differentiator, is everything downstream of it — feeding that signal into portfolio-grounded reasoning tied to a user's actual holdings, through an RA-licensed one-to-many lens, translated by the Explanation Layer. None of the products above do any of that.

## 7. Technical Architecture: Stack, Model, Evals, Auditability & Citation

Everything above is product and domain scoping. This section is the engineering layer underneath it — what it's built with, what model does the reasoning, how we know the outputs are trustworthy, and how every claim traces back to something real.

### Tech stack

Proposed as a default, not a mandate — team skills/existing infra should override any of this:

- **Data & quant primitives service**: Python — dominant ecosystem for the alpha/beta/VaR/correlation/drift calculations, pandas/numpy for the math, straightforward integration with whatever price/fundamentals/AMFI vendor gets chosen.
- **API layer**: a lightweight async framework (e.g. FastAPI) — the Reasoning Agent's responses should stream, and the Concall Monitor's ingestion is I/O-bound (waiting on filings/vendor APIs), both of which favor async over a traditional sync framework.
- **Storage**: Postgres for structured data (holdings, computed quant primitive values, published theses, audit log) plus a time-series-friendly setup for price history; object storage for raw transcript/filing PDFs.
- **Job orchestration**: something that can run the Concall Monitor's calendar-tracking and ingestion reliably on a schedule and retry on failure — doesn't need to be exotic at this stage, just reliable.
- **Reasoning/agent orchestration**: keep this custom and minimal rather than reaching for a heavy agent framework. A fixed, small toolset (query quant primitives, query concall overview, query news) that's easy to log every call of is more valuable here than a general-purpose framework's flexibility — the audit and citation requirements below depend on knowing exactly what the agent queried and when.
- **Frontend**: flexible, whatever the team already knows (React/Next.js is the common default for a dashboard + retail app).

This is the one area of this doc that's genuinely about team fit rather than something the product requirements dictate — revise once team size/skills are known.

### Data sources

Consolidating what's been scattered across earlier open questions, now that concall sourcing is resolved:

| Source | Status |
|---|---|
| Concall transcripts | **Resolved** — buy from a vendor (Multibagg/Earnings Pulse/AlphaStreet/Trendlyne/StockAdda bake-off), Section 11 open question 5 |
| AMFI mutual fund NAV/holdings | Public, well-established — AMFI publishes daily NAVs and periodic portfolio disclosures directly |
| Equity prices & fundamentals | **Still open** — this is different from the concall case: live price/fundamentals redistribution typically needs a licensed commercial data vendor agreement, not a scrape of public regulatory filings. Needs the same kind of direct market check the concall question got, not an assumed vendor name |
| News/sentiment | **Still open** — same: needs a market check before assuming a source |

Worth flagging explicitly: the concall sourcing answer (public filings, scrapable) does **not** generalize to live prices and fundamentals — those are commercially licensed data, a different sourcing category with a different cost and legal structure. Don't let the concall resolution create false confidence that the rest of the data-sourcing open question is similarly easy.

### Query handling & aggregation

Not every query needs the Reasoning Agent, and treating them as if they do is both slower and riskier than necessary — more LLM surface area means more grounding-gate work and more cost for questions that are actually just arithmetic. A query router should triage by what the query actually requires, not send everything through the same pipeline:

- **Tier 0 — direct lookup** ("what's fund X's alpha"): straight to the quant primitives service, no LLM involved at all. Fastest, cheapest, and zero hallucination surface, because nothing is generated.
- **Tier 1 — structured screen/filter** ("midcap funds, 3Y alpha > 1, manager tenure > 5Y"): a small model translates the NL query into a structured filter (the analyst's parametrized query needs no translation at all), the filter executes deterministically against precomputed data, and only the result narration — if any — touches the Reasoning Agent.
- **Tier 2 — synthesis/explanation** ("why is my portfolio drifting"): the full two-stage grounded pipeline described below — this is genuinely where the Reasoning Agent's cost and latency belong.
- **Tier 3 — fan-out/aggregate** ("does anything I hold need a look," "how does this RBI policy affect my holdings"): the expensive one, and the one that needs the most deliberate design.

**The single most important aggregation decision: compute once per entity, not once per user.** The RA constraint (one-to-many, no personalization) isn't only a compliance boundary — it's also what makes this affordable. If subscribers hold overlapping names, "does this stock need review" has to be computed once per stock, on the Concall Monitor's schedule (Section 6), and then looked up per user's holdings — not re-reasoned separately for every user asking about the same underlying event. Designing it the other way — live fan-out reasoning per user per query — is the kind of mistake that's cheap to make early and expensive to unwind under load, so it belongs in the architecture now, not as a later optimization.

Portfolio-level aggregation (drift, concentration, correlation across a user's own holdings) stays pure computation — matrix math, not the LLM — consistent with everything else in this doc. The Reasoning Agent's job is explaining a computed aggregate, never producing one.

### Cross-domain query reasoning

Tier 3 above covers fan-out within one domain — many holdings, one kind of question. The harder case is a query that has to reason across genuinely different domains at once: "how does this rate hike affect my funds *and* my direct holdings *and* my portfolio's risk," or the MF look-through case from Section 5's Portfolio domain — "which of my direct holdings also show up inside my funds, and does that create hidden concentration." That needs a few things the single-domain pipeline doesn't:

**A canonical entity graph, or cross-domain joins silently break.** The same company exists as a stock in the user's direct portfolio, as a holding inside several of the user's funds (via look-through), and has its own concall history and industry/policy tags — four different representations across four different data stores. Nothing below works unless one identifier (ISIN or equivalent) ties all of them together. This is a data-modeling prerequisite, not something the Reasoning Agent can paper over at query time.

**Cross-domain numeric aggregation stays a quant primitive, not something assembled live.** Combined sector exposure across direct holdings plus fund look-through, or a correlation matrix spanning both, is exactly the "the LLM never does arithmetic" principle from the grounding-mechanism section above — just applied across domains instead of within one. It belongs as its own precomputed primitive (a "blended exposure" calculator, say), the same way alpha/beta/VaR do, not stitched together ad hoc from separate tool-call results inside a single reasoning pass.

**A query-planning step, and the plan itself needs a grounding check, not just the answer.** A cross-domain question first has to figure out which entities and domains are actually relevant — which holdings are exposed to this policy, which funds hold this stock — before any synthesis happens. That scoping step can be wrong (miss a relevant holding, include an irrelevant one) independent of whether the final narrative is grounded, so the plan needs to be checkable against the entity graph above, not left entirely to the model's judgment.

**Two independently-true facts don't earn a relationship between them for free.** This is a failure mode specific to cross-domain reasoning, distinct from the hallucination and unfaithful-narrative modes already named: the model correctly retrieves that a rate hike happened *and* that a fund underperformed, then asserts the two are connected — a claim that needs its own grounding (was that correlation actually computed?), not one it inherits just because both halves are individually true. The claims table has to treat a cross-domain relationship as its own claim requiring its own citation, never a free inference from two cited facts sitting next to each other.

**Conflicting signals across domains get presented, not resolved into one verdict.** Quant primitives can say a fund is performing well while the concall signal shows the manager hedging on guidance — cross-domain reasoning will surface exactly this kind of tension regularly. Synthesizing it into one artificial conclusion drifts toward a recommendation; naming the tension explicitly is both more honest and more aligned with "reasoning, not a tip" than picking a side.

**Freshness mismatches compound across domains and need to be surfaced, not glossed over.** MF holdings are a month stale (Section 11, open question 2) while price data is closer to real-time; any query joining them is combining two different "as-of" dates. That mismatch is itself a fact the citation needs to carry, not something the narrative should imply is simultaneous.

### Review Trigger framework — generalizing beyond concall

A worked example forced this: *"stocks which need review — from performance, concentration, or thematic risk, across MFs and stocks."* The Concall Monitor (Section 6) is already a review-trigger mechanism, but scoped to one signal source. This query makes clear it needs to generalize into a framework, with concall as one instance rather than the whole thing — the same "static signals of performance" idea from the very first round of notes, just with more signal sources feeding it than originally scoped.

Two trigger categories, not one:
- **Entity-level triggers** — computed per stock/fund, same pattern as the Concall Monitor: performance decline, concentration/thematic breach. Each needs its own defined, general threshold (Section 11, open question 6 already flags this for concall specifically; the same requirement now applies to performance and concentration triggers too).
- **Macro-level triggers** — computed once per macro event (a rate decision, a large commodity move), then fanned out to every subscriber with material exposure, rather than computed per user. New category, introduced by the next worked example.

**The screening query itself decomposes the same way everything else in this section does.** The filtering step — which names trip a threshold — is deterministic: precomputed per-entity scores checked against thresholds, no LLM. Only the flagged subset goes to Tier 2 for the "why," reusing precomputed artifacts rather than reasoning live per user.

**"Across MFs and stocks" requires blended exposure, which confirms the primitive already proposed under cross-domain reasoning above** — concentration and thematic exposure computed on direct-plus-look-through holdings, summed per underlying company via the entity graph, rolled up to theme/sector level. Not a hypothetical use case for that primitive; a direct one.

**Thematic risk introduces a genuinely open question sector classification doesn't have.** Sector has an established standard to lean on (GICS or equivalent). Theme doesn't — someone has to define and maintain what counts as, say, a "China+1" or "rate-sensitive" theme, which is an editorial/curatorial choice, not a computation. Needs an owner and a maintenance cadence, and possibly its own disclosure, since it's the platform's own methodology rather than an external standard. Tracked as open question 7 in Section 11.

### Macro factor exposure & event impact reasoning

The other worked example — *"how would oil price, the current war, or an RBI repo rate change affect my portfolio"* — is the "event impact thesis" query pattern that's been an unfleshed bullet under the Industry domain (Section 5) since the first draft. The three examples aren't the same shape of input, and that split matters architecturally:

- **RBI repo rate and oil price are discrete or continuous but quantifiable** — a clean before/after number (+25bps, oil up 15%).
- **"Current war" is open-ended** — no single number to shock, situational and evolving.

That means two different mechanisms under one query type, not one:

**For quantifiable factors:** a new primitive, **factor exposure / macro-beta** — the same statistical idea as market beta, regressed against oil price or repo rate history instead of the index, computed per stock. Portfolio-level exposure is a weighted sum via the entity graph — mechanical, no LLM — giving a real number ("your portfolio's oil-beta is X, driven mainly by holdings A, B, C") instead of a narrative guess at exposure. The same thin-data confidence flagging described below applies here too: a newly-listed stock won't have enough history for a reliable regression.

**For open-ended events:** there's no variable to regress against, so forcing this into the factor-beta framework would be false precision in the opposite direction from hallucination — inventing a number that doesn't deserve to exist. This stays grounded narrative synthesis over news: which holdings are named or sector-implicated, what the transmission channel is. Tier 2, citation-heavy, no computed beta behind it.

**This is also a macro-level Review Trigger**, per the framework above: a large oil move or an RBI decision is exactly the kind of signal that should compute once and fan out to every subscriber with material factor exposure, not get reasoned about per user per query.

### The personalization boundary — one general principle instead of three

Three separate places in this doc ask a version of the same question — does something stay one-to-many research, or does it edge into personalized advice the RA registration doesn't cover:
- The Explanation Layer rewriting a thesis into lenient terms (Section 11, open question 3)
- The Concall Monitor generating a per-holding overview (Section 6)
- A factor-exposure computation run against a specific user's specific holdings (above)

Proposed general principle, rather than resolving each separately: **a general, one-to-many thesis or computation, applied mechanically to a user's own portfolio composition, stays research. The line gets crossed only when the substance of the thesis itself is tailored to the individual** — not when the arithmetic happens to use their numbers. "Rate hikes pressure rate-sensitive sectors" is generic; "your portfolio's rate-beta is X, from holdings A/B/C" is that same generic thesis run against the user's own composition — still research under this framing. "You should sell your bank stocks because rates are rising" is a tailored recommendation — the platform's stated design already refuses to produce that.

This is a proposal, not a resolved compliance answer — it still needs sign-off from whoever handles the RA registration before being treated as settled, same caveat as everything else compliance-adjacent in this doc.

### Model architecture

Two different jobs, two different model choices:

- **Reasoning Agent**: needs strong grounded reasoning, tool-use, and long context (to hold quant primitives + concall extracts + news + the user's actual holdings in one pass), and needs to be low on hallucination since its numeric claims have to trace to real data. A frontier-tier model via API is the right call here, not a self-hosted/fine-tuned model — self-hosting frontier-quality reasoning is expensive and unnecessary at this stage. Claude, GPT, and Gemini are all reasonable candidates; Claude's long context and prompt-caching economics are a natural fit for a pipeline that re-grounds the same portfolio/domain context repeatedly, but this deserves an actual cost/quality bake-off once volume estimates exist, not a default pick.
- **Explanation Layer**: a narrower job — rewrite an already-approved thesis into lenient language, not generate new claims. This can run on a smaller/cheaper model, but more importantly, its prompt has to be constrained to **rewrite only**: forbidden from adding claims, numbers, or recommendations the Reasoning Agent didn't already produce. That constraint is what keeps it inside the "not personalized advice" boundary from Section 11, open question 3 — it's a compliance requirement enforced through the prompt/architecture, not just a style choice.
- **Tool-use boundary**: the Reasoning Agent should only be able to call a fixed, small set of internal tools (quant primitives service, concall overview, news/events) — no freeform web access. That constraint is what makes both auditability and citation, below, tractable: every claim in an output can be traced to a specific tool call with a specific timestamp, because there's nowhere else the claim could have come from.

### Grounded reasoning vs. black-box reasoning — the actual mechanism

"Grounded" has been used a lot in this doc without saying what enforces it. It's not a property a model has by default, and it's not the same thing as the model *sounding* like it's reasoning carefully. It has to be a mechanism, checkable independently of the model's own narrative about itself.

**Core rule: the Reasoning Agent is never allowed to "know" a fact — only to retrieve and reason over facts it was handed.** Anything specific — a number, a date, a guidance line, a rating — has to come from a tool call in this session, never from the model's training data or free association. This is what the tool-use boundary above actually buys: not just tidiness, but the precondition for everything below being checkable.

**Two distinct failure modes, worth naming separately because they need different defenses:**
- **Hallucination** — the model states a number or fact that wasn't in what it retrieved. The defense is mechanical: verify every claim against the tool-call log.
- **Unfaithful narrative** — the model retrieved the *correct* facts, but the reasoning it writes down isn't actually how it got to its conclusion — it's a plausible-sounding post-hoc story wrapped around a judgment made some other way. This is a well-documented property of LLM chain-of-thought in general, not a bug specific to this build, and it's the more dangerous failure mode for a platform whose entire premise is "reasoning, not a tip" — if the reasoning is decorative rather than load-bearing, the compliance posture built on top of it (Section 3) is decorative too.

**The pipeline that makes groundedness checkable rather than aspirational:**
1. Tool-only fact injection (above) — no fact enters the context except through a logged tool call.
2. **Two-stage generation, not one pass.** Stage one produces a structured claims table — each claim explicitly paired with the tool-call ID/field/timestamp it came from. Stage two turns that already-verified table into prose. This matters because it shrinks where hallucination can actually occur: stage two is generating narrative from pre-verified structured data, not reaching back into raw context and inventing connective tissue between facts.
3. **A programmatic grounding gate before publication, not just an offline eval.** Every numeric or factual claim in the final narrative gets checked against the claims table; anything that doesn't match blocks publication. Given the compliance stakes here, this needs to be a hard gate in the pipeline, not a periodic quality check run separately from it.
4. **Chain-of-thought, if the model produces one, gets logged for debugging but is explicitly not treated as proof of grounding.** Because CoT faithfulness isn't guaranteed (see "unfaithful narrative" above), the structured citation schema — not the model's visible reasoning text — is the actual evidentiary artifact. Don't let a convincing-looking reasoning trace substitute for the mechanical check.

**What stays a black box, deliberately, and why that's fine:** the model's internal token-level computation — attention, latent representations — is not something this architecture opens up, and doesn't need to. The promise being made isn't mechanistic interpretability of a neural network, which nobody can actually deliver today; it's a verifiable evidentiary chain from input data to published claim. That's a narrower, more honest, and more achievable bar — and it's also the one that actually satisfies a skeptical analyst or a regulator asking "how did you get this," since neither wants a transformer's internals, they want to know the number is real.

**This is also why the Explanation Layer has to rewrite the claims table, not the free narrative** (constraint already stated above) — rewriting already-grounded, structured claims into lenient language keeps the retail-facing surface inside the same checkable pipeline. Rewriting the *narrative* instead would reopen exactly the black-box risk this section exists to close, one layer downstream of where it was solved.

### Ambiguity & confidence handling

Not every reasoning output is equally certain, and treating all of them as equally confident is itself a failure mode — three distinct problems bundled under "ambiguous or low-confidence," each needing different handling:

1. **Ambiguous query (input-side)** — "is my portfolio too concentrated," "midcap fund better now," without specifying the axis or comparison. Caught at the router, before the expensive Tier 2/3 pipeline runs — either a clarifying question, or the assumed interpretation stated explicitly up front ("interpreting this as sector concentration — say if you meant something else"), never a silent guess run through as if it were unambiguous.
2. **Weak or conflicting underlying data (signal-side)** — a fund with 6 months of history giving a statistically shaky alpha, or a quant primitive disagreeing with the concall signal. Partly covered under cross-domain reasoning above (conflicting signals get presented, not resolved into a verdict), but this happens within a single domain too, not only across domains.
3. **The model's own uncertainty inside a synthesis** — even with solid grounded facts, whether a given connection is load-bearing or tenuous is a judgment call embedded in the narrative.

The mechanism, consistent with everything else in this section: **confidence is a structural field in the claims table, next to the citation — computed, not self-reported.** LLM self-reported confidence is known to be poorly calibrated, so it shouldn't be the model stating a percentage. It should be a deterministic property of the signal — sample size, data age, cross-source agreement — computed the same way alpha/beta is computed, applying the "the LLM never does arithmetic" principle to confidence instead of to numbers.

Three consequences of that:
- **The grounding gate also gates on confidence, not just citation.** A claim can be perfectly grounded — a real, logged number — and still misleading presented without its confidence caveat. Below some threshold, the gate should require the caveat to survive into the output, not just verify the number exists.
- **The Explanation Layer has to preserve the caveat through the rewrite, not smooth it away for readability.** Silently dropping "based on limited history" while simplifying language changes the epistemic status of the claim — arguably worse than dropping the claim outright, and exactly the kind of drift the rewrite-only constraint (Model architecture, above) exists to prevent.
- **When confidence is too low to synthesize anything useful, the answer is to say that, not force a narrative.** Same graceful-degradation instinct as the grounding-gate failure case (Bottlenecks, below) — and it's a compliance point as much as a UX one: a licensed RA overstating confidence in a published one-to-many thesis is real regulatory exposure, not a rough edge.

### Optimizing reasoning — concrete levers

- **Model tiering by query tier**, from above — a small/fast model for Tier 1 translation and narration, the frontier model reserved for Tier 2/3 synthesis, where it's actually earning its cost.
- **Precompute over live compute.** Anything that doesn't depend on the specific query — a stock's concall overview, a fund's alpha/beta as of today — gets computed once when the underlying event happens (new concall, daily close) and read at query time, not recalculated inline. This is a latency and cost lever, and an auditability lever at the same time: the precomputed artifact and its log entry are the same object.
- **Prompt caching on the static grounded context.** The quant-primitive snapshot and concall overview for a given stock/fund don't change between queries about it; caching that context rather than reprocessing it per query is the difference between reasoning cost scaling with query volume and reasoning cost scaling with underlying events — a much smaller number.
- **Match reasoning depth to query complexity**, not a fixed depth for every Tier 2/3 call. A single concall-triggered "why did this move" needs less than "explain my whole portfolio's risk profile across 20 holdings." Spending the same compute on both wastes it on the easy end and probably under-serves the hard end.

### Bottlenecks worth designing around now, not discovering later

1. **Fan-out cost, restated as the top risk.** The compute-once-per-entity principle above is a design decision, not a later optimization — getting it wrong at the start means re-architecting under load, not tuning a parameter after the fact.
2. **Data freshness ceiling.** MF holdings disclosure is monthly (Section 11, open question 2) and price/fundamentals vendor freshness is still an open question (Data sources, above). No amount of reasoning optimization fixes a "dynamic" answer sitting on stale source data — this bounds how real-time the product can honestly claim to be, independent of model choice.
3. **Portfolio-scale context cost.** A user with many holdings, asking a portfolio-wide question, means assembling quant primitives, concall signals, and news for every holding into one grounded context. This needs a scaling plan — a materiality threshold, or hierarchical summarization (per-holding summaries first, portfolio synthesis over summaries rather than raw data) — worked out before it's tested against a user with 40 holdings, not after.
4. **Grounding-gate failure handling.** When the hard gate rejects an output over an unverified claim, what happens at request time matters: an unbounded retry loop is a cost and latency risk, and quietly bypassing the gate under latency pressure defeats the entire mechanism from the section above. The safe default is graceful degradation to the structured data alone, no narrative — not either extreme.
5. **Compliance-aware routing for direct-advice requests.** Retail NL queries will regularly ask for exactly what the RA registration prohibits — "should I sell this now." The query router needs a dedicated branch that recognizes this and redirects to the reasoning framing, not a tier classifier that only sorts by complexity and lets a direct-advice request slip into normal synthesis.
6. **Concall signal reliability feeding everything downstream.** The accent/code-switching/attribution risk flagged in Section 11 isn't only a sourcing question — a noisy concall signal degrades every reasoning output that cites it, worth resolving before this primitive is trusted the way alpha/beta are.
7. **Eval coverage has to track query-type diversity.** A single eval set built around synthesis-style queries won't catch failures specific to fan-out aggregation or screen/filter translation — blind spots show up exactly in the query types the eval set doesn't represent, so coverage needs to expand as query tiers get built, not stay fixed at what the Evals subsection below already describes.

### Evals

Given the compliance stakes, evals split into two categories that need different rigor:

1. **Grounding/hallucination evals** — does every numeric or factual claim in an output trace to an actual logged tool-call result? This is close to a standard RAG-grounding eval and can be largely automated: parse the output's claims, check each against the tool-call log for that generation.
2. **Compliance evals** — does the output ever cross into personalized advice or a direct buy/sell/switch call? This needs a maintained red-team eval set (adversarial retail queries specifically designed to elicit "just tell me what to do") run against every model/prompt change, not a one-time check. Given this is a legal constraint tied to the RA registration, not a style preference, this eval set should probably be reviewed by whoever handles compliance, not just engineering.
3. **Explanation Layer fidelity evals** — does the lenient-terms rewrite preserve the same substantive thesis (same claims, same conclusion) without adding, dropping, or personalizing anything? A drift here is exactly the risk flagged in Section 11's open question 3.

### Auditability

As an RA, published research isn't just a UX artifact — it's a regulated record. Two things this implies architecturally:

- **Every published thesis needs its grounding logged immutably**: the exact quant primitive values, concall extract, and news items the Reasoning Agent used, at the moment of generation, plus the exact output text — as an append-only record, separate from the live/mutable dashboard data. If a thesis is questioned later, the log has to reproduce exactly what the platform knew and said, not an approximation.
- **Versioning on the computation pipelines**: quant primitive formulas and the concall signal-extraction pipeline both need version tags on their output, so a thesis published under pipeline version N can still be explained accurately after the pipeline moves to version N+1.
- **Retention period**: needs a concrete answer, not an assumption — SEBI's RA recordkeeping requirements should be checked directly. (This session's concall research found a 5-year *hosting* requirement on listed *companies* under LODR Reg 46(2)(o) — that's a different rule for a different party. The RA's own recordkeeping duration for its own research records needs its own direct check, not an inference from that figure.)

### Citation

Every claim the Reasoning Agent makes should carry an inline citation to exactly where it came from — "portfolio beta of 1.3, computed [date]," "per Q2 FY26 concall, filed [date]," "per [news source], [date]." This isn't a nice-to-have layered on top; it's the same mechanism that makes the grounding evals and the audit log checkable by a human, not just by another model. The Explanation Layer should preserve citations through the lenient-terms rewrite — possibly presented more lightly (a footnote, or "as of [date]") rather than a full source line — rather than stripping them out for readability, since dropping them would undermine both user trust and the audit trail in the same move.

### Deeper engineering design — companion docs

This section stays at the architecture level on purpose. The detailed technical design that follows from it lives in separate docs rather than growing this one indefinitely:

- [`engineering/data-architecture.md`](./engineering/data-architecture.md) — storage layer, entity graph, entity caching & staleness, and the Phase 1 fixture-based user-holdings approach
- [`engineering/concall-extraction.md`](./engineering/concall-extraction.md) — how a raw transcript becomes the structured concall signal
- [`engineering/reasoning-agent-architecture.md`](./engineering/reasoning-agent-architecture.md) — tool-calling orchestration and the validation/citation/audit gate sequence
- [`engineering/open-risks.md`](./engineering/open-risks.md) — model/agent/data gaps not yet resolved by the design, including two real open ones: multi-turn compliance drift and prompt-injection resistance at content-ingestion points

## 8. MVP scope recommendation

Building all four domains × both personas at once is too much surface for a first version. Two axes matter for sequencing, not one:

- **Domain axis** — which analysis domain ships first
- **Business-model axis** — RA-published research (v1) → RIA personalization → PMS management (future, Section 10)

**Phase 1 — RA-published research + Explanation Layer, for the lower-fund wedge**
- Portfolio drift, concentration, cross-holding correlation (including MF look-through), and MF backward-tracing/manager behavior — the least commoditized slice, hardest to get from Screener/Tickertape/Trendlyne today
- Concall Monitor scoped to fund manager commentary/interviews, feeding Fund Manager Profile — company earnings concalls come in Phase 2 with the Stock domain
- Every thesis published through the Explanation Layer in lenient terms, since the wedge segment's blocker is comprehension as much as access
- Everything scoped to what an RA registration actually permits: one-to-many, no personalization

**Phase 2 — Stock domain**, once the reasoning layer and data pipeline are proven — extends the Concall Monitor to company earnings calls, feeding Sentiment & Trust
**Phase 3 — Industry/macro overlay** (policy, geopolitics) as a context layer feeding into Phase 1/2 reasoning, rather than a standalone domain

## 9. Competitive landscape: what exists today, and the validated gap

Researched two clusters of existing Indian products against our four domains: stock-research platforms (Screener, Tickertape, Trendlyne, Moneycontrol) and portfolio/MF platforms (Value Research, Morningstar India, smallcase, INDmoney, Groww, Zerodha Console/Coin, ET Money, Kuvera). The two research passes were done independently and converged on nearly identical gaps — a good signal these are real, not artifacts of one search.

**By domain — what's already commoditized vs. what's missing everywhere:**

| Domain | Already commoditized (who has it) | Missing everywhere |
|---|---|---|
| Stock | Valuation scorecards (Screener X-Ray, Tickertape Scorecard, Trendlyne DVM/SWOT), analyst-target aggregation (Tickertape, Trendlyne Forecaster) | A synthesized multi-signal thesis in prose — every "explanation" found is a threshold-triggered template ("P/E above historical average"), not reasoning |
| Portfolio | Stock/fund overlap detection, asset/sector mix, XIRR (INDmoney, Groww, Kuvera, Value Research) | Portfolio-level correlation matrix, beta-to-benchmark, VaR on the actual combined portfolio; drift explained against a stated thesis rather than just displayed |
| Mutual Funds | Fund screening/comparison, star ratings, style-box (Morningstar), direct fund-switch calls (ET Money, under RIA) | Continuous automated manager-style-drift/rebalancing-behavior monitoring — Morningstar's Medalist rating is the closest analog and it's a periodic human report, not a live signal |
| Industry | Ad hoc via editorial content (Moneycontrol) | No product does systematic policy/geopolitical impact-on-holdings reasoning |

**Two cross-cutting findings validate the product thesis directly, not just the domain gaps:**

1. **The "reasoning, not a tip" position is genuinely unoccupied.** The market is polarized: Screener/Tickertape/Trendlyne stay strictly descriptive with zero calls; Moneycontrol Pro/Super Pro, smallcase, and ET Money issue explicit buy/sell/switch calls (mostly under RIA or aggregated third-party RA registrations). Nobody sits in between — explained reasoning grounded in deterministic metrics, without a direct call, under a firm's own RA registration. That's exactly this platform's design, confirmed as white space rather than assumed.
2. **No genuine low-literacy explanation layer exists anywhere.** Every "beginner-friendly" surface found across all eight portfolio/MF products is marketing copy or a glossary, not an adaptive layer that translates a specific user's specific numbers into plain language. This directly confirms Section 4's wedge — the comprehension gap for lower-fund retail users is real and currently unaddressed, not already being solved by someone else under a different name.

**What "aggregated and dynamic" concretely means, given this landscape:** almost every individual capability above already exists *somewhere* — overlap detection at INDmoney, style-box at Morningstar, scorecards at Tickertape — but split across products a user has to stitch together themselves, and every one of them is a static dashboard or templated screen. The aggregation is domain coverage (stock + portfolio + MF + industry in one reasoning core, not four separate apps); the "dynamic" part is that it's answerable through natural-language/parametrized query against the Intelligence Layer (Section 6), grounded in deterministic quant primitives, rather than pre-built screens the user has to know to go looking for.

**Competitive signal worth tracking, not dismissing:** INDmoney shipped an MCP server letting users query their real portfolio in plain English via Claude, and Groww has a beta "GR1" AI assistant plus its own MCP integration — both 2026-era moves toward exactly the NL-query territory this platform is aiming at. Neither is grounded in deterministic quant primitives (they route through general-purpose LLMs), neither pairs with a compliance-scoped explanation layer, and both are opt-in/beta rather than the core product — but "having an NL chat over your portfolio" is becoming table stakes faster than expected. Differentiation has to rest on the quant-primitive grounding, the RA-licensed reasoning-not-advice stance, and the literacy-tiered Explanation Layer — not on NL query access alone.

**Confidence note:** several SEBI registration claims above (Value Research Advisor, Morningstar India, Trendlyne, Moneycontrol's in-house research team, Groww's GR1) were not verified against the SEBI intermediary registry directly — flagged by both research passes as needing direct verification before being cited externally. Worth resolving cleanly for this platform's own registration story regardless, since registration transparency is inconsistent industry-wide and is itself a trust differentiator.

## 10. Future scope (explicitly not v1)

- **RIA advisory** — personalized recommendations by goal and risk profile (long-term / liquid-money / passive-income goal types; aggressive vs. conservative return expectations), fee-on-AUM monetization. Layer on top of a proven RA research core once users need more than research access.
- **PMS** — full discretionary management for HNI/UHNI/Family Wealth/Business People Money segments, once compliance infrastructure justifies the overhead.
- Broader instrument coverage — Bonds, REITs, Real Estate, Govt Securities — beyond the Stock/MF core.

## 11. Open questions to resolve before building

1. **Data sourcing** — which data vendor(s) for prices/fundamentals/news for Indian equities & MFs (e.g. NSE/BSE feeds, AMFI for MF data, a news/sentiment API)? Determines cost structure early.
2. **Correlation/look-through computation** — MF holdings disclosure is monthly, not real-time; bounds how "live" cross-fund correlation numbers can actually be.
3. **Explanation Layer vs. personalized advice line — proposed resolution, needs compliance sign-off.** "Lenient terms" must stay a restatement of the same one-to-many thesis, not something that reads as tailored to the individual user, or it risks sliding into RIA territory the RA registration doesn't cover. Section 7's "personalization boundary" now proposes a general rule for this and two related cases (Concall Monitor overviews, factor-exposure computations): a general thesis applied mechanically to a user's own portfolio composition stays research; the line is crossed only when the thesis's substance is tailored to the individual. Still needs sign-off from whoever handles the RA registration before treated as settled.
4. **Explanation Layer mechanism** — templated per-thesis explanations, an LLM rewrite pass, inline tooltips, or a separate onboarding/literacy flow? And how is "understood by the wedge segment" actually tested?
5. **Concall transcript sourcing — resolved direction; the vendor decision is now the only open piece.** SEBI LODR **Regulation 46(2)(o)** requires listed companies to publish the call recording within 24 hours (or before next trading day) and a **written transcript within 5 working days**, hosted for a minimum of 5 years; the same materials get filed to BSE/NSE under Regulation 30. Confidence on the regulation itself is now high — the specific 24-hour/5-working-day/5-year figures are corroborated near-verbatim across multiple independent company IR compliance pages (SBI, KEI Industries, Garware, Ceigall, and others), which is strong evidence even without a direct fetch from sebi.gov.in (blocked in this environment both times it was tried). Sourcing itself turns out to be a **buy, not build** decision: this is a live, multi-vendor market, not something we need our own scraper for — Multibagg ("Concall Monitor" — recordings, transcripts, AI summaries), Earnings Pulse (concall calendar + transcripts + AI summaries, ~₹1,799/year), AlphaStreet India (institutional-grade, claims an API), Trendlyne, and StockAdda all already do transcript aggregation with AI summarization. Self-built speech-to-text stays a fallback only, for the rare company that's late or non-compliant on the filing. **Remaining work is a vendor bake-off** — coverage breadth, data freshness, licensing terms for redistribution through our own reasoning layer, and price — not a build decision.
6. **Review-trigger threshold for the Concall Monitor** — what change in the language-signal score or guidance actually warrants surfacing "this needs a look" rather than adding noise to every subscriber's feed after every call? Needs a defined, general (not per-user) threshold before this ships as a standing signal rather than a one-off overview. Now one instance of the broader Review Trigger framework (Section 7) — the same threshold-definition problem applies to its performance, concentration, and macro-factor trigger categories too.
7. **Thematic taxonomy ownership** — unlike sector (GICS or equivalent), there's no external standard for "theme." Someone has to define and maintain what counts as, say, a "China+1" or "rate-sensitive" theme — an editorial choice, not a computation. Needs an owner, a maintenance cadence, and possibly its own disclosure before thematic risk (Section 5, Portfolio domain) ships as a screenable criterion.

## 12. Next steps

Once data sourcing is confirmed and the Explanation Layer's compliance boundary (open question 3) has a concrete answer, this doc has enough to break Phase 1 into: (a) quant primitives service (drift/concentration/correlation/alpha/beta/VaR calculators), (b) data ingestion for prices + AMFI MF holdings, (c) RA reasoning agent grounded on (a)+(b), (d) Explanation Layer translating (c) for retail, (e) dashboard/list surface for retail and analyst views.

**Coding starts with fixture-based user holdings, not a live broker/demat integration.** Real holdings data is deferred to a later phase; the first build exercises the entity graph, quant primitives, and reasoning pipeline against realistic mock holdings shaped exactly like a real broker feed would arrive, so swapping in live data later is a data-source change, not a schema change. Detail in [`engineering/data-architecture.md`](./engineering/data-architecture.md#phase-1-build-note-fixture-based-user-holdings).

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

Holding the RA license in-house doesn't change what the output looks like — the answer is the same either way, constrained by SEBI's RA rules (one-to-many, no personalized advice). What it changes is *who* is legally allowed to produce and publish that answer: the firm itself, rather than needing to broker third-party analysts. RIA and PMS are explicitly **not** v1 — see Section 8.

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
- Sentiment & trust
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
- Fund manager profile
- Fund monitoring: how actively a manager rebalances in response to market moves, and what effect that has on the fund

## 6. System Architecture

```
                    ┌─────────────────────────────┐
                    │          Data Layer          │
                    │  Prices · News · Product/     │
                    │  company fundamentals ·       │
                    │  Global events · Supply chains │
                    └───────────────┬──────────────┘
                                    │
   ┌───────────────────┐           │
   │  User Query Layer   │──────────┤
   │  Retail: NL query    │          │
   │  Analyst: params     │          ▼
   │  + Holdings/portfolio│  ┌───────────────────────┐
   └───────────────────┘   │   Intelligence Layer     │
                            │  ┌─────────────────────┐ │
   ┌───────────────────┐   │  │ Quant primitives     │ │
   │   MF-specific        │──▶│ (alpha, beta, VaR,   │ │
   │   context: portfolio │   │  correlation, drift) │ │
   │   changes, past perf,│   └──────────┬───────────┘ │
   │   manager review,    │              │             │
   │   rebalance frequency│              ▼             │
   └───────────────────┘   │  ┌─────────────────────┐ │
                            │  │ Reasoning agent       │ │
                            │  │ (RA thesis, grounded  │ │
                            │  │  on quant + data)     │ │
                            │  └──────────┬───────────┘ │
                            └─────────────┼─────────────┘
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

**Key architectural point from the original sketch, worth keeping explicit:** the Intelligence Layer is two-tiered, not one LLM call. A **quant primitives layer** computes alpha, beta, VaR, correlation, and drift deterministically from data — these are numbers, not model output, and must be auditable. A **reasoning layer** (agentic, LLM-driven) sits on top, grounded on those computed numbers plus news/events/policy context, and produces the narrative. This split matters for trust: an analyst (and a regulator) will accept a hallucination-prone LLM explaining *why* a computed VaR is high, but not an LLM inventing the VaR itself.

**New from this round: the Explanation Layer is a first-class component, not a UX nice-to-have.** It sits between the reasoning agent's output and the retail surface, translating the same one-to-many RA thesis into lenient terms. Analysts see the full reasoning chain directly; retail users see the translated version. This is the layer that actually closes the wedge gap in Section 4 — the RA solves access, the Explanation Layer solves comprehension.

## 7. MVP scope recommendation

Building all four domains × both personas at once is too much surface for a first version. Two axes matter for sequencing, not one:

- **Domain axis** — which analysis domain ships first
- **Business-model axis** — RA-published research (v1) → RIA personalization → PMS management (future, Section 8)

**Phase 1 — RA-published research + Explanation Layer, for the lower-fund wedge**
- Portfolio drift, concentration, cross-holding correlation (including MF look-through), and MF backward-tracing/manager behavior — the least commoditized slice, hardest to get from Screener/Tickertape/Trendlyne today
- Every thesis published through the Explanation Layer in lenient terms, since the wedge segment's blocker is comprehension as much as access
- Everything scoped to what an RA registration actually permits: one-to-many, no personalization

**Phase 2 — Stock domain**, once the reasoning layer and data pipeline are proven
**Phase 3 — Industry/macro overlay** (policy, geopolitics) as a context layer feeding into Phase 1/2 reasoning, rather than a standalone domain

## 8. Future scope (explicitly not v1)

- **RIA advisory** — personalized recommendations by goal and risk profile (long-term / liquid-money / passive-income goal types; aggressive vs. conservative return expectations), fee-on-AUM monetization. Layer on top of a proven RA research core once users need more than research access.
- **PMS** — full discretionary management for HNI/UHNI/Family Wealth/Business People Money segments, once compliance infrastructure justifies the overhead.
- Broader instrument coverage — Bonds, REITs, Real Estate, Govt Securities — beyond the Stock/MF core.

## 9. Open questions to resolve before building

1. **Data sourcing** — which data vendor(s) for prices/fundamentals/news for Indian equities & MFs (e.g. NSE/BSE feeds, AMFI for MF data, a news/sentiment API)? Determines cost structure early.
2. **Correlation/look-through computation** — MF holdings disclosure is monthly, not real-time; bounds how "live" cross-fund correlation numbers can actually be.
3. **Explanation Layer vs. personalized advice line** — "lenient terms" must stay a restatement of the same one-to-many thesis, not something that reads as tailored to the individual user, or it risks sliding into RIA territory the RA registration doesn't cover. Needs a concrete design rule, not just an intention, before this layer is built.
4. **Explanation Layer mechanism** — templated per-thesis explanations, an LLM rewrite pass, inline tooltips, or a separate onboarding/literacy flow? And how is "understood by the wedge segment" actually tested?

## 10. Next steps

Once data sourcing is confirmed and the Explanation Layer's compliance boundary (open question 3) has a concrete answer, this doc has enough to break Phase 1 into: (a) quant primitives service (drift/concentration/correlation/alpha/beta/VaR calculators), (b) data ingestion for prices + AMFI MF holdings, (c) RA reasoning agent grounded on (a)+(b), (d) Explanation Layer translating (c) for retail, (e) dashboard/list surface for retail and analyst views.

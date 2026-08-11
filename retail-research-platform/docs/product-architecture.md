# Retail Research Platform — Product & Architecture Doc

## 1. Vision

A dynamic research platform that answers *"why does this stock/fund/portfolio look the way it does, right now, given what's happening"* — for both retail investors and research analysts, off one shared reasoning core.

The single most important design constraint, carried over directly from the original sketch: the system explains and reasons about a position **according to a thesis** — it does **not** issue direct buy/sell calls. This is not a hedge, it's the product. It's what differentiates the platform from a tip service, keeps it on the right side of India's SEBI Research Analyst / Investment Adviser regulations (a platform that "suggests directly" needs an RIA/RA license and materially more compliance overhead; a platform that surfaces reasoning and lets the user or their advisor decide does not), and it's what makes the analyst persona want to use the same core a retail user does — analysts want the reasoning chain, not a verdict.

## 2. Personas, one core

| | Retail investor | Research analyst |
|---|---|---|
| Query style | Natural language ("is my portfolio too concentrated in IT?") | Structured/parametrized ("midcap fund, 3Y alpha > 1, manager tenure > 5Y") |
| Primary surface | Dashboard + plain-language reasoning | Lists/screens + exportable reasoning, raw params |
| Trust need | Needs the "why," in plain terms, tied to their own holdings | Needs the numbers underneath the "why," auditable |
| Depth | Curated, guided (system may need to educate on unfamiliar concepts, e.g. forward growth) | Self-directed, wants filtering control |

Both personas hit the same **Intelligence Layer**. What differs is the query interface in and the presentation layer out — not the underlying computation or reasoning. Build the core once; retail is a simplified lens over the analyst surface, not a separate product.

## 3. Analysis Domains

Four domains, each decomposed into concrete sub-analyses:

**Stock**
- Valuation
- Buy range
- Forward growth *(this one needs in-product education for users without a prior model of what "forward growth" means — don't assume the concept is understood)*
- Sentiment & trust
- Analyst ratings (aggregation, not the platform's own rating)

**Portfolio**
- Drift from target asset allocation
- Concentration risk (position/sector/theme)
- Correlation — across stocks within a portfolio, across industries, and across mutual fund holdings (i.e. detecting hidden concentration when multiple funds hold the same underlying names)

**Industry**
- Impact of government policy
- Geopolitical impact

**Mutual Funds**
- Backward-traced portfolio performance (what actually drove the return)
- Fund manager style bets
- Portfolio financial parameters — alpha, beta, VaR
- Fund manager profile
- Fund monitoring: how actively a manager rebalances in response to market moves, and what effect that has on the fund

## 4. System Architecture

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
                            │  │ (grounded on quant    │ │
                            │  │  output + data layer) │ │
                            │  └──────────┬───────────┘ │
                            └─────────────┼─────────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    ▼                     ▼                     ▼
               Dashboard               Lists              Reasoning / Fund view
          (portfolio health,     (screened stocks/     ("according to this
           at-a-glance)           funds, ranked)         thesis" — not a
                                                          direct suggestion)
```

**Key architectural point from the original sketch, worth keeping explicit:** the Intelligence Layer is two-tiered, not one LLM call. A **quant primitives layer** computes alpha, beta, VaR, correlation, and drift deterministically from data — these are numbers, not model output, and must be auditable. A **reasoning layer** (agentic, LLM-driven) sits on top, grounded on those computed numbers plus news/events/policy context, and produces the narrative. This split matters for trust: an analyst (and a regulator) will accept a hallucination-prone LLM explaining *why* a computed VaR is high, but not an LLM inventing the VaR itself.

## 5. MVP scope recommendation

Building all four domains × both personas at once is too much surface for a first version. Recommend narrowing the first slice along the axis that's most differentiated and most reusable across personas:

**Phase 1 — Portfolio + Mutual Fund analysis** (skip standalone single-stock valuation/buy-range for now — that segment is already well-served by Screener, Tickertape, Trendlyne, and a v1 there wins nothing on differentiation)
- Portfolio drift, concentration, cross-holding correlation (including MF look-through)
- MF backward-tracing and fund manager behavior analysis
- This is the least commoditized piece in both notes and the one where "reasoning, not a tip" is most defensible as a product wedge

**Phase 2 — Stock domain**, once the reasoning layer and data pipeline are proven
**Phase 3 — Industry/macro overlay** (policy, geopolitics) as a context layer feeding into Phase 1/2 reasoning, rather than a standalone domain

## 6. Open questions to resolve before building

1. **Data sourcing** — which data vendor(s) for prices/fundamentals/news for Indian equities & MFs (e.g. NSE/BSE feeds, AMFI for MF data, a news/sentiment API)? This determines cost structure early.
2. **Regulatory posture** — confirm the "reasoning not suggestion" framing is sufficient to stay outside SEBI RA/RIA registration, or whether registration is the intended path anyway (changes what the reasoning layer is allowed to say).
3. **Correlation/look-through computation** — MF holdings disclosure is monthly, not real-time; this bounds how "live" the cross-fund correlation numbers can actually be.
4. **Retail education UX** — for concepts like forward growth where the user may have no prior model, is that inline (tooltips/explainers) or a separate onboarding flow?

## 7. Next steps

Once data sourcing and the regulatory posture are confirmed, this doc has enough to break Phase 1 into: (a) quant primitives service (drift/concentration/correlation/alpha/beta/VaR calculators), (b) data ingestion for prices + AMFI MF holdings, (c) reasoning agent grounded on (a)+(b), (d) dashboard/list surface for retail and analyst views.

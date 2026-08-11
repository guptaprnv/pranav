# Quant Primitives Service

Deterministic financial computations for the Retail Research Platform's Intelligence Layer — alpha, beta, VaR, correlation, drift, concentration. These are the "quant primitives" described in [`docs/product-architecture.md`](../docs/product-architecture.md) (Section 6/7): auditable numbers a Reasoning Agent grounds its narrative in, never something an LLM computes or invents.

## Why this service has no LLM in it

By design. The whole point of the two-tier Intelligence Layer (product-architecture.md, "why two tiers, not one model call") is that these numbers come from real math, not a model's guess — see [`docs/engineering/reasoning-agent-architecture.md`](../docs/engineering/reasoning-agent-architecture.md) for how a future Reasoning Agent is meant to consume this service's output.

## What's here

- `src/quant_primitives/models.py` — `PrimitiveResult`, the versioned/cited output wrapper every primitive returns (`value`, `computed_at`, `pipeline_version`, `input_as_of`, `confidence`) — the schema [`docs/engineering/data-architecture.md`](../docs/engineering/data-architecture.md) calls for at the storage layer.
- `src/quant_primitives/confidence.py` — confidence computed structurally from sample size, never self-reported by a model (see `docs/engineering/open-risks.md` and the main doc's "Ambiguity & confidence handling").
- `src/quant_primitives/primitives/` — the actual formulas: `returns.py`, `risk.py` (alpha/beta/VaR), `portfolio.py` (correlation/drift/concentration).
- `src/quant_primitives/fixtures/` — synthetic, seeded price/holdings data standing in for a real vendor and a real broker/demat connection. See the **Fixture data** section below — this is temporary by design, not a shortcut that got left in.
- `src/quant_primitives/api/` — a thin FastAPI layer exposing each primitive as a Tier-0-style direct lookup (main doc, "Query handling & aggregation").

## Fixture data

Per `docs/engineering/data-architecture.md`'s Phase 1 build note: this service currently reads prices, entities, and a sample user's holdings from `src/quant_primitives/fixtures/generate.py` — a seeded synthetic random walk, not real market data, and a hardcoded holdings dict, not a live broker/demat feed. Both are still genuinely open sourcing decisions (main doc, Section 7, Data sources).

`fixtures_store.py` is the only place that knows about fixtures — it's the seam where a real price/fundamentals vendor and a real holdings integration get swapped in later. None of the primitive functions in `primitives/` know or care where their input came from; they take `pandas` Series and dicts, which is what makes the eventual swap a data-source change, not a rewrite.

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# run the tests
pytest

# run the API
uvicorn quant_primitives.api.main:app --reload
# then, e.g.: curl localhost:8000/primitives/entities
```

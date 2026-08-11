# Retail Research Platform

Dynamic research platform for retail investors and research analysts, built around a shared reasoning core over stock, portfolio, industry, and mutual fund analysis.

See [`docs/product-architecture.md`](docs/product-architecture.md) for the product vision, personas, analysis domains, system architecture, and MVP scope.

Detailed engineering design lives in `docs/engineering/`:
- [`data-architecture.md`](docs/engineering/data-architecture.md) — storage, entity graph, entity caching & staleness
- [`concall-extraction.md`](docs/engineering/concall-extraction.md) — transcript-to-signal extraction pipeline
- [`reasoning-agent-architecture.md`](docs/engineering/reasoning-agent-architecture.md) — tool-calling orchestration and the validation/citation/audit gate sequence
- [`open-risks.md`](docs/engineering/open-risks.md) — unresolved model/agent/data gaps

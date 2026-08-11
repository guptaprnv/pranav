# Reasoning Agent: Orchestration & Validation

Companion to [`product-architecture.md`](../product-architecture.md), Section 7. How the Reasoning Agent actually executes a Tier 2/3 query end to end: from deciding what to look at, through generating an answer, to the checks that run before anything publishes.

## Tool-Calling Orchestration

**This is a constrained plan → execute → merge → generate pipeline, not a freeform agentic loop.** A ReAct-style loop — call a tool, look at the result, decide the next call, repeat until the model decides it's done — is slower, and more importantly moves the black-box risk earlier in the pipeline. The grounding mechanism (main doc, Section 7) protects against the model inventing facts it didn't retrieve, but says nothing about whether it retrieved the *right* facts. Left to improvisation, tool selection can produce an answer that's fully grounded in what it looked at and still wrong because it didn't look at everything relevant.

**A fourth failure mode, alongside hallucination, unfaithful narrative, and unearned relationships: selective or incomplete evidence gathering.** The model retrieves real, correctly-cited facts, but misses that the user also holds this stock through two other funds, or skips the concall signal entirely. Grounded, not hallucinated — still misleading. The grounding gate doesn't catch this, because everything it checks against is technically true.

**Defense: make planning mechanical wherever possible.** For known query shapes (most of them, per the query-tiering work in the main doc), the set of tools to call can be derived directly from the entity graph rather than left to model judgment — "user asked about Company X" expands programmatically into "direct holding? which funds hold it via look-through? concall history? factor tags?" via the graph's edges (see [`data-architecture.md`](./data-architecture.md), Entity Graph). A rule-based planner working off the graph doesn't forget a look-through relationship the way an improvising model might. The LLM only helps plan for genuinely novel query shapes that don't fit an enumerated pattern — and that's exactly where "the plan itself needs its own grounding check" (main doc, Cross-domain query reasoning) applies: validate the plan against the entity graph before executing it.

**Independent tool calls execute in parallel, batched from the plan.** Beyond the latency win already covered under Optimizing reasoning, a batch-plan-then-parallel-execute pattern is easier to audit than a sequential loop — the full set of calls is known up front and logged as one unit.

**Results need an explicit merge step before the claims-table stage** — dedup (a stock's data retrieved via both a direct holding and a fund look-through shouldn't produce two redundant claims), conflict surfacing (feeds the "present, don't resolve" principle), and organizing by entity so the narrative stage gets structured input.

**Fan-out has to be bounded at planning time, not discovered mid-execution.** For a large portfolio, the plan decides up front to use per-holding summaries rather than full detail (the hierarchical-summarization approach from the Bottlenecks list), not something improvised once context is already too large.

**Every layer of the pipeline needs its own graceful-degradation behavior, not just the final gate.** If one tool call fails (timeout, missing data for one entity), the right move is proceeding with an explicit "data unavailable for X" note — not failing the whole query, and not silently treating the gap as "nothing to report," which reads very differently from "couldn't retrieve." A solid gate at the end doesn't help if a silent gap earlier already shaped what the narrative had to work with.

**Named component: the Query Orchestrator**, sitting between the Router and the Reasoning Agent's generation stage. Its job: take the router's tier classification, expand it into a concrete tool-call plan (mechanical where the graph allows it), execute in parallel with failure handling, merge results. Its execution trace *is* the tool-call log from Auditability — not a separate thing to build, the same artifact viewed from the orchestration side.

## Validation, Citation & Audit Layer

**This is a sequence of composable gates, not one monolithic check — and the order matters.**

1. **Grounding Gate** — runs on the claims table (stage-one output). Checks citation completeness (every claim has one) and citation accuracy (it resolves to something real) — really one gate, not two. Hard block on failure.
2. **Confidence Gate** — also runs on the claims table, since confidence is a per-claim property established at extraction time. Below-threshold claims get their caveat injected; escalates to a block if the caveat can't be verified as attached.
3. **Compliance Gate** — runs on the narrative (stage-two output), not the claims table, because personalized-advice risk lives in phrasing, not in which facts got selected. Hard block on failure, routed to human review rather than auto-corrected — an automated "fix" for a compliance violation risks introducing a different one.
4. **Fidelity Gate** — for Explanation Layer output specifically, verifies the retail rewrite didn't add or drop claims relative to the already-passed claims table.

**Failures route back to the earliest stage that can fix them, not a full restart.** A compliance failure in phrasing doesn't mean the grounding work was wrong — only narrative generation needs to retry with the same verified claims table.

**Retries are capped, and the fallback is decided now, not discovered under load.** After a bounded number of failed narrative attempts (1–2), the safe fallback is serving the verified claims table directly — lightly formatted, no narrative wrapper — rather than blocking the user or forcing through a narrative that hasn't passed. The claims table is already grounded and confidence-tagged by that point, so it's a legitimate answer on its own.

**This layer's pass/fail decisions are the audit log, not a separate logging step.** Ties directly to RA recordkeeping — a regulator asking "why was this published" needs to see that it passed specific checks, not just the final text.

**Compliance-gate failures need an actual review queue** — an SLA, a reviewer interface, its own logging of who decided what and when. A real engineering surface, not an abstract "escalate to compliance."

**Citation verification (backend) and citation rendering (frontend) are distinct.** Same underlying verified citation data, two presentation paths — full tool-call-ID-level detail for analysts, a lighter footnote for the Explanation Layer's retail view.

**Validation rigor scales with query tier.** Tier 0 (direct lookup) skips this layer entirely — there's no generation to validate. Tier 1 needs a lighter check (translation fidelity plus grounding on any narration). Only Tier 2/3 need the full gate sequence.

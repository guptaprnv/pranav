# Concall Transcript Fact Extraction

Companion to [`product-architecture.md`](../product-architecture.md). Detailed design for turning a raw concall transcript into the structured "concall language signal" quant primitive referenced throughout the main doc (Section 5, Sentiment & Trust; Section 6, Concall Monitor; Section 7).

## Extraction is stage-one-claims-table, applied to one document type

Extraction is not a new mechanism — it reuses the two-stage grounded generation pattern already established for the Reasoning Agent (`product-architecture.md`, Section 7, Grounded vs. black-box reasoning), scoped to a transcript instead of a full query. Don't let the extraction model freely summarize a transcript into prose. Extract a fixed, structured set of fields — revenue/margin guidance given, capex plans mentioned, hedging/uncertainty markers in Q&A — each carrying an exact quote or excerpt from the transcript it came from, the same way every other claim in the architecture carries a citation back to its source.

## Grounding check here is easier than the general case

For a computed number like alpha, "is this grounded" means checking against a tool-call log. For extraction, the source of truth is the raw transcript text itself — verifying an extracted claim can be close to a mechanical quote/fuzzy-match check (does this excerpt actually appear in the transcript) rather than another LLM pass. Cheaper and more reliable than narrative grounding.

## Quarter-over-quarter comparison needs stored prior-quarter output

"Reiterate vs. revise guidance" needs the prior quarter's extraction stored and retrievable via the entity graph (Company X, prior quarter) — see [`data-architecture.md`](./data-architecture.md) — not just this quarter's transcript, making concall extraction inherently a diff task across time. Two distinct outputs, not one:

- **Guidance-number comparison**: mechanical once both quarters are structured (15–17% vs. 15–17% is a reiteration; vs. 12–14% is a revision down).
- **Hedging/language-tone read**: qualitative per-quarter, trended rather than diffed like a number.

## Absence of a claim is itself a signal

If a company declines to give guidance this quarter, that's arguably a stronger signal than routine reiteration. The schema needs an explicit "no guidance given" state, not a missing field that silently reads as "unchanged."

## Speaker attribution depends on vendor transcript format

Hedging language from the CEO under direct analyst questioning is a different signal than the same phrase in a scripted opening statement — but only usable if the transcript preserves speaker turns. This is a new evaluation criterion for the still-open vendor bake-off (`product-architecture.md`, Section 11, open question 5), not something extraction can fix after the fact if the source transcript is an undifferentiated wall of text.

## Untrusted content handling

Transcript content is external, third-party text and must be treated strictly as data, never as instructions, in the extraction prompt — the same trusted/untrusted content separation any system ingesting external text needs, applied at the point where it matters most here, since this is the first place raw external text enters the pipeline. See [`open-risks.md`](./open-risks.md) for the broader version of this concern.

## Scheduling

Runs as a batch job on the Concall Monitor's schedule (`product-architecture.md`, Section 6) — once when a transcript becomes available, not live at query time, consistent with "precompute over live compute" (Section 7, Optimizing reasoning). Output is stored as a versioned computed primitive (see `data-architecture.md`, Storage) and the Reasoning Agent reads that structured output later, rather than re-reading the raw transcript per query — keeping context smaller and keeping the extraction-grounding check localized to one well-scoped step.

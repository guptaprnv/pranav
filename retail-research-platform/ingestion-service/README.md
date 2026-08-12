# MF Ingestion Service

Holdings ingestion and AMFI entity resolution — step 1 of the MVP build order.
MF-only, free public data only, no licensed feeds.

## The decisions register is the point

`src/mf_ingestion/decisions.py` mirrors the repo-root [`decisions.md`](../decisions.md).
Every judgement value is registered there and referenced by ID. Unresolved decisions
have **no value**, and reading one raises `UnresolvedDecisionError` with a pointer to
decisions.md.

This is what makes the build brief's hard rule mechanical instead of aspirational:
"the agent quietly picked a threshold" becomes a loud crash, not a silent correctness
bug that surfaces in someone's findings months later.

```python
>>> from mf_ingestion import decisions
>>> decisions.get(decisions.ING_1_AUTO_ACCEPT_SCORE)
UnresolvedDecisionError: decision ING-1 is UNRESOLVED and has no value.
  question: Above what match score is a parsed scheme name auto-bound ...
  fix: resolve ING-1 in decisions.md, then set it here.
  do NOT pick a default to get past this error.
```

Tests exercise logic by *injecting* values (`decisions.with_values({...})`), which
deliberately does not mark anything resolved — so proving the machinery works can never
be mistaken for having decided the numbers.

## What works now

| Component | State |
|---|---|
| AMFI NAVAll parser | **Done.** Stateful line parser, category/AMC carry-down, `N.A.` → `None`, malformed rows surfaced in `unparsed_lines` rather than dropped |
| Plan / option detection | **Done.** Conservative — returns `UNKNOWN` rather than guessing, since plan variant drives the largest leak |
| Scheme master client | **Done, untestable here.** Real `httpx` fetch against amfiindia.com, plus `load_scheme_master()` for a downloaded snapshot |
| Entity resolution | **Machinery done, blocked on ING-1/2/3/4.** `resolve()` raises until thresholds are decided |
| Confirmation gate | **Done.** `ParsedPortfolio.is_ready_to_compute()` requires both user confirmation and full resolution |
| Screenshot extraction | **Not built** — needs the hand-labelled corpus first |
| CAS PDF extraction | **Not built** — needs sample CAMS/KFintech files (redacted is fine) |

32 tests, all passing.

## AMFI network access

`amfiindia.com` is blocked by the egress policy of the sandbox this was developed in
(403 at the proxy on CONNECT). That is an environment restriction, not a property of the
data — the feed is free and public, and `fetch_scheme_master()` works from any
unrestricted host such as your own server.

For offline work, download the snapshot and use the file path:

```python
from mf_ingestion.amfi.client import load_scheme_master
master = load_scheme_master("navall.txt")
```

`load_scheme_master` takes `fetched_at` from the file's mtime, not today's date, so a
stale snapshot can't masquerade as fresh — as-of dating survives the offline path.

## Uploads are never persisted

`holdings/sources.py` is the only module that touches raw upload bytes. No implementation
may write them to disk or object storage — screenshots and CAS files contain account
numbers and personal details. Extraction is in-memory, and the bytes are discarded.

## What's needed to finish this layer

1. **ING-1 … ING-4** resolved in `decisions.md`. Note ING-3 (the metric) has to be settled
   before ING-1/ING-2 (the thresholds) mean anything — different metrics give materially
   different scores for the same truncated name.
2. **A real AMFI snapshot** committed as a fixture, or egress access.
3. **Sample CAS PDFs** (redacted) to write that parser against.
4. **The ~200-screenshot eval corpus** — see the PII note in `decisions.md`; a committed
   corpus of real screenshots contradicts the never-persist rule and needs a redaction or
   synthetic-regeneration decision first.

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

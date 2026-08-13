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
| Monthly disclosure parser | **Done.** CSV + Excel, header-alias column mapping, fails loudly on unidentifiable columns rather than falling back to column order |
| Look-through aggregation | **Done.** Fund weights × disclosed holdings → per-ISIN exposure, with uncovered weight reported |
| Screenshot extraction | **Not built** — needs the hand-labelled corpus first |
| CAS PDF extraction | **Not built** — needs sample CAMS/KFintech files (redacted is fine) |

58 tests, all passing.

## Monthly portfolio disclosures

This is the half of MF ingestion that the leak engine actually needs: the scheme
master says which funds exist, disclosures say what each fund *holds*. Look-through
concentration and fund overlap are both computed from this.

Column identification is by header alias, not position — AMC wording varies
("% to Net Assets" / "% to NAV" / "% of Net Assets") and footnote markers are common.
If a required column can't be identified, parsing **fails** with the headers it saw,
rather than guessing by position. Adding a new AMC's wording is an edit to `_ALIASES`
plus a test, not new parsing logic.

**One parsing rule worth reviewing**, since it's the closest thing here to a judgement
call: subtotal rows (`Sub Total`, `Total`, `Grand Total`) carry both a name and a
percentage, so a naive parser reads them as holdings and every look-through exposure
roughly doubles. `is_structural_row()` excludes them, requiring **two** signals — the
name matches a total-ish pattern *and* the row has no ISIN. Name alone would misclassify
a genuine holding in a company whose name contains "total" (TotalEnergies is a real
listed company); ISIN alone would misclassify legitimately unlisted holdings. Excluded
rows go to `unmapped_rows` rather than being dropped silently.

## Look-through

`lookthrough.compute_look_through()` returns an exposure table. It does **not** decide
what counts as concentrated — that's CONC-2/CONC-3, undecided — so nothing it returns
is labelled a finding.

Two limits, both traceable to `decisions.md`:
- **ISIN grain, not company.** Rolling multiple ISINs up to one company (ordinary vs DVR
  shares) is CONC-1 and undecided. ISIN-grain output is a floor on true company exposure,
  never an overstatement.
- **Holdings without an ISIN are excluded and reported, not name-matched.** Matching
  "Reliance Industries Ltd" to "Reliance Inds." across two AMCs' files is the ING-3
  fuzzy-matching problem; guessing it would silently merge or split companies inside the
  headline number.

`LookThroughResult.unresolved_weight` carries the share of the portfolio that couldn't be
looked through — funds with no disclosure loaded, plus holdings with no ISIN. A
concentration figure computed over 60% of a portfolio but presented as covering 100% is
misleading in exactly the way the citation rule exists to prevent.

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

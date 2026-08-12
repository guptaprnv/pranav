"""Holdings sources behind a single interface.

Per the brief: "Design the holdings model behind an interface so Account
Aggregator can slot in later without reshaping the schema." Every source --
screenshot, CAS PDF, and eventually AA -- returns the same `RawHolding` list,
so adding AA later is a new implementation of this protocol and nothing
downstream changes.

**Uploads are never persisted.** `extract` takes bytes in memory and returns
parsed holdings; no implementation may write the source bytes to disk or object
storage. Screenshots and CAS files contain account numbers and personal
details. This is a hard rule from the brief, restated here because this module
is the only place raw uploads exist.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol

from ..models import ParsedPortfolio, RawHolding, ResolvedHolding, ResolutionStatus


class HoldingsSource(Protocol):
    """Anything that can produce a user's holdings.

    Implementations must not retain, log, or persist the input bytes.
    """

    name: str

    def extract(self, payload: bytes) -> list[RawHolding]:
        ...


class ScreenshotSource:
    """Portfolio screenshot upload.

    NOT IMPLEMENTED -- deliberately. A real implementation needs an OCR/vision
    step tuned against the ~200 hand-labelled real screenshots the brief
    specifies as the eval corpus. Writing a plausible-looking extractor before
    that corpus exists would produce something untestable and probably wrong in
    exactly the ways the corpus is meant to catch (truncated scheme names,
    mis-read digits).

    Blocked on: the eval corpus, and ING-1..4 for the resolution step that
    follows extraction.
    """

    name = "screenshot"

    def extract(self, payload: bytes) -> list[RawHolding]:
        raise NotImplementedError(
            "ScreenshotSource needs the hand-labelled screenshot corpus before "
            "an extractor can be written and measured. See decisions.md, "
            "'Open dependency -- eval corpus'."
        )


class CASPdfSource:
    """CAMS / KFintech Consolidated Account Statement PDF.

    NOT IMPLEMENTED -- deliberately. CAS PDFs are password-protected and their
    layout differs between CAMS and KFintech. Writing a parser without real
    sample files means guessing at the table structure, which the brief's
    no-silent-fallbacks rule rules out.

    Blocked on: sample CAS PDFs (redacted is fine -- structure is what matters,
    not the values).
    """

    name = "cas_pdf"

    def extract(self, payload: bytes) -> list[RawHolding]:
        raise NotImplementedError(
            "CASPdfSource needs sample CAMS/KFintech CAS files to parse against. "
            "Redacted samples are sufficient."
        )


def to_unconfirmed_portfolio(
    holdings: list[RawHolding],
    as_of: date,
) -> ParsedPortfolio:
    """Wrap freshly extracted holdings as an unconfirmed portfolio.

    Holdings arrive unresolved; resolution happens separately. `confirmed` is
    False, and the brief makes showing this table back to the user before any
    computation non-negotiable.
    """
    return ParsedPortfolio(
        holdings=[
            ResolvedHolding(
                raw=holding,
                status=ResolutionStatus.NEEDS_USER_INPUT,
                reason="not yet resolved against the scheme master",
            )
            for holding in holdings
        ],
        as_of=as_of,
        confirmed=False,
    )

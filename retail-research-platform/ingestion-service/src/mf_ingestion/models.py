"""Canonical models -- the scheme/ISIN spine the brief calls the thing
"nothing works without".

Two rules from the brief are enforced structurally here rather than left to
caller discipline:

1. **As-of dating on every fact.** NAV carries `nav_date`; holdings carry
   `as_of`. Nothing in this layer produces an undated fact, so no downstream
   consumer can accidentally imply two different as-of dates are simultaneous.
2. **No silent fallbacks.** Where a value cannot be determined (plan variant
   truncated away, scheme name unresolvable), the model carries an explicit
   UNKNOWN / NEEDS_USER_INPUT state. There is no "probably Growth" default.
"""
from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class Plan(str, Enum):
    """Direct vs Regular. Per the brief this distinction determines the largest
    single leak (fee drag), so UNKNOWN is a first-class state -- guessing it
    would fabricate or erase that finding.
    """

    DIRECT = "direct"
    REGULAR = "regular"
    UNKNOWN = "unknown"


class Option(str, Enum):
    GROWTH = "growth"
    IDCW = "idcw"  # income distribution cum capital withdrawal (formerly dividend)
    UNKNOWN = "unknown"


class Scheme(BaseModel):
    """One row of the AMFI scheme master."""

    amfi_code: str
    name: str
    amc: str
    category: str
    plan: Plan
    option: Option
    isin_growth: str | None = None
    isin_reinvestment: str | None = None
    nav: float | None = None
    nav_date: date | None = None


class SchemeMaster(BaseModel):
    """A parsed AMFI NAVAll snapshot, plus everything that did not parse.

    `unparsed_lines` is not decoration: the brief forbids silent fallbacks, so
    lines the parser did not recognise are surfaced rather than dropped. A
    caller that ignores them is making that choice explicitly.
    """

    schemes: list[Scheme]
    source_url: str
    fetched_at: date
    unparsed_lines: list[str] = Field(default_factory=list)

    def by_code(self) -> dict[str, Scheme]:
        return {scheme.amfi_code: scheme for scheme in self.schemes}


class RawHolding(BaseModel):
    """A holding as extracted from a user upload, before entity resolution.

    `scheme_name_raw` is exactly what was read off the screenshot or CAS --
    possibly truncated, possibly misspelled. Resolution to an AMFI code happens
    separately so the raw string survives for audit and for re-resolution when
    the matching rules change.

    Quantity is optional by design: per the brief, scheme identity plus
    approximate weight is enough for overlap, concentration, redundancy and fee
    drag, which dodges most OCR risk on numbers.
    """

    scheme_name_raw: str
    value: float | None = None
    units: float | None = None
    entry_date: date | None = None


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    NEEDS_USER_INPUT = "needs_user_input"
    NO_MATCH = "no_match"


class Candidate(BaseModel):
    scheme: Scheme
    score: float


class ResolvedHolding(BaseModel):
    raw: RawHolding
    status: ResolutionStatus
    scheme: Scheme | None = None
    candidates: list[Candidate] = Field(default_factory=list)
    reason: str = ""


class ParsedPortfolio(BaseModel):
    """The output of ingestion, gated on user confirmation.

    The brief makes showing the parsed table back for confirmation
    non-negotiable -- "a misread number silently corrupts everything
    downstream". `confirmed` defaults False and the compute layer is expected
    to refuse an unconfirmed portfolio, so that gate cannot be skipped by
    forgetting to check it.
    """

    holdings: list[ResolvedHolding]
    as_of: date
    confirmed: bool = False

    @property
    def needs_user_input(self) -> list[ResolvedHolding]:
        return [h for h in self.holdings if h.status is not ResolutionStatus.RESOLVED]

    def is_ready_to_compute(self) -> bool:
        return self.confirmed and not self.needs_user_input

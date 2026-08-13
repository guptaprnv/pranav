"""Monthly portfolio disclosure models.

This is the other half of MF ingestion. The scheme master says which funds
exist; disclosures say what each fund *holds*, which is what look-through
concentration and fund overlap are computed from. Neither of those leak
detectors can exist without this data.

Disclosures are published monthly, so every fact here is stale by construction
-- `as_of` is mandatory, not optional, and downstream code is expected to cite
it rather than imply the holdings are current.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class DisclosureHolding(BaseModel):
    """One line of a scheme's monthly portfolio disclosure.

    `percent_to_nav` is the field look-through actually needs. Quantity and
    market value are kept when present because they are useful for
    cross-checks, but they are not required -- consistent with the brief's
    "quantities are optional; scheme identity plus approximate weights is
    enough" for the MVP's detectors.
    """

    instrument_name: str
    isin: str | None = None
    industry: str | None = None
    quantity: float | None = None
    market_value_lakhs: float | None = None
    percent_to_nav: float | None = None

    @property
    def is_identifiable(self) -> bool:
        """Whether this row can participate in look-through aggregation.

        A holding with no ISIN cannot be reliably matched to the same company
        held by another fund, which is the entire point of look-through. Such
        rows are kept (they still count toward the disclosure's totals) but
        are excluded from cross-fund aggregation rather than matched on name,
        which would silently merge or split companies.
        """
        return bool(self.isin) and self.percent_to_nav is not None


class SchemePortfolio(BaseModel):
    """A single scheme's disclosed portfolio as of one date."""

    scheme_name: str
    as_of: date
    holdings: list[DisclosureHolding]
    source_file: str
    amfi_code: str | None = None
    unmapped_rows: list[str] = Field(default_factory=list)

    @property
    def identifiable_holdings(self) -> list[DisclosureHolding]:
        return [h for h in self.holdings if h.is_identifiable]

    def total_percent_to_nav(self) -> float:
        return sum(h.percent_to_nav or 0.0 for h in self.holdings)


class DisclosureParseError(ValueError):
    """Raised when a disclosure file's columns cannot be identified.

    Deliberately fatal rather than best-effort. A disclosure parsed with the
    wrong column mapping produces plausible-looking weights that are simply
    wrong, and every downstream finding inherits the error silently -- exactly
    the failure the brief's no-silent-fallbacks rule targets.
    """

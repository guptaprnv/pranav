"""Look-through: the user's fund weights x each fund's disclosed holdings, to
get true exposure to each underlying security.

This is arithmetic, not a finding. It computes the exposure table; it does
**not** decide what counts as "concentrated". That judgement is CONC-2
(threshold) and CONC-3 (materiality floor), both unresolved, so nothing here
labels anything a leak.

Two deliberate limits, both traceable to decisions.md:

- **Aggregation is at ISIN grain, not company.** ISIN is the natural key the
  disclosure data provides. Rolling multiple ISINs up to one company (ordinary
  vs DVR shares) is CONC-1 and undecided, so it is not done here. ISIN-grain
  output is a floor on true company exposure, never an overstatement.
- **Holdings without an ISIN are excluded and reported, not name-matched.**
  Matching "Reliance Industries Ltd" to "Reliance Inds." across two AMCs'
  files is exactly the fuzzy-matching problem ING-3 covers, and guessing it
  would silently merge or split companies inside the headline number.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class FundPosition:
    """One of the user's fund holdings, as a share of their total portfolio."""

    scheme_key: str
    weight: float  # 0..1 share of the user's total portfolio


@dataclass
class SecurityExposure:
    """Aggregate exposure to one security across all of the user's funds."""

    isin: str
    instrument_name: str
    total_weight: float = 0.0  # 0..1 of the user's total portfolio
    via_funds: dict[str, float] = field(default_factory=dict)
    oldest_as_of: date | None = None

    @property
    def fund_count(self) -> int:
        return len(self.via_funds)


@dataclass
class LookThroughResult:
    exposures: list[SecurityExposure]
    unresolved_weight: float
    """Share of the user's portfolio that could not be looked through -- funds
    with no disclosure loaded, plus holdings with no ISIN. Reported rather than
    silently dropped, because a concentration figure computed over 60% of a
    portfolio while presented as if it covered 100% is misleading in exactly
    the way the citation rule exists to prevent."""

    funds_without_disclosure: list[str] = field(default_factory=list)
    unidentifiable_weight_by_fund: dict[str, float] = field(default_factory=dict)
    oldest_disclosure: date | None = None

    @property
    def covered_weight(self) -> float:
        return 1.0 - self.unresolved_weight


def compute_look_through(
    positions: list[FundPosition],
    portfolios_by_scheme_key: dict[str, "SchemePortfolioLike"],
) -> LookThroughResult:
    """Aggregate the user's fund weights through to underlying securities.

    `portfolios_by_scheme_key` maps the same key used in `FundPosition` to that
    scheme's parsed disclosure. Any position with no entry is counted toward
    `unresolved_weight` rather than assumed to hold nothing.
    """
    exposures: dict[str, SecurityExposure] = {}
    unresolved = 0.0
    missing: list[str] = []
    unidentifiable: dict[str, float] = {}
    oldest: date | None = None

    for position in positions:
        portfolio = portfolios_by_scheme_key.get(position.scheme_key)
        if portfolio is None:
            unresolved += position.weight
            missing.append(position.scheme_key)
            continue

        if oldest is None or portfolio.as_of < oldest:
            oldest = portfolio.as_of

        for holding in portfolio.holdings:
            percent = holding.percent_to_nav
            if percent is None:
                continue
            # fund weight in portfolio x security weight in fund
            contribution = position.weight * (percent / 100.0)

            if not holding.isin:
                unidentifiable[position.scheme_key] = (
                    unidentifiable.get(position.scheme_key, 0.0) + contribution
                )
                unresolved += contribution
                continue

            exposure = exposures.get(holding.isin)
            if exposure is None:
                exposure = SecurityExposure(
                    isin=holding.isin,
                    instrument_name=holding.instrument_name,
                    oldest_as_of=portfolio.as_of,
                )
                exposures[holding.isin] = exposure

            exposure.total_weight += contribution
            exposure.via_funds[position.scheme_key] = (
                exposure.via_funds.get(position.scheme_key, 0.0) + contribution
            )
            if exposure.oldest_as_of is None or portfolio.as_of < exposure.oldest_as_of:
                exposure.oldest_as_of = portfolio.as_of

    ordered = sorted(exposures.values(), key=lambda e: e.total_weight, reverse=True)

    return LookThroughResult(
        exposures=ordered,
        unresolved_weight=unresolved,
        funds_without_disclosure=missing,
        unidentifiable_weight_by_fund=unidentifiable,
        oldest_disclosure=oldest,
    )


def compute_pairwise_overlap_weights(
    portfolios_by_scheme_key: dict[str, "SchemePortfolioLike"],
    scheme_a: str,
    scheme_b: str,
) -> float:
    """Common holdings between two schemes, as `sum(min(w_a, w_b))` over ISINs.

    NOTE: this implements only one of the candidate definitions in OVER-1,
    which is undecided. It is exposed here because look-through needs the same
    ISIN-keyed weight extraction, but no caller should treat it as *the*
    overlap metric until OVER-1 resolves -- and OVER-2's threshold is
    meaningless until then.
    """
    def weights(key: str) -> dict[str, float]:
        portfolio = portfolios_by_scheme_key[key]
        result: dict[str, float] = {}
        for holding in portfolio.holdings:
            if holding.isin and holding.percent_to_nav is not None:
                result[holding.isin] = result.get(holding.isin, 0.0) + holding.percent_to_nav / 100.0
        return result

    weights_a = weights(scheme_a)
    weights_b = weights(scheme_b)
    shared = set(weights_a) & set(weights_b)
    return sum(min(weights_a[isin], weights_b[isin]) for isin in shared)


class SchemePortfolioLike:
    """Structural type marker for what `compute_look_through` needs.

    Kept as a duck-typed contract (`as_of`, `holdings`) rather than importing
    the concrete model, so these pure functions stay independent of the
    ingestion models and are trivially testable with stubs.
    """

    as_of: date
    holdings: list

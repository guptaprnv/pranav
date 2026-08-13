"""Look-through aggregation tests.

Every expected value here is hand-computable from the inputs, deliberately --
the brief's division of work puts correctness control in the tests rather than
in hand-written core logic, so a test whose expected value cannot be verified
by reading it is not doing its job.
"""
from dataclasses import dataclass
from datetime import date

import pytest

from mf_ingestion.disclosures.models import DisclosureHolding
from mf_ingestion.lookthrough import (
    FundPosition,
    compute_look_through,
    compute_pairwise_overlap_weights,
)


@dataclass
class StubPortfolio:
    as_of: date
    holdings: list


def _holding(name: str, isin: str | None, percent: float) -> DisclosureHolding:
    return DisclosureHolding(instrument_name=name, isin=isin, percent_to_nav=percent)


class TestLookThrough:
    def test_same_stock_across_two_funds_aggregates(self):
        # Fund A is 60% of the portfolio and holds 10% Alpha -> 0.06
        # Fund B is 40% of the portfolio and holds 20% Alpha -> 0.08
        # combined exposure to Alpha = 0.14
        portfolios = {
            "A": StubPortfolio(date(2026, 7, 31), [_holding("Alpha Bank", "INE_A", 10.0)]),
            "B": StubPortfolio(date(2026, 7, 31), [_holding("Alpha Bank", "INE_A", 20.0)]),
        }
        positions = [FundPosition("A", 0.6), FundPosition("B", 0.4)]

        result = compute_look_through(positions, portfolios)

        assert len(result.exposures) == 1
        alpha = result.exposures[0]
        assert alpha.total_weight == pytest.approx(0.14)
        assert alpha.fund_count == 2
        assert alpha.via_funds["A"] == pytest.approx(0.06)
        assert alpha.via_funds["B"] == pytest.approx(0.08)

    def test_exposures_are_sorted_largest_first(self):
        portfolios = {
            "A": StubPortfolio(
                date(2026, 7, 31),
                [
                    _holding("Small", "INE_S", 5.0),
                    _holding("Big", "INE_B", 40.0),
                    _holding("Mid", "INE_M", 20.0),
                ],
            )
        }
        result = compute_look_through([FundPosition("A", 1.0)], portfolios)

        assert [e.instrument_name for e in result.exposures] == ["Big", "Mid", "Small"]

    def test_fund_with_no_disclosure_counts_as_unresolved_not_empty(self):
        """A fund we have no disclosure for holds *unknown* things, not nothing.
        Treating it as empty would understate concentration."""
        portfolios = {
            "A": StubPortfolio(date(2026, 7, 31), [_holding("Alpha", "INE_A", 50.0)]),
        }
        positions = [FundPosition("A", 0.7), FundPosition("MISSING", 0.3)]

        result = compute_look_through(positions, portfolios)

        assert result.unresolved_weight == 0.3
        assert result.funds_without_disclosure == ["MISSING"]
        assert result.covered_weight == 0.7

    def test_holdings_without_isin_are_excluded_and_reported(self):
        # 100% of portfolio in fund A; A holds 10% identifiable + 4% unlisted
        portfolios = {
            "A": StubPortfolio(
                date(2026, 7, 31),
                [
                    _holding("Alpha", "INE_A", 10.0),
                    _holding("Unlisted Co", None, 4.0),
                ],
            )
        }
        result = compute_look_through([FundPosition("A", 1.0)], portfolios)

        assert len(result.exposures) == 1
        assert result.unresolved_weight == 0.04
        assert result.unidentifiable_weight_by_fund == {"A": 0.04}

    def test_oldest_disclosure_date_is_tracked_for_citation(self):
        """Two funds disclosed on different dates means the aggregate has two
        as-of dates; the oldest bounds how current the whole figure is."""
        portfolios = {
            "A": StubPortfolio(date(2026, 7, 31), [_holding("Alpha", "INE_A", 10.0)]),
            "B": StubPortfolio(date(2026, 6, 30), [_holding("Alpha", "INE_A", 10.0)]),
        }
        positions = [FundPosition("A", 0.5), FundPosition("B", 0.5)]

        result = compute_look_through(positions, portfolios)

        assert result.oldest_disclosure == date(2026, 6, 30)
        assert result.exposures[0].oldest_as_of == date(2026, 6, 30)

    def test_no_finding_is_labelled(self):
        """Look-through returns exposures, never verdicts. Concentration
        thresholds are CONC-2/CONC-3 and undecided."""
        portfolios = {
            "A": StubPortfolio(date(2026, 7, 31), [_holding("Whole Portfolio", "INE_W", 100.0)])
        }
        result = compute_look_through([FundPosition("A", 1.0)], portfolios)

        exposure = result.exposures[0]
        assert exposure.total_weight == 1.0
        assert not hasattr(exposure, "is_concentrated")
        assert not hasattr(exposure, "severity")


class TestPairwiseOverlap:
    def test_identical_portfolios_overlap_fully(self):
        holdings = [_holding("Alpha", "INE_A", 60.0), _holding("Beta", "INE_B", 40.0)]
        portfolios = {
            "A": StubPortfolio(date(2026, 7, 31), holdings),
            "B": StubPortfolio(date(2026, 7, 31), list(holdings)),
        }
        assert compute_pairwise_overlap_weights(portfolios, "A", "B") == 1.0

    def test_disjoint_portfolios_do_not_overlap(self):
        portfolios = {
            "A": StubPortfolio(date(2026, 7, 31), [_holding("Alpha", "INE_A", 100.0)]),
            "B": StubPortfolio(date(2026, 7, 31), [_holding("Beta", "INE_B", 100.0)]),
        }
        assert compute_pairwise_overlap_weights(portfolios, "A", "B") == 0.0

    def test_partial_overlap_takes_the_minimum_weight(self):
        # shared Alpha at min(50%, 30%) = 30%; Beta/Gamma not shared
        portfolios = {
            "A": StubPortfolio(
                date(2026, 7, 31),
                [_holding("Alpha", "INE_A", 50.0), _holding("Beta", "INE_B", 50.0)],
            ),
            "B": StubPortfolio(
                date(2026, 7, 31),
                [_holding("Alpha", "INE_A", 30.0), _holding("Gamma", "INE_G", 70.0)],
            ),
        }
        assert compute_pairwise_overlap_weights(portfolios, "A", "B") == 0.3

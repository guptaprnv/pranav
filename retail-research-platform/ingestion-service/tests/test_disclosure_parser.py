from datetime import date
from pathlib import Path

import pytest

from mf_ingestion.disclosures.models import DisclosureParseError
from mf_ingestion.disclosures.parser import (
    is_structural_row,
    map_columns,
    parse_csv,
    parse_rows,
)

FIXTURE = Path(__file__).parent / "fixtures" / "disclosure_sample.csv"


def _portfolio():
    return parse_csv(
        FIXTURE,
        scheme_name="Example One Large Cap Fund",
        as_of=date(2026, 7, 31),
        amfi_code="100101",
    )


class TestColumnMapping:
    def test_maps_standard_sebi_headers(self):
        mapping = map_columns(
            [
                "Name of the Instrument",
                "ISIN",
                "Industry^",
                "Quantity",
                "Market value (Rs. in Lakhs)",
                "% to Net Assets",
            ]
        )
        assert mapping["instrument_name"] == 0
        assert mapping["isin"] == 1
        assert mapping["percent_to_nav"] == 5

    def test_tolerates_alternative_wordings_between_amcs(self):
        mapping = map_columns(["Security Name", "ISIN", "% to NAV"])
        assert mapping["instrument_name"] == 0
        assert mapping["percent_to_nav"] == 2

    def test_footnote_markers_do_not_break_matching(self):
        mapping = map_columns(["Name of the Instrument", "ISIN", "% to Net Assets #"])
        assert mapping["percent_to_nav"] == 2

    def test_missing_required_column_fails_loudly_with_what_it_saw(self):
        with pytest.raises(DisclosureParseError) as excinfo:
            map_columns(["Name of the Instrument", "ISIN", "Quantity"])

        message = str(excinfo.value)
        assert "percent_to_nav" in message
        # the error must be diagnosable without opening the file
        assert "Quantity" in message

    def test_never_falls_back_to_column_position(self):
        # three unlabelled columns in the right order must still fail --
        # a mis-mapped column yields plausible but wrong weights
        with pytest.raises(DisclosureParseError):
            map_columns(["A", "B", "C"])


class TestParsing:
    def test_finds_the_header_row_below_title_metadata(self):
        # the fixture has three title rows and a blank before the real header.
        # 7 holdings = 4 listed equities + 1 unlisted + TREPS + net receivables.
        # the cash lines are genuine portfolio components, not structural rows,
        # so they count -- only totals/subtotals are excluded.
        portfolio = _portfolio()
        assert len(portfolio.holdings) == 7

    def test_extracts_holdings_with_thousands_separators(self):
        portfolio = _portfolio()
        alpha = next(h for h in portfolio.holdings if h.instrument_name == "Alpha Bank Ltd")

        assert alpha.isin == "INE000A01001"
        assert alpha.percent_to_nav == 9.85
        assert alpha.quantity == 1250000.0
        assert alpha.market_value_lakhs == 18450.00
        assert alpha.industry == "Financial Services"

    def test_section_headers_and_subtotals_are_not_treated_as_holdings(self):
        portfolio = _portfolio()
        names = {h.instrument_name for h in portfolio.holdings}

        for noise in ("Equity & Equity related", "Sub Total", "Total", "Grand Total"):
            assert noise not in names

    def test_non_holding_rows_are_surfaced_not_silently_dropped(self):
        portfolio = _portfolio()
        assert portfolio.unmapped_rows
        assert any("Sub Total" in row for row in portfolio.unmapped_rows)

    def test_holding_without_isin_is_kept_but_not_identifiable(self):
        portfolio = _portfolio()
        unlisted = next(h for h in portfolio.holdings if h.instrument_name == "Some Unlisted Co")

        assert unlisted.isin is None
        assert unlisted.is_identifiable is False
        # it still exists, so it counts toward totals rather than vanishing
        assert unlisted.percent_to_nav == 0.13
        assert len(portfolio.identifiable_holdings) == 4

    def test_negative_percentages_are_preserved(self):
        # net payables are legitimately negative; coercing them to 0 or
        # dropping them would quietly inflate every other weight's share
        rows = [
            ["Name of the Instrument", "ISIN", "% to Net Assets"],
            ["Net Receivables / (Payables)", "", "-0.08"],
        ]
        portfolio = parse_rows(rows, "X", date(2026, 7, 31), "test")
        assert portfolio.holdings[0].percent_to_nav == -0.08

    def test_as_of_is_carried_through_not_inferred(self):
        portfolio = _portfolio()
        assert portfolio.as_of == date(2026, 7, 31)
        assert portfolio.amfi_code == "100101"

    def test_subtotals_would_double_count_if_admitted(self):
        """Regression guard for the bug these tests originally caught.

        Subtotal rows carry a name and a percentage, so a naive parser reads
        them as holdings and every look-through exposure roughly doubles. The
        fixture's holdings sum to 23.88; admitting the subtotal rows would push
        it past 70.
        """
        portfolio = _portfolio()
        assert portfolio.total_percent_to_nav() == pytest.approx(24.92, abs=0.01)


class TestStructuralRowDetection:
    """Both signals are required -- see is_structural_row's docstring."""

    def test_total_rows_without_isin_are_structural(self):
        assert is_structural_row("Sub Total", None) is True
        assert is_structural_row("Total", None) is True
        assert is_structural_row("Grand Total", None) is True
        assert is_structural_row("Sub-Total", None) is True
        assert is_structural_row("Net Assets", None) is True

    def test_a_real_company_named_total_is_not_structural(self):
        # TotalEnergies is a genuine listed company; name alone must not
        # disqualify a row that carries an ISIN
        assert is_structural_row("TotalEnergies SE", "INE000X01001") is False

    def test_unlisted_holding_without_isin_is_not_structural(self):
        # no ISIN, but the name is not a total marker -- a real position
        assert is_structural_row("Some Unlisted Co", None) is False

    def test_structural_rows_are_reported_in_unmapped_not_dropped(self):
        portfolio = _portfolio()
        assert any("Sub Total" in row for row in portfolio.unmapped_rows)
        assert any("Grand Total" in row for row in portfolio.unmapped_rows)

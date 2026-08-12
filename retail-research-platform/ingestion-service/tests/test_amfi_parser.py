from datetime import date
from pathlib import Path

from mf_ingestion.amfi.parser import detect_option, detect_plan, parse_navall
from mf_ingestion.models import Option, Plan

FIXTURE = Path(__file__).parent / "fixtures" / "navall_sample.txt"


def _master():
    return parse_navall(
        FIXTURE.read_text(encoding="utf-8"),
        source_url="file://navall_sample.txt",
        fetched_at=date(2026, 8, 6),
    )


def test_parses_every_data_row_and_nothing_else():
    master = _master()
    assert len(master.schemes) == 8
    assert master.unparsed_lines == []


def test_category_and_amc_carry_down_to_following_rows():
    by_code = _master().by_code()

    assert by_code["100101"].amc == "Example One Mutual Fund"
    assert "Large Cap Fund" in by_code["100101"].category

    # the third section -- proves state resets rather than accumulating
    assert by_code["100301"].amc == "Example Three Mutual Fund"
    assert "Liquid Fund" in by_code["100301"].category


def test_nav_and_date_parsed_with_na_becoming_none():
    by_code = _master().by_code()

    assert by_code["100101"].nav == 145.6721
    assert by_code["100101"].nav_date == date(2026, 8, 6)

    # "N.A." must not become 0.0 -- a zero NAV would silently corrupt any
    # downstream value calculation, which is exactly the failure the
    # no-silent-fallbacks rule exists to prevent
    assert by_code["100302"].nav_date is None
    assert by_code["100303"].nav is None


def test_missing_isins_become_none_not_empty_string():
    by_code = _master().by_code()

    assert by_code["100302"].isin_reinvestment is None
    assert by_code["100303"].isin_growth is None


def test_malformed_row_is_surfaced_not_dropped():
    text = (
        "Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;"
        "Scheme Name;Net Asset Value;Date\n"
        "Open Ended Schemes(Equity Scheme - Large Cap Fund)\n"
        "Example AMC\n"
        "100101;INF000A01AA1;INF000A01AB9;Good Fund - Direct Plan - Growth;10.0;06-Aug-2026\n"
        "100102;INF000A01AC7;TOO;FEW;FIELDS\n"
    )
    master = parse_navall(text, source_url="test", fetched_at=date(2026, 8, 6))

    assert len(master.schemes) == 1
    assert len(master.unparsed_lines) == 1
    assert "TOO;FEW;FIELDS" in master.unparsed_lines[0]


class TestPlanDetection:
    def test_explicit_direct_and_regular(self):
        assert detect_plan("Example Fund - Direct Plan - Growth") is Plan.DIRECT
        assert detect_plan("Example Fund - Regular Plan - Growth") is Plan.REGULAR

    def test_absent_marker_is_unknown_not_a_guess(self):
        # many older schemes carry no plan marker at all; guessing here would
        # fabricate or erase the fee-drag finding (see decisions ING-4)
        assert detect_plan("Example Three Liquid Fund - Growth") is Plan.UNKNOWN

    def test_both_markers_present_is_unknown(self):
        assert detect_plan("Direct and Regular Plan Fund") is Plan.UNKNOWN

    def test_substring_does_not_false_positive(self):
        # "Directional" contains "direct" but is not a Direct plan
        assert detect_plan("Example Directional Strategy Fund - Growth") is Plan.UNKNOWN


class TestOptionDetection:
    def test_growth_and_idcw(self):
        assert detect_option("Example Fund - Direct Plan - Growth") is Option.GROWTH
        assert detect_option("Example Fund - Direct Plan - IDCW") is Option.IDCW

    def test_legacy_dividend_wording_maps_to_idcw(self):
        assert detect_option("Example Fund - Dividend Payout") is Option.IDCW
        assert detect_option("Example Fund - Direct - Reinvestment") is Option.IDCW

    def test_ambiguous_is_unknown(self):
        assert detect_option("Example Fund - Growth and Dividend") is Option.UNKNOWN

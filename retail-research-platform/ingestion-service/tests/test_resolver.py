"""Resolver tests.

These inject ING-1/ING-2 values rather than reading them, which is the point:
the *logic* is verified now, the *numbers* stay the architect's call. Every
injected value here is a test scaffold, not a proposed threshold.
"""
from datetime import date
from pathlib import Path

import pytest

from mf_ingestion import decisions
from mf_ingestion.amfi.parser import parse_navall
from mf_ingestion.models import Plan, RawHolding, ResolutionStatus
from mf_ingestion.resolution.resolver import normalise, resolve, score_candidates

FIXTURE = Path(__file__).parent / "fixtures" / "navall_sample.txt"


@pytest.fixture
def schemes():
    master = parse_navall(
        FIXTURE.read_text(encoding="utf-8"),
        source_url="test",
        fetched_at=date(2026, 8, 6),
    )
    return master.schemes


def exact_prefix_scorer(target: str, candidate: str) -> float:
    """A deterministic stand-in for ING-3, used only to drive the tests.

    Ratio of the longest common prefix to the longer string. Chosen because it
    is trivially hand-computable, so expected values in these tests can be
    verified by reading them -- NOT because it is a recommendation for the real
    metric, which is ING-3 and undecided.
    """
    common = 0
    for a, b in zip(target, candidate):
        if a != b:
            break
        common += 1
    longest = max(len(target), len(candidate))
    return common / longest if longest else 0.0


class TestNormalise:
    def test_strips_punctuation_and_case(self):
        assert normalise("HDFC Mid-Cap Opportunities Fund") == "hdfc mid cap opportunities fund"

    def test_collapses_runs_of_punctuation_to_single_space(self):
        assert normalise("Fund  --  Direct   Plan") == "fund direct plan"


class TestScoreCandidates:
    def test_excludes_candidates_whose_plan_contradicts_the_raw_name(self, schemes):
        candidates = score_candidates(
            "Example One Large Cap Fund - Direct Plan - Growth",
            schemes,
            exact_prefix_scorer,
            limit=10,
        )
        plans = {candidate.scheme.plan for candidate in candidates}
        assert Plan.REGULAR not in plans

    def test_keeps_unknown_plan_candidates_when_raw_name_states_a_plan(self, schemes):
        # an UNKNOWN-plan scheme is not a contradiction, it is an ambiguity --
        # excluding it would hide a legitimate match
        candidates = score_candidates(
            "Example Three Liquid Fund - Direct Plan - Growth",
            schemes,
            exact_prefix_scorer,
            limit=10,
        )
        assert any(candidate.scheme.plan is Plan.UNKNOWN for candidate in candidates)

    def test_returns_candidates_sorted_best_first(self, schemes):
        candidates = score_candidates(
            "Example Two Mid-Cap Opportunities Fund - Direct Plan - Growth",
            schemes,
            exact_prefix_scorer,
            limit=5,
        )
        scores = [candidate.score for candidate in candidates]
        assert scores == sorted(scores, reverse=True)


class TestResolveRefusesToGuess:
    def test_raises_when_thresholds_are_undecided(self, schemes):
        holding = RawHolding(scheme_name_raw="Example One Large Cap Fund - Direct Plan - Growth")

        with pytest.raises(decisions.UnresolvedDecisionError) as excinfo:
            resolve(holding, schemes, exact_prefix_scorer)

        assert excinfo.value.decision_id == "ING-1"


class TestResolveLogic:
    """Thresholds injected purely to exercise the branches."""

    def test_strong_match_with_explicit_plan_resolves(self, schemes):
        holding = RawHolding(scheme_name_raw="Example One Large Cap Fund - Direct Plan - Growth")

        with decisions.with_values(
            {
                decisions.ING_1_AUTO_ACCEPT_SCORE: 0.9,
                decisions.ING_2_ASK_USER_SCORE: 0.3,
            }
        ):
            result = resolve(holding, schemes, exact_prefix_scorer)

        assert result.status is ResolutionStatus.RESOLVED
        assert result.scheme.amfi_code == "100101"

    def test_score_in_the_ambiguous_band_asks_the_user(self, schemes):
        # truncated mid-word, but the plan is still explicit -- so this lands
        # in the band on score alone, without the ING-4 plan branch firing.
        # normalised: 41 chars of a 44-char target -> 0.932
        holding = RawHolding(scheme_name_raw="Example One Large Cap Fund - Direct Plan - Gro")

        with decisions.with_values(
            {
                decisions.ING_1_AUTO_ACCEPT_SCORE: 0.999,
                decisions.ING_2_ASK_USER_SCORE: 0.1,
            }
        ):
            result = resolve(holding, schemes, exact_prefix_scorer)

        assert result.status is ResolutionStatus.NEEDS_USER_INPUT
        assert "ambiguous band" in result.reason
        assert result.candidates  # the user needs options to choose from

    def test_score_below_the_floor_is_no_match(self, schemes):
        holding = RawHolding(scheme_name_raw="Completely Unrelated Pension Product")

        with decisions.with_values(
            {
                decisions.ING_1_AUTO_ACCEPT_SCORE: 0.9,
                decisions.ING_2_ASK_USER_SCORE: 0.5,
            }
        ):
            result = resolve(holding, schemes, exact_prefix_scorer)

        assert result.status is ResolutionStatus.NO_MATCH

    def test_truncated_name_missing_plan_asks_rather_than_assuming(self, schemes):
        """The case the brief calls out specifically: the truncated part is the
        plan variant, and it determines the largest leak."""
        holding = RawHolding(scheme_name_raw="Example One Large Cap Fund")

        with decisions.with_values(
            {
                decisions.ING_1_AUTO_ACCEPT_SCORE: 0.1,  # would otherwise auto-accept
                decisions.ING_2_ASK_USER_SCORE: 0.0,
            }
        ):
            result = resolve(holding, schemes, exact_prefix_scorer)

        assert result.status is ResolutionStatus.NEEDS_USER_INPUT
        assert "ING-4" in result.reason

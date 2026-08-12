"""The decisions register is the mechanism that makes the brief's hard rule
enforceable, so it gets tested like load-bearing code, not config.
"""
import pytest

from mf_ingestion import decisions


def test_every_ingestion_decision_is_still_unresolved():
    # This is a tripwire, not a formality: if someone resolves a decision in
    # code without updating decisions.md, this test tells them to go do that.
    assert decisions.unresolved_ids() == ["ING-1", "ING-2", "ING-3", "ING-4"]


def test_reading_an_unresolved_decision_raises_rather_than_defaulting():
    with pytest.raises(decisions.UnresolvedDecisionError) as excinfo:
        decisions.get(decisions.ING_1_AUTO_ACCEPT_SCORE)

    message = str(excinfo.value)
    assert "ING-1" in message
    assert "decisions.md" in message
    # the error should actively discourage the exact wrong fix
    assert "do NOT pick a default" in message


def test_injected_value_is_readable_inside_the_block_only():
    with decisions.with_values({decisions.ING_1_AUTO_ACCEPT_SCORE: 0.92}):
        assert decisions.get(decisions.ING_1_AUTO_ACCEPT_SCORE) == 0.92

    with pytest.raises(decisions.UnresolvedDecisionError):
        decisions.get(decisions.ING_1_AUTO_ACCEPT_SCORE)


def test_injection_does_not_mark_the_decision_resolved_in_the_register():
    with decisions.with_values({decisions.ING_1_AUTO_ACCEPT_SCORE: 0.92}):
        # is_resolved reports True because a value is readable in this scope,
        # but the underlying register entry is untouched -- so the tripwire
        # test above still fails if anyone edits the register itself
        assert decisions.is_resolved(decisions.ING_1_AUTO_ACCEPT_SCORE)

    assert "ING-1" in decisions.unresolved_ids()


def test_injecting_an_unknown_decision_id_is_an_error():
    with pytest.raises(KeyError):
        with decisions.with_values({"NOT-A-REAL-ID": 1}):
            pass


def test_nested_injection_restores_the_outer_value():
    with decisions.with_values({decisions.ING_1_AUTO_ACCEPT_SCORE: 0.90}):
        with decisions.with_values({decisions.ING_1_AUTO_ACCEPT_SCORE: 0.95}):
            assert decisions.get(decisions.ING_1_AUTO_ACCEPT_SCORE) == 0.95
        assert decisions.get(decisions.ING_1_AUTO_ACCEPT_SCORE) == 0.90

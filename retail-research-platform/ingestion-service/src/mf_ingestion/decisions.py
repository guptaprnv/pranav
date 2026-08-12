"""Programmatic mirror of ../../../decisions.md.

This module is the enforcement mechanism for the build brief's hard rule:

    Never invent a threshold, cutoff, weight, or business rule. If a value is
    needed and not specified, STOP and ask.

Every judgement value in the codebase is registered here by its decisions.md ID
and referenced by name -- never inlined as a literal. Unresolved decisions have
no value at all, and reading one raises `UnresolvedDecisionError` rather than
falling back to a plausible default. That makes "the agent quietly picked a
number" a loud runtime failure instead of a silent correctness bug that only
shows up in a user's findings.

Tests exercise detector *logic* by injecting values explicitly (see
`with_values`), which deliberately does not resolve the decision -- it proves
the machinery works without pinning the number, so filling in decisions.md
later cannot be mistaken for already-done.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


class UnresolvedDecisionError(RuntimeError):
    """Raised when code reads a decision that has not been decided yet."""

    def __init__(self, decision_id: str, question: str) -> None:
        super().__init__(
            f"decision {decision_id} is UNRESOLVED and has no value.\n"
            f"  question: {question}\n"
            f"  fix: resolve {decision_id} in decisions.md, then set it here.\n"
            f"  do NOT pick a default to get past this error."
        )
        self.decision_id = decision_id


@dataclass(frozen=True)
class Decision:
    id: str
    question: str
    value: Any = None
    resolved: bool = False
    note: str = ""


_REGISTRY: dict[str, Decision] = {}
_OVERRIDES: dict[str, Any] = {}


def _register(decision: Decision) -> str:
    _REGISTRY[decision.id] = decision
    return decision.id


def get(decision_id: str) -> Any:
    """Read a decision's value, or raise if it is not decided."""
    if decision_id in _OVERRIDES:
        return _OVERRIDES[decision_id]
    try:
        decision = _REGISTRY[decision_id]
    except KeyError:
        raise KeyError(f"no such decision: {decision_id}") from None
    if not decision.resolved:
        raise UnresolvedDecisionError(decision.id, decision.question)
    return decision.value


def is_resolved(decision_id: str) -> bool:
    return decision_id in _OVERRIDES or _REGISTRY[decision_id].resolved


def unresolved_ids() -> list[str]:
    return sorted(d.id for d in _REGISTRY.values() if not d.resolved)


@contextmanager
def with_values(overrides: dict[str, Any]) -> Iterator[None]:
    """Inject decision values for the duration of a block, e.g.
    `with_values({ING_1_AUTO_ACCEPT_SCORE: 0.9})`.

    For tests only. This exists so a detector's logic can be tested at a
    boundary without anyone having to commit to what the boundary *is* --
    injecting a value here deliberately does not mark the decision resolved.
    """
    unknown = set(overrides) - set(_REGISTRY)
    if unknown:
        raise KeyError(f"no such decision(s): {sorted(unknown)}")
    previous = dict(_OVERRIDES)
    _OVERRIDES.update(overrides)
    try:
        yield
    finally:
        _OVERRIDES.clear()
        _OVERRIDES.update(previous)


# ---------------------------------------------------------------------------
# Ingestion & entity resolution. See decisions.md section 1.
# ---------------------------------------------------------------------------

ING_1_AUTO_ACCEPT_SCORE = _register(
    Decision(
        id="ING-1",
        question=(
            "Above what match score is a parsed scheme name auto-bound to an AMFI "
            "scheme code without asking the user?"
        ),
        note=(
            "Blocked on ING-3 -- a score threshold is meaningless until the metric "
            "producing the score is fixed."
        ),
    )
)

ING_2_ASK_USER_SCORE = _register(
    Decision(
        id="ING-2",
        question=(
            "Below what match score do we refuse to guess and ask the user to "
            "disambiguate? And how is the band between ING-2 and ING-1 handled?"
        ),
    )
)

ING_3_DISTANCE_METRIC = _register(
    Decision(
        id="ING-3",
        question=(
            "Which string distance metric backs ING-1/ING-2 -- token-set ratio, "
            "Levenshtein, or two-stage token blocking then edit distance?"
        ),
        note=(
            "Metrics disagree sharply on truncated scheme names, which are the "
            "common case per the brief."
        ),
    )
)

ING_4_PLAN_DISAMBIGUATION = _register(
    Decision(
        id="ING-4",
        question=(
            "When plan (Direct/Regular) or option (Growth/IDCW) is absent or "
            "truncated away, do we always ask, or infer from context?"
        ),
        note=(
            "Defaulting here fabricates the regular-vs-direct drag finding in one "
            "direction or the other. Until resolved, the resolver returns "
            "NEEDS_USER_INPUT rather than assuming."
        ),
    )
)

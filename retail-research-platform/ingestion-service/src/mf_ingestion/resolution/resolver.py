"""Entity resolution: raw scheme name (often truncated) -> AMFI scheme code.

This module is intentionally incomplete, and the incompleteness is enforced:

- The scoring metric is **ING-3**, unresolved. `resolve` therefore takes a
  scorer as an argument rather than defaulting to one. There is no fallback
  metric, because picking one silently would make ING-1/ING-2's numbers mean
  something different from whatever the architect eventually intends.
- The accept/ask thresholds are **ING-1** and **ING-2**, unresolved. Reading
  them raises `UnresolvedDecisionError`.

So `resolve` cannot run end to end today. That is the correct behaviour under
the brief's hard rule, not a gap to paper over. The machinery below is fully
built and tested by injecting values (see tests), which proves the logic works
without pinning the numbers.

The normalisation step is *not* a judgement value -- it is deterministic string
hygiene applied identically to both sides of every comparison, so it cannot
tilt a match toward one candidate over another.
"""
from __future__ import annotations

import re
from typing import Callable, Protocol

from .. import decisions
from ..models import (
    Candidate,
    Plan,
    RawHolding,
    ResolutionStatus,
    ResolvedHolding,
    Scheme,
)

Scorer = Callable[[str, str], float]


class SchemeIndex(Protocol):
    def __iter__(self): ...


# Punctuation and casing carry no identifying information in scheme names and
# vary freely between a CAS PDF, a broker screenshot, and AMFI's own feed.
_PUNCT_RE = re.compile(r"[^a-z0-9]+")


def normalise(name: str) -> str:
    return _PUNCT_RE.sub(" ", name.lower()).strip()


def _plan_conflict(raw_name: str, scheme: Scheme) -> bool:
    """True when the raw string states a plan that contradicts the candidate.

    Only fires on an explicit contradiction. A raw name with no plan marker is
    not a conflict -- it is an ambiguity, handled by ING-4, because the marker
    is frequently the part that got truncated away.
    """
    from ..amfi.parser import detect_plan

    raw_plan = detect_plan(raw_name)
    if raw_plan is Plan.UNKNOWN or scheme.plan is Plan.UNKNOWN:
        return False
    return raw_plan is not scheme.plan


def score_candidates(
    raw_name: str,
    schemes: list[Scheme],
    scorer: Scorer,
    limit: int = 5,
) -> list[Candidate]:
    """Score every scheme against the raw name and return the best `limit`.

    Candidates whose plan explicitly contradicts the raw name are excluded
    rather than down-weighted: a Direct holding is not a fuzzy match for the
    Regular variant of the same fund, it is the wrong scheme, and the fee-drag
    finding depends on getting that right.
    """
    target = normalise(raw_name)
    scored = [
        Candidate(scheme=scheme, score=scorer(target, normalise(scheme.name)))
        for scheme in schemes
        if not _plan_conflict(raw_name, scheme)
    ]
    scored.sort(key=lambda candidate: candidate.score, reverse=True)
    return scored[:limit]


def resolve(
    holding: RawHolding,
    schemes: list[Scheme],
    scorer: Scorer,
) -> ResolvedHolding:
    """Resolve one raw holding against the scheme master.

    Raises `UnresolvedDecisionError` for ING-1/ING-2 until those are decided.
    """
    auto_accept = decisions.get(decisions.ING_1_AUTO_ACCEPT_SCORE)
    ask_user = decisions.get(decisions.ING_2_ASK_USER_SCORE)

    candidates = score_candidates(holding.scheme_name_raw, schemes, scorer)
    if not candidates:
        return ResolvedHolding(
            raw=holding,
            status=ResolutionStatus.NO_MATCH,
            reason="no candidate schemes after plan-conflict filtering",
        )

    best = candidates[0]

    if best.score < ask_user:
        return ResolvedHolding(
            raw=holding,
            status=ResolutionStatus.NO_MATCH,
            candidates=candidates,
            reason=f"best score {best.score:.3f} below ING-2 floor {ask_user}",
        )

    if best.score < auto_accept:
        return ResolvedHolding(
            raw=holding,
            status=ResolutionStatus.NEEDS_USER_INPUT,
            candidates=candidates,
            reason=(
                f"best score {best.score:.3f} in the ING-2..ING-1 ambiguous band "
                f"[{ask_user}, {auto_accept})"
            ),
        )

    # A clear winner on score can still be ambiguous on plan: if the raw name
    # never stated Direct/Regular, both variants remain live and they differ by
    # exactly the fee drag we are trying to measure. That is ING-4's call, and
    # until it is decided we ask rather than assume.
    if best.scheme.plan is not Plan.UNKNOWN:
        from ..amfi.parser import detect_plan

        if detect_plan(holding.scheme_name_raw) is Plan.UNKNOWN:
            if not decisions.is_resolved(decisions.ING_4_PLAN_DISAMBIGUATION):
                return ResolvedHolding(
                    raw=holding,
                    status=ResolutionStatus.NEEDS_USER_INPUT,
                    candidates=candidates,
                    reason=(
                        "raw name does not state Direct/Regular; ING-4 undecided, "
                        "so the plan variant must be confirmed by the user"
                    ),
                )

    return ResolvedHolding(
        raw=holding,
        status=ResolutionStatus.RESOLVED,
        scheme=best.scheme,
        candidates=candidates,
        reason=f"score {best.score:.3f} at or above ING-1 {auto_accept}",
    )

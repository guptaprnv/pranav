"""Portfolio-level primitives -- correlation, drift, concentration. These are
the primitives the main doc's Portfolio domain (Section 5) and the
cross-domain/blended-exposure discussion (docs/product-architecture.md,
"Cross-domain query reasoning") are built on: pure computation over weights
and return series, never something a Reasoning Agent assembles live.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from ..confidence import confidence_from_sample_size
from ..models import ConfidenceLevel, PrimitiveResult
from ..pipeline_versions import CONCENTRATION_V1, CORRELATION_V1, DRIFT_V1

DETERMINISTIC_REASON = (
    "deterministic computation on current holdings/weights, not a statistical estimate"
)


def compute_correlation_matrix(returns_by_entity: dict[str, pd.Series]) -> PrimitiveResult:
    """Pairwise correlation of daily returns across holdings.

    Takes already-computed return series (see primitives/returns.py) rather
    than prices, so this primitive composes with the rest of the package
    instead of recomputing returns itself.
    """
    frame = pd.DataFrame(returns_by_entity)
    aligned = frame.dropna()
    sample_size = len(aligned)
    confidence, reason = confidence_from_sample_size(sample_size)

    matrix = frame.corr().round(4)

    return PrimitiveResult(
        name="correlation_matrix",
        value=matrix.to_dict(),
        computed_at=datetime.now(timezone.utc),
        pipeline_version=CORRELATION_V1,
        input_as_of=aligned.index.max().date() if sample_size else date.today(),
        confidence=confidence,
        confidence_reason=reason,
        sample_size=sample_size,
    )


def compute_drift(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    as_of: date,
) -> PrimitiveResult:
    """Drift of current allocation from a target, per category -- the
    caller decides what "category" means (asset class, sector, or theme)
    by choosing what keys go into the two weight dicts.
    """
    categories = sorted(set(current_weights) | set(target_weights))
    drift = {
        category: round(
            current_weights.get(category, 0.0) - target_weights.get(category, 0.0), 4
        )
        for category in categories
    }
    max_drift_category = max(drift, key=lambda c: abs(drift[c])) if drift else None

    return PrimitiveResult(
        name="drift",
        value={
            "drift_by_category": drift,
            "max_drift_category": max_drift_category,
            "max_drift": drift.get(max_drift_category) if max_drift_category else None,
        },
        computed_at=datetime.now(timezone.utc),
        pipeline_version=DRIFT_V1,
        input_as_of=as_of,
        confidence=ConfidenceLevel.HIGH,
        confidence_reason=DETERMINISTIC_REASON,
        sample_size=None,
    )


def compute_concentration(
    weights: dict[str, float],
    as_of: date,
    top_n: int = 3,
) -> PrimitiveResult:
    """Herfindahl-Hirschman Index plus top-N concentration, at whatever
    level the caller passes in (position, sector, or theme weights).

    HHI is the sum of squared weights -- ranges from ~0 (fully diversified)
    to 1 (single holding). It's the standard concentration measure because
    it penalizes large individual weights more than a simple max/sum would.
    """
    sorted_weights = sorted(weights.values(), reverse=True)
    hhi = round(sum(w**2 for w in weights.values()), 4)
    top_n_weight = round(sum(sorted_weights[:top_n]), 4)
    largest = sorted_weights[0] if sorted_weights else 0.0

    return PrimitiveResult(
        name="concentration",
        value={
            "hhi": hhi,
            "largest_weight": round(largest, 4),
            f"top_{top_n}_weight": top_n_weight,
        },
        computed_at=datetime.now(timezone.utc),
        pipeline_version=CONCENTRATION_V1,
        input_as_of=as_of,
        confidence=ConfidenceLevel.HIGH,
        confidence_reason=DETERMINISTIC_REASON,
        sample_size=None,
    )

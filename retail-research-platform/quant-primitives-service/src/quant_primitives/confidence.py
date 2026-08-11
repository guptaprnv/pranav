"""Confidence, computed structurally from sample size -- never self-reported
by a model. See docs/product-architecture.md, "Ambiguity & confidence
handling": LLM self-reported confidence is poorly calibrated, so confidence
has to be a deterministic property of the signal, the same way alpha or
beta is computed rather than guessed.

Thresholds are trading-day counts: a newly-listed stock or a fund with a few
months of history shouldn't get the same confidence label as one with years
of data behind it, regardless of what the computed value happens to be.
"""
from __future__ import annotations

from .models import ConfidenceLevel

HIGH_THRESHOLD_DAYS = 252  # ~1 trading year
MEDIUM_THRESHOLD_DAYS = 60  # ~3 trading months


def confidence_from_sample_size(sample_size: int) -> tuple[ConfidenceLevel, str]:
    if sample_size >= HIGH_THRESHOLD_DAYS:
        return (
            ConfidenceLevel.HIGH,
            f"{sample_size} trading days of history (>= 1 year)",
        )
    if sample_size >= MEDIUM_THRESHOLD_DAYS:
        return (
            ConfidenceLevel.MEDIUM,
            f"{sample_size} trading days of history (< 1 year, >= 3 months)",
        )
    return (
        ConfidenceLevel.LOW,
        f"only {sample_size} trading days of history (< 3 months) -- treat with caution",
    )

"""Return calculations. Everything else in this package that needs a return
series (alpha/beta, VaR, correlation) composes with `daily_returns` rather
than recomputing it, so there's exactly one definition of "return" in the
whole service.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from ..confidence import confidence_from_sample_size
from ..models import PrimitiveResult
from ..pipeline_versions import RETURNS_V1


def daily_returns(prices: pd.Series) -> pd.Series:
    """Simple daily returns from a price series indexed by date."""
    return prices.sort_index().pct_change().dropna()


def compute_period_return(prices: pd.Series) -> PrimitiveResult:
    """Total return over the full span of the supplied price series."""
    prices = prices.sort_index()
    sample_size = len(prices)
    confidence, reason = confidence_from_sample_size(sample_size)

    if sample_size < 2:
        return PrimitiveResult(
            name="period_return",
            value=None,
            computed_at=datetime.now(timezone.utc),
            pipeline_version=RETURNS_V1,
            input_as_of=prices.index.max().date() if sample_size else date.today(),
            confidence=confidence,
            confidence_reason="insufficient history to compute a period return",
            sample_size=sample_size,
        )

    total_return = float(prices.iloc[-1] / prices.iloc[0] - 1)

    return PrimitiveResult(
        name="period_return",
        value=round(total_return, 4),
        computed_at=datetime.now(timezone.utc),
        pipeline_version=RETURNS_V1,
        input_as_of=prices.index.max().date(),
        confidence=confidence,
        confidence_reason=reason,
        sample_size=sample_size,
    )

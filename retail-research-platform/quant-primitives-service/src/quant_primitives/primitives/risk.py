"""Alpha, beta, and Value-at-Risk -- the "how does this hold up against risk"
primitives referenced throughout docs/product-architecture.md's Stock and
Mutual Fund domains (Section 5).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ..confidence import confidence_from_sample_size
from ..models import PrimitiveResult
from ..pipeline_versions import ALPHA_BETA_V1, VAR_HISTORICAL_V1
from .returns import daily_returns

TRADING_DAYS_PER_YEAR = 252


def compute_alpha_beta(
    asset_prices: pd.Series,
    benchmark_prices: pd.Series,
    risk_free_rate_annual: float = 0.065,
) -> PrimitiveResult:
    """Jensen's alpha and CAPM beta against a benchmark.

    Beta = Cov(asset, benchmark) / Var(benchmark).
    Alpha = annualized asset return - [risk-free + beta * (annualized
    benchmark return - risk-free)] -- the return the asset delivered above
    what CAPM would have predicted given its beta.

    Only overlapping dates between the two series are used, and the sample
    size of that overlap (not either series' raw length) is what confidence
    is computed from -- a five-year-old stock compared against a
    six-month-old benchmark series is still a six-month estimate.
    """
    asset_returns = daily_returns(asset_prices)
    benchmark_returns = daily_returns(benchmark_prices)
    aligned = pd.concat(
        [asset_returns.rename("asset"), benchmark_returns.rename("benchmark")],
        axis=1,
    ).dropna()

    sample_size = len(aligned)
    confidence, reason = confidence_from_sample_size(sample_size)

    if sample_size < 2:
        fallback_date = (
            aligned.index.max().date()
            if sample_size
            else asset_prices.sort_index().index.max().date()
        )
        return PrimitiveResult(
            name="alpha_beta",
            value=None,
            computed_at=datetime.now(timezone.utc),
            pipeline_version=ALPHA_BETA_V1,
            input_as_of=fallback_date,
            confidence=confidence,
            confidence_reason="insufficient overlapping history with the benchmark to compute beta",
            sample_size=sample_size,
        )

    benchmark_variance = aligned["benchmark"].var()
    if not benchmark_variance:
        return PrimitiveResult(
            name="alpha_beta",
            value=None,
            computed_at=datetime.now(timezone.utc),
            pipeline_version=ALPHA_BETA_V1,
            input_as_of=aligned.index.max().date(),
            confidence=confidence,
            confidence_reason="benchmark shows zero variance over the overlapping window -- beta is undefined",
            sample_size=sample_size,
        )

    covariance = aligned["asset"].cov(aligned["benchmark"])
    beta_value = covariance / benchmark_variance

    asset_mean_annual = aligned["asset"].mean() * TRADING_DAYS_PER_YEAR
    benchmark_mean_annual = aligned["benchmark"].mean() * TRADING_DAYS_PER_YEAR
    expected_return = risk_free_rate_annual + beta_value * (
        benchmark_mean_annual - risk_free_rate_annual
    )
    alpha_value = asset_mean_annual - expected_return

    return PrimitiveResult(
        name="alpha_beta",
        value={"alpha": round(float(alpha_value), 4), "beta": round(float(beta_value), 4)},
        computed_at=datetime.now(timezone.utc),
        pipeline_version=ALPHA_BETA_V1,
        input_as_of=aligned.index.max().date(),
        confidence=confidence,
        confidence_reason=reason,
        sample_size=sample_size,
    )


def compute_value_at_risk(
    asset_prices: pd.Series,
    confidence_level: float = 0.95,
    portfolio_value: float = 1.0,
) -> PrimitiveResult:
    """Historical-simulation VaR: the loss at the given confidence level,
    read directly off the empirical distribution of past daily returns
    rather than assuming a normal distribution.

    `confidence_level` is the VaR confidence (e.g. 0.95 for "95% VaR") and is
    independent of the PrimitiveResult's own `confidence` field, which
    reflects how much history backs this estimate, not the VaR threshold
    chosen.
    """
    returns = daily_returns(asset_prices)
    sample_size = len(returns)
    confidence, reason = confidence_from_sample_size(sample_size)

    if sample_size < 2:
        return PrimitiveResult(
            name="value_at_risk",
            value=None,
            computed_at=datetime.now(timezone.utc),
            pipeline_version=VAR_HISTORICAL_V1,
            input_as_of=asset_prices.sort_index().index.max().date(),
            confidence=confidence,
            confidence_reason="insufficient history to compute VaR",
            sample_size=sample_size,
        )

    sorted_returns = returns.sort_values()
    cutoff_index = int((1 - confidence_level) * len(sorted_returns))
    cutoff_index = min(max(cutoff_index, 0), len(sorted_returns) - 1)
    var_return = sorted_returns.iloc[cutoff_index]
    var_amount = -var_return * portfolio_value

    return PrimitiveResult(
        name="value_at_risk",
        value={
            "var_confidence_level": confidence_level,
            "var_amount": round(float(var_amount), 4),
            "portfolio_value": portfolio_value,
        },
        computed_at=datetime.now(timezone.utc),
        pipeline_version=VAR_HISTORICAL_V1,
        input_as_of=returns.index.max().date(),
        confidence=confidence,
        confidence_reason=reason,
        sample_size=sample_size,
    )

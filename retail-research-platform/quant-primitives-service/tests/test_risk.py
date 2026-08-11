import numpy as np
import pandas as pd
import pytest

from quant_primitives.primitives.risk import compute_alpha_beta, compute_value_at_risk


def _prices_from_returns(returns: list[float], start_price: float, periods: int) -> pd.Series:
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=periods)
    growth_factors = [1.0] + [1.0 + r for r in returns]
    prices = start_price * np.cumprod(growth_factors)
    return pd.Series(prices, index=dates)


def test_beta_is_exactly_two_when_asset_return_is_double_benchmark():
    benchmark_returns = [0.01, -0.02, 0.015, 0.02, -0.01]
    asset_returns = [2 * r for r in benchmark_returns]

    benchmark_prices = _prices_from_returns(benchmark_returns, start_price=100.0, periods=6)
    asset_prices = _prices_from_returns(asset_returns, start_price=50.0, periods=6)

    result = compute_alpha_beta(asset_prices, benchmark_prices, risk_free_rate_annual=0.0)

    assert result.value["beta"] == pytest.approx(2.0, abs=1e-6)
    # With risk-free = 0 and asset return exactly 2x benchmark return, CAPM's
    # predicted return exactly matches the realized return -- alpha is 0 by
    # construction, not by coincidence.
    assert result.value["alpha"] == pytest.approx(0.0, abs=1e-6)
    assert result.sample_size == 5


def test_alpha_beta_zero_benchmark_variance_is_undefined_not_a_crash():
    benchmark_prices = _prices_from_returns([0.0, 0.0], start_price=100.0, periods=3)
    asset_prices = _prices_from_returns([0.01, 0.02], start_price=100.0, periods=3)

    result = compute_alpha_beta(asset_prices, benchmark_prices)

    assert result.value is None
    assert "zero variance" in result.confidence_reason


def test_alpha_beta_insufficient_overlap_returns_none():
    benchmark_prices = _prices_from_returns([], start_price=100.0, periods=1)
    asset_prices = _prices_from_returns([], start_price=50.0, periods=1)

    result = compute_alpha_beta(asset_prices, benchmark_prices)

    assert result.value is None
    assert result.sample_size == 0


def test_value_at_risk_picks_correct_percentile_from_empirical_distribution():
    returns = [-0.05, -0.03, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06]
    prices = _prices_from_returns(returns, start_price=100.0, periods=11)

    # 0.75 is exactly representable in binary float (1/4), unlike 0.9 --
    # avoids a floating-point boundary changing which index int() truncates
    # to. cutoff_index = int((1 - 0.75) * 10) = int(2.5) = 2 -> third-
    # smallest return, -0.01.
    result = compute_value_at_risk(prices, confidence_level=0.75, portfolio_value=1000.0)

    assert result.value["var_amount"] == pytest.approx(10.0, abs=0.5)
    assert result.value["var_confidence_level"] == 0.75
    assert result.sample_size == 10


def test_value_at_risk_insufficient_history_returns_none():
    prices = _prices_from_returns([], start_price=100.0, periods=1)
    result = compute_value_at_risk(prices)

    assert result.value is None

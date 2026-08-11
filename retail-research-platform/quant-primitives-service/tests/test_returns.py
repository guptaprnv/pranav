from quant_primitives.models import ConfidenceLevel
from quant_primitives.primitives.returns import compute_period_return, daily_returns


def test_daily_returns_matches_hand_calculation(price_series_factory):
    prices = price_series_factory([100.0, 110.0, 99.0])
    returns = daily_returns(prices)

    assert list(returns.round(6)) == [0.1, -0.1]


def test_period_return_over_full_span(price_series_factory):
    prices = price_series_factory([100.0, 150.0])
    result = compute_period_return(prices)

    assert result.value == 0.5
    assert result.sample_size == 2
    assert result.name == "period_return"
    assert result.input_as_of == prices.index.max().date()


def test_period_return_confidence_reflects_sample_size(price_series_factory):
    short_history = price_series_factory([100.0] * 30)
    result = compute_period_return(short_history)
    assert result.confidence == ConfidenceLevel.LOW

    long_history = price_series_factory([100.0] * 300)
    result = compute_period_return(long_history)
    assert result.confidence == ConfidenceLevel.HIGH


def test_period_return_insufficient_history_returns_none(price_series_factory):
    single_price = price_series_factory([100.0])
    result = compute_period_return(single_price)

    assert result.value is None
    assert "insufficient" in result.confidence_reason

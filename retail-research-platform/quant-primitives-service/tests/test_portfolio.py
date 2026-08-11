from datetime import date

import pandas as pd
import pytest

from quant_primitives.models import ConfidenceLevel
from quant_primitives.primitives.portfolio import (
    compute_concentration,
    compute_correlation_matrix,
    compute_drift,
)


def _series(values: list[float]) -> pd.Series:
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=len(values))
    return pd.Series(values, index=dates)


def test_correlation_matrix_identical_and_inverted_series():
    base_returns = [0.01, -0.02, 0.03, 0.01, -0.01]
    returns_by_entity = {
        "IDENTICAL_A": _series(base_returns),
        "IDENTICAL_B": _series(base_returns),
        "INVERTED": _series([-r for r in base_returns]),
    }

    result = compute_correlation_matrix(returns_by_entity)

    matrix = result.value
    assert matrix["IDENTICAL_A"]["IDENTICAL_B"] == pytest.approx(1.0, abs=1e-6)
    assert matrix["IDENTICAL_A"]["INVERTED"] == pytest.approx(-1.0, abs=1e-6)
    assert result.sample_size == 5


def test_drift_flags_largest_unambiguous_deviation():
    current_weights = {"Auto": 0.35, "IT": 0.10}
    target_weights = {"Auto": 0.20, "IT": 0.20, "Pharma": 0.10}

    result = compute_drift(current_weights, target_weights, as_of=date(2026, 8, 11))

    assert result.value["drift_by_category"] == {"Auto": 0.15, "IT": -0.10, "Pharma": -0.10}
    assert result.value["max_drift_category"] == "Auto"
    assert result.value["max_drift"] == 0.15
    assert result.confidence == ConfidenceLevel.HIGH
    assert result.input_as_of == date(2026, 8, 11)


def test_concentration_hhi_and_top_n():
    weights = {"A": 0.5, "B": 0.3, "C": 0.2}

    result = compute_concentration(weights, as_of=date(2026, 8, 11), top_n=2)

    assert result.value["hhi"] == pytest.approx(0.38)
    assert result.value["largest_weight"] == 0.5
    assert result.value["top_2_weight"] == pytest.approx(0.8)


def test_concentration_hhi_is_lower_for_a_more_diversified_portfolio():
    concentrated = compute_concentration(
        {"A": 0.7, "B": 0.1, "C": 0.1, "D": 0.1}, as_of=date(2026, 8, 11)
    )
    diversified = compute_concentration(
        {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}, as_of=date(2026, 8, 11)
    )

    assert concentrated.value["hhi"] > diversified.value["hhi"]

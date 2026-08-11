from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def price_series_factory():
    """Build a price Series from a plain list of prices, indexed by
    consecutive business days ending today -- lets each test spell out
    exactly the prices it needs without touching the random fixture
    generator, so expected values can be computed by hand.
    """

    def _make(prices: list[float]) -> pd.Series:
        dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=len(prices))
        return pd.Series(prices, index=dates)

    return _make

"""Synthetic, seeded fixture data standing in for a real price/fundamentals
vendor and a real broker/demat holdings feed, per
docs/engineering/data-architecture.md's Phase 1 build note. Both of those
integrations are still open decisions (docs/product-architecture.md, Section
7, Data sources) -- this module is deliberately the only place in the
service that pretends to have already made them.

Deterministic (fixed seed) so tests and the API's fixture store see
identical data across runs, and so a data-quality bug can't hide behind
"the random numbers came out differently."
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SEED = 20260811
TRADING_DAYS = 500  # ~2 years of business days
TRADING_DAYS_PER_YEAR = 252

BENCHMARK_ID = "NIFTY50_FIXTURE"

# entity_id -> reference data. Fake ISINs, deliberately shaped like real ones
# so the entity-graph schema (docs/engineering/data-architecture.md) doesn't
# need to change when real securities replace these.
ENTITIES: dict[str, dict[str, str]] = {
    "INE000A01001": {"name": "Alpha Motors Ltd", "ticker": "ALPHAMOT", "sector": "Auto", "theme": "Auto"},
    "INE000B01002": {"name": "Betaind Steel Ltd", "ticker": "BETAIND", "sector": "Metals", "theme": "China+1"},
    "INE000C01003": {"name": "Gamma Pharma Ltd", "ticker": "GAMMAPHARMA", "sector": "Pharma", "theme": "Healthcare"},
    "INE000D01004": {"name": "Delta Finserv Ltd", "ticker": "DELTAFIN", "sector": "Financials", "theme": "Rate-sensitive"},
    "INE000E01005": {"name": "Epsilon Technologies Ltd", "ticker": "EPSILONTECH", "sector": "IT", "theme": "Export-oriented"},
}

# entity_id -> (annualized drift, annualized volatility) used to simulate a
# geometric random walk for that entity's price history.
_RETURN_PROFILE: dict[str, tuple[float, float]] = {
    "INE000A01001": (0.10, 0.22),
    "INE000B01002": (0.08, 0.30),
    "INE000C01003": (0.14, 0.20),
    "INE000D01004": (0.11, 0.25),
    "INE000E01005": (0.18, 0.28),
}
_START_PRICE = 1000.0
_BENCHMARK_PROFILE = (0.12, 0.15)
_BENCHMARK_START_PRICE = 20000.0


def _random_walk(
    rng: np.random.Generator,
    start_price: float,
    annual_drift: float,
    annual_vol: float,
    days: int,
) -> np.ndarray:
    daily_returns = rng.normal(
        annual_drift / TRADING_DAYS_PER_YEAR,
        annual_vol / np.sqrt(TRADING_DAYS_PER_YEAR),
        days,
    )
    return start_price * np.cumprod(1 + daily_returns)


def generate_price_history() -> pd.DataFrame:
    """A DataFrame indexed by business-day date, one column per entity plus
    the benchmark, of synthetic daily closing prices.
    """
    rng = np.random.default_rng(SEED)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=TRADING_DAYS)

    columns: dict[str, np.ndarray] = {
        BENCHMARK_ID: _random_walk(rng, _BENCHMARK_START_PRICE, *_BENCHMARK_PROFILE, TRADING_DAYS),
    }
    for entity_id, (drift, vol) in _RETURN_PROFILE.items():
        columns[entity_id] = _random_walk(rng, _START_PRICE, drift, vol, TRADING_DAYS)

    return pd.DataFrame(columns, index=dates)


def generate_user_holdings() -> dict[str, float]:
    """Position weights for a single fixture user -- stands in for a real
    broker/demat feed until that integration lands.
    """
    return {
        "INE000A01001": 0.30,
        "INE000B01002": 0.10,
        "INE000C01003": 0.15,
        "INE000D01004": 0.20,
        "INE000E01005": 0.25,
    }


def generate_target_sector_allocation() -> dict[str, float]:
    """A sector-level target allocation to compute drift against."""
    return {
        "Auto": 0.20,
        "Metals": 0.15,
        "Pharma": 0.20,
        "Financials": 0.25,
        "IT": 0.20,
    }


def weights_by_sector(holding_weights: dict[str, float]) -> dict[str, float]:
    """Roll position-level weights up to sector-level weights via the entity
    reference data -- the same kind of rollup the real entity graph
    (docs/engineering/data-architecture.md) will do through the
    Security -> Company -> Sector edges once this is backed by real data.
    """
    sector_weights: dict[str, float] = {}
    for entity_id, weight in holding_weights.items():
        sector = ENTITIES[entity_id]["sector"]
        sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
    return sector_weights

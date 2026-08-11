"""The seam between the primitives and where their input data comes from.

Every other module in this package (primitives/, api/) reads data only
through the functions here -- never by importing quant_primitives.fixtures
directly. That's deliberate: when a real price/fundamentals vendor and a
real broker/demat holdings feed are wired in (docs/product-architecture.md,
Section 7, Data sources; docs/engineering/data-architecture.md's Phase 1
build note), this is the one file that needs to change. The primitive
functions take plain pandas Series and dicts and don't know or care where
they came from.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from .fixtures.generate import (
    BENCHMARK_ID,
    ENTITIES,
    generate_price_history,
    generate_target_sector_allocation,
    generate_user_holdings,
    weights_by_sector,
)


@lru_cache(maxsize=1)
def _price_history() -> pd.DataFrame:
    return generate_price_history()


def get_price_series(entity_id: str) -> pd.Series:
    frame = _price_history()
    if entity_id not in frame.columns:
        raise KeyError(f"unknown entity_id: {entity_id}")
    return frame[entity_id]


def get_benchmark_series() -> pd.Series:
    return _price_history()[BENCHMARK_ID]


def get_user_holdings() -> dict[str, float]:
    return generate_user_holdings()


def get_target_sector_allocation() -> dict[str, float]:
    return generate_target_sector_allocation()


def get_current_sector_weights() -> dict[str, float]:
    return weights_by_sector(get_user_holdings())


def list_entities() -> list[dict[str, str]]:
    return [{"entity_id": entity_id, **info} for entity_id, info in ENTITIES.items()]

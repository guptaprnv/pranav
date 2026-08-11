"""Tier-0-style direct-lookup endpoints (docs/product-architecture.md,
"Query handling & aggregation") -- no LLM anywhere on this path, just the
primitive functions reading fixture data through fixtures_store.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException

from ..fixtures_store import (
    get_benchmark_series,
    get_current_sector_weights,
    get_price_series,
    get_target_sector_allocation,
    get_user_holdings,
    list_entities,
)
from ..models import PrimitiveResult
from ..primitives.portfolio import compute_concentration, compute_correlation_matrix, compute_drift
from ..primitives.returns import compute_period_return, daily_returns
from ..primitives.risk import compute_alpha_beta, compute_value_at_risk

router = APIRouter(prefix="/primitives", tags=["primitives"])


def _get_price_series_or_404(entity_id: str):
    try:
        return get_price_series(entity_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/entities")
def entities() -> list[dict[str, str]]:
    return list_entities()


@router.get("/{entity_id}/return", response_model=PrimitiveResult)
def period_return(entity_id: str) -> PrimitiveResult:
    prices = _get_price_series_or_404(entity_id)
    return compute_period_return(prices)


@router.get("/{entity_id}/alpha-beta", response_model=PrimitiveResult)
def alpha_beta(entity_id: str, risk_free_rate: float = 0.065) -> PrimitiveResult:
    prices = _get_price_series_or_404(entity_id)
    benchmark = get_benchmark_series()
    return compute_alpha_beta(prices, benchmark, risk_free_rate_annual=risk_free_rate)


@router.get("/{entity_id}/var", response_model=PrimitiveResult)
def value_at_risk(
    entity_id: str,
    confidence_level: float = 0.95,
    portfolio_value: float = 1.0,
) -> PrimitiveResult:
    prices = _get_price_series_or_404(entity_id)
    return compute_value_at_risk(
        prices, confidence_level=confidence_level, portfolio_value=portfolio_value
    )


@router.get("/portfolio/correlation", response_model=PrimitiveResult)
def portfolio_correlation() -> PrimitiveResult:
    holdings = get_user_holdings()
    returns_by_entity = {
        entity_id: daily_returns(get_price_series(entity_id)) for entity_id in holdings
    }
    return compute_correlation_matrix(returns_by_entity)


@router.get("/portfolio/drift", response_model=PrimitiveResult)
def portfolio_drift() -> PrimitiveResult:
    current = get_current_sector_weights()
    target = get_target_sector_allocation()
    return compute_drift(current, target, as_of=date.today())


@router.get("/portfolio/concentration", response_model=PrimitiveResult)
def portfolio_concentration(level: str = "position") -> PrimitiveResult:
    if level == "position":
        weights = get_user_holdings()
    elif level == "sector":
        weights = get_current_sector_weights()
    else:
        raise HTTPException(status_code=400, detail="level must be 'position' or 'sector'")
    return compute_concentration(weights, as_of=date.today())

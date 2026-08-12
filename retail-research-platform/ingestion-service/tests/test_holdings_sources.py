from datetime import date

import pytest

from mf_ingestion.holdings.sources import (
    CASPdfSource,
    ScreenshotSource,
    to_unconfirmed_portfolio,
)
from mf_ingestion.models import RawHolding, ResolutionStatus


@pytest.mark.parametrize("source", [ScreenshotSource(), CASPdfSource()])
def test_unbuilt_extractors_fail_loudly_with_what_they_need(source):
    """These are NotImplemented on purpose -- both need real sample data before
    an extractor can be written and measured. The test pins that they say so
    rather than returning empty results, which would look like "user has no
    holdings" to everything downstream.
    """
    with pytest.raises(NotImplementedError) as excinfo:
        source.extract(b"anything")

    assert "needs" in str(excinfo.value).lower()


def test_freshly_extracted_holdings_are_unconfirmed_and_unresolved():
    holdings = [
        RawHolding(scheme_name_raw="Example One Large Cap Fund - Direct Plan - Growth"),
        RawHolding(scheme_name_raw="Example Two Mid-Cap Opportunities Fund"),
    ]

    portfolio = to_unconfirmed_portfolio(holdings, as_of=date(2026, 8, 6))

    assert portfolio.confirmed is False
    assert all(h.status is ResolutionStatus.NEEDS_USER_INPUT for h in portfolio.holdings)


def test_portfolio_is_not_computable_until_confirmed_and_fully_resolved():
    portfolio = to_unconfirmed_portfolio(
        [RawHolding(scheme_name_raw="Example One Large Cap Fund")],
        as_of=date(2026, 8, 6),
    )

    # unconfirmed and unresolved
    assert portfolio.is_ready_to_compute() is False

    # confirming alone is not enough while holdings remain unresolved --
    # the brief's confirmation gate and the resolution gate are separate
    portfolio.confirmed = True
    assert portfolio.is_ready_to_compute() is False
    assert len(portfolio.needs_user_input) == 1

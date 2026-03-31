"""
Contribution ledger — tracks every node's compute contribution
and converts it to training credits.

Key principle: your training quota = what you've given the network.
"""
from .contribution import ContributionLedger, ContributionRecord
from .credits import CreditEngine, CreditBalance
from .quota import QuotaPolicy, QuotaEnforcer

__all__ = [
    "ContributionLedger", "ContributionRecord",
    "CreditEngine", "CreditBalance",
    "QuotaPolicy", "QuotaEnforcer",
]

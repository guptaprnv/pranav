"""
Quota policy — per-user restrictions on training resource usage.

Tiers:
  free        : starter users, limited to free-tier credits, 1 GPU, 1 hour max
  contributor : users who have contributed compute; limits scale with contribution
  power       : top contributors; near-unlimited within cluster capacity

Policy is evaluated by the orchestrator before admitting any job.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .credits import CreditEngine
from .contribution import ContributionLedger

logger = logging.getLogger(__name__)


@dataclass
class QuotaPolicy:
    """Configurable limits per tier."""
    max_gpus: int
    max_nodes: int
    max_job_hours: float
    max_concurrent_jobs: int
    max_queued_jobs: int
    can_use_cloud_backup: bool
    priority_boost: int         # added to base job priority score


# Tier definitions
TIERS: dict[str, QuotaPolicy] = {
    "free": QuotaPolicy(
        max_gpus=1,
        max_nodes=1,
        max_job_hours=1.0,
        max_concurrent_jobs=1,
        max_queued_jobs=2,
        can_use_cloud_backup=False,
        priority_boost=0,
    ),
    "contributor": QuotaPolicy(
        max_gpus=4,
        max_nodes=2,
        max_job_hours=12.0,
        max_concurrent_jobs=2,
        max_queued_jobs=10,
        can_use_cloud_backup=True,
        priority_boost=10,
    ),
    "power": QuotaPolicy(
        max_gpus=32,
        max_nodes=8,
        max_job_hours=72.0,
        max_concurrent_jobs=5,
        max_queued_jobs=50,
        can_use_cloud_backup=True,
        priority_boost=25,
    ),
}

# Contribution thresholds to reach each tier
TIER_THRESHOLDS = {
    "contributor": 3_600,     # 1 GPU-hour equivalent
    "power":       72_000,    # 20 GPU-hours equivalent
}


def resolve_tier(owner_compute_units: float) -> str:
    if owner_compute_units >= TIER_THRESHOLDS["power"]:
        return "power"
    elif owner_compute_units >= TIER_THRESHOLDS["contributor"]:
        return "contributor"
    return "free"


@dataclass
class QuotaCheckResult:
    allowed: bool
    reason: str
    tier: str
    policy: QuotaPolicy


class QuotaEnforcer:
    """
    Evaluates whether a job submission should be allowed given the
    owner's current tier, credit balance, and active job count.
    """

    def __init__(
        self,
        ledger: ContributionLedger,
        credits: CreditEngine,
        redis_url: str = "redis://localhost:6379/0",
    ):
        self.ledger = ledger
        self.credits = credits
        import redis as _redis
        self._r = _redis.Redis.from_url(redis_url, decode_responses=True)

    def check(
        self,
        owner: str,
        num_gpus: int,
        num_nodes: int,
        estimated_hours: float,
    ) -> QuotaCheckResult:
        total_units = self.ledger.owner_total(owner)
        tier = resolve_tier(total_units)
        policy = TIERS[tier]

        # Check credit balance
        credits_needed = estimated_hours * 3600  # 1 credit = 1 second GPU training
        balance = self.credits.balance(owner)

        if balance.available < credits_needed:
            return QuotaCheckResult(
                allowed=False,
                reason=f"Insufficient credits: have {balance.available:.0f}, need {credits_needed:.0f}. "
                       f"Contribute more compute to earn credits.",
                tier=tier,
                policy=policy,
            )

        if num_gpus > policy.max_gpus:
            return QuotaCheckResult(
                allowed=False,
                reason=f"Tier '{tier}' allows max {policy.max_gpus} GPU(s). "
                       f"Contribute more to unlock higher limits.",
                tier=tier,
                policy=policy,
            )

        if num_nodes > policy.max_nodes:
            return QuotaCheckResult(
                allowed=False,
                reason=f"Tier '{tier}' allows max {policy.max_nodes} node(s).",
                tier=tier,
                policy=policy,
            )

        if estimated_hours > policy.max_job_hours:
            return QuotaCheckResult(
                allowed=False,
                reason=f"Tier '{tier}' max job length: {policy.max_job_hours}h.",
                tier=tier,
                policy=policy,
            )

        # Check concurrent jobs
        active = int(self._r.get(f"quota:active:{owner}") or 0)
        if active >= policy.max_concurrent_jobs:
            return QuotaCheckResult(
                allowed=False,
                reason=f"Already running {active} job(s). Tier '{tier}' limit: {policy.max_concurrent_jobs}.",
                tier=tier,
                policy=policy,
            )

        return QuotaCheckResult(allowed=True, reason="ok", tier=tier, policy=policy)

    def increment_active(self, owner: str) -> None:
        self._r.incr(f"quota:active:{owner}")
        self._r.expire(f"quota:active:{owner}", 86400)

    def decrement_active(self, owner: str) -> None:
        val = int(self._r.get(f"quota:active:{owner}") or 0)
        if val > 0:
            self._r.decr(f"quota:active:{owner}")

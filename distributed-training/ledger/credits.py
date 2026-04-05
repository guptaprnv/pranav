"""
Credit engine — converts contribution units into spendable training credits.

Exchange rate:
  1 compute-unit contributed  →  CREDIT_RATE training-credits
  1 training-credit           →  1 second of GPU-equivalent training time

Credits are stored in Redis and debited as jobs run.
New users receive a FREE_TIER_CREDITS starter grant (enough for ~20 minutes).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

import redis

logger = logging.getLogger(__name__)

CREDIT_RATE = 1.2          # credits earned per compute-unit (20% bonus for contributing)
FREE_TIER_CREDITS = 1200   # starter grant: 1200 credits = 20 minutes of GPU training
MAX_CREDITS = 86400 * 7    # cap: can bank up to 7 days of equivalent training time


@dataclass
class CreditBalance:
    owner: str
    available: float
    lifetime_earned: float
    lifetime_spent: float
    last_updated: float

    @property
    def utilization_pct(self) -> float:
        if self.lifetime_earned == 0:
            return 0.0
        return round(self.lifetime_spent / self.lifetime_earned * 100, 1)


class CreditEngine:
    """
    Manages credit balances: earn, spend, and check.

    Thread-safe via Redis atomic operations (INCRBYFLOAT, Lua scripts).
    """

    BALANCE_KEY = "credits:balance:"
    EARNED_KEY = "credits:earned:"
    SPENT_KEY = "credits:spent:"
    TX_LOG_KEY = "credits:txlog:"
    TX_TTL = 86400 * 90    # keep transaction log 90 days

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._r = redis.Redis.from_url(redis_url, decode_responses=True)

    # ------------------------------------------------------------------
    # Earning credits
    # ------------------------------------------------------------------

    def award(self, owner: str, compute_units: float, reason: str = "contribution") -> float:
        """Convert compute units to credits and add to owner's balance."""
        credits = min(compute_units * CREDIT_RATE, MAX_CREDITS)
        self._r.incrbyfloat(f"{self.BALANCE_KEY}{owner}", credits)
        self._r.incrbyfloat(f"{self.EARNED_KEY}{owner}", credits)
        self._log_tx(owner, "earn", credits, reason)
        logger.info(f"Awarded {credits:.2f} credits to {owner} ({reason})")
        return credits

    def grant_free_tier(self, owner: str) -> bool:
        """One-time starter grant for new users. Returns False if already granted."""
        granted_key = f"credits:free_tier_granted:{owner}"
        if self._r.exists(granted_key):
            return False
        self._r.set(granted_key, "1")
        self.award(owner, FREE_TIER_CREDITS / CREDIT_RATE, reason="free_tier_grant")
        logger.info(f"Free tier grant issued to {owner}: {FREE_TIER_CREDITS} credits")
        return True

    # ------------------------------------------------------------------
    # Spending credits
    # ------------------------------------------------------------------

    def reserve(self, owner: str, credits_needed: float, job_id: str) -> bool:
        """
        Atomically reserve credits for a job.
        Returns True if successful, False if insufficient balance.
        """
        script = """
        local balance = tonumber(redis.call('GET', KEYS[1]) or '0')
        local needed = tonumber(ARGV[1])
        if balance < needed then return 0 end
        redis.call('INCRBYFLOAT', KEYS[1], -needed)
        redis.call('INCRBYFLOAT', KEYS[2], needed)
        redis.call('SET', KEYS[3], ARGV[2], 'EX', 86400)
        return 1
        """
        result = self._r.eval(
            script, 3,
            f"{self.BALANCE_KEY}{owner}",
            f"{self.SPENT_KEY}{owner}",
            f"credits:reserved:{job_id}",
            credits_needed,
            json.dumps({"owner": owner, "job_id": job_id, "credits": credits_needed}),
        )
        if result == 1:
            self._log_tx(owner, "reserve", credits_needed, f"job:{job_id}")
            return True
        logger.warning(f"Insufficient credits for {owner}: need {credits_needed:.1f}")
        return False

    def release_reservation(self, owner: str, job_id: str, used_credits: float) -> None:
        """
        Called when a job finishes.
        Refunds unused reserved credits (reserved - actually used).
        """
        reserved_key = f"credits:reserved:{job_id}"
        raw = self._r.get(reserved_key)
        if not raw:
            return
        reserved = json.loads(raw)["credits"]
        refund = max(0.0, reserved - used_credits)
        if refund > 0:
            self._r.incrbyfloat(f"{self.BALANCE_KEY}{owner}", refund)
            self._r.incrbyfloat(f"{self.SPENT_KEY}{owner}", -refund)
        self._r.delete(reserved_key)
        self._log_tx(owner, "settle", used_credits, f"job:{job_id} refund:{refund:.2f}")

    # ------------------------------------------------------------------
    # Balance inquiry
    # ------------------------------------------------------------------

    def balance(self, owner: str) -> CreditBalance:
        avail = float(self._r.get(f"{self.BALANCE_KEY}{owner}") or 0)
        earned = float(self._r.get(f"{self.EARNED_KEY}{owner}") or 0)
        spent = float(self._r.get(f"{self.SPENT_KEY}{owner}") or 0)
        return CreditBalance(
            owner=owner,
            available=round(avail, 2),
            lifetime_earned=round(earned, 2),
            lifetime_spent=round(spent, 2),
            last_updated=time.time(),
        )

    def can_afford(self, owner: str, seconds: float) -> bool:
        """Check if owner has enough credits for `seconds` of GPU training."""
        return self.balance(owner).available >= seconds

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _log_tx(self, owner: str, tx_type: str, amount: float, note: str) -> None:
        entry = json.dumps({
            "ts": time.time(), "type": tx_type,
            "amount": round(amount, 4), "note": note,
        })
        self._r.lpush(f"{self.TX_LOG_KEY}{owner}", entry)
        self._r.ltrim(f"{self.TX_LOG_KEY}{owner}", 0, 999)  # keep last 1000 transactions

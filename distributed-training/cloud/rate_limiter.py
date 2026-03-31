"""
Per-user cloud rate limiter — uses a token bucket algorithm in Redis.

Bandwidth limits by tier:
  free        :   100 MB/day upload,   500 MB/day download
  contributor :  2 GB/day  upload,    10 GB/day  download
  power       : 20 GB/day  upload,   100 GB/day  download

Checked before every upload/download operation.
"""
from __future__ import annotations

import logging
import time
from typing import Tuple

import redis

from ledger.quota import resolve_tier, TIERS

logger = logging.getLogger(__name__)

MB = 1024 * 1024
GB = 1024 * MB

UPLOAD_LIMITS = {
    "free":        100 * MB,
    "contributor":   2 * GB,
    "power":        20 * GB,
}
DOWNLOAD_LIMITS = {
    "free":        500 * MB,
    "contributor":  10 * GB,
    "power":       100 * GB,
}


class CloudRateLimiter:
    """
    Token bucket per user per day, stored in Redis.
    Buckets reset at UTC midnight.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._r = redis.Redis.from_url(redis_url, decode_responses=True)

    def check_upload(self, owner: str, size_bytes: int, contribution_units: float) -> Tuple[bool, str]:
        return self._check("upload", owner, size_bytes, contribution_units)

    def check_download(self, owner: str, size_bytes: int, contribution_units: float) -> Tuple[bool, str]:
        return self._check("download", owner, size_bytes, contribution_units)

    def record_upload(self, owner: str, size_bytes: int) -> None:
        self._consume("upload", owner, size_bytes)

    def record_download(self, owner: str, size_bytes: int) -> None:
        self._consume("download", owner, size_bytes)

    def remaining_quota(self, owner: str, contribution_units: float) -> dict:
        tier = resolve_tier(contribution_units)
        up_used = int(self._r.get(self._key("upload", owner)) or 0)
        dn_used = int(self._r.get(self._key("download", owner)) or 0)
        return {
            "tier": tier,
            "upload_used_mb": round(up_used / MB, 1),
            "upload_limit_mb": round(UPLOAD_LIMITS[tier] / MB, 1),
            "upload_remaining_mb": round((UPLOAD_LIMITS[tier] - up_used) / MB, 1),
            "download_used_mb": round(dn_used / MB, 1),
            "download_limit_mb": round(DOWNLOAD_LIMITS[tier] / MB, 1),
            "download_remaining_mb": round((DOWNLOAD_LIMITS[tier] - dn_used) / MB, 1),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _check(self, direction: str, owner: str, size_bytes: int, units: float) -> Tuple[bool, str]:
        tier = resolve_tier(units)
        limit = UPLOAD_LIMITS[tier] if direction == "upload" else DOWNLOAD_LIMITS[tier]
        used = int(self._r.get(self._key(direction, owner)) or 0)
        if used + size_bytes > limit:
            remaining = max(0, limit - used)
            return False, (
                f"Daily {direction} quota exceeded for tier '{tier}'. "
                f"Remaining: {remaining // MB}MB. "
                f"Contribute more compute to increase your limit."
            )
        return True, "ok"

    def _consume(self, direction: str, owner: str, size_bytes: int) -> None:
        key = self._key(direction, owner)
        pipe = self._r.pipeline()
        pipe.incrby(key, size_bytes)
        pipe.expireat(key, self._next_midnight())
        pipe.execute()

    @staticmethod
    def _key(direction: str, owner: str) -> str:
        day = time.strftime("%Y%m%d")
        return f"cloud_rate:{direction}:{owner}:{day}"

    @staticmethod
    def _next_midnight() -> int:
        import datetime
        now = datetime.datetime.utcnow()
        midnight = (now + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return int(midnight.timestamp())

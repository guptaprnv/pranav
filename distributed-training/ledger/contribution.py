"""
Contribution tracker — records compute time donated by each peer.

Contribution is measured in "compute-seconds" normalized by hardware tier:
  GPU-second (A100-class)  = 1.0 unit
  GPU-second (consumer)    = 0.5 unit
  Apple Silicon (M2/M3)    = 0.3 unit
  iPad Neural Engine       = 0.1 unit
  CPU-second               = 0.02 unit

This means a Mac mini M3 contributing 1 hour earns:
  3600 * 0.3 = 1080 compute-units → can run 1080s of GPU-equivalent training

All data persisted in Redis; compacted to daily summaries after 7 days.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import redis

logger = logging.getLogger(__name__)

# Hardware tier multipliers (normalized to A100 = 1.0)
TIER_MULTIPLIERS = {
    "a100":        1.00,
    "h100":        2.00,
    "v100":        0.60,
    "rtx4090":     0.55,
    "rtx3090":     0.40,
    "apple_m3":    0.35,
    "apple_m2":    0.28,
    "apple_m1":    0.20,
    "ipad_m2":     0.12,
    "ipad_m1":     0.08,
    "ipad_neural": 0.05,
    "cpu_server":  0.03,
    "cpu_laptop":  0.01,
    "unknown":     0.10,
}


@dataclass
class ContributionRecord:
    peer_id: str
    owner: str                  # username / email
    session_id: str
    start_ts: float
    end_ts: float
    hardware_tier: str
    compute_units_earned: float   # normalized units
    task_type: str              # "training" | "inference" | "validation"
    job_id: Optional[str] = None

    @property
    def duration_seconds(self) -> float:
        return self.end_ts - self.start_ts

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ContributionRecord:
        return cls(**d)


class ContributionLedger:
    """
    Append-only log of every compute session contributed by each peer.
    Provides per-owner totals, peer totals, and time-series summaries.
    """

    SESSION_PREFIX = "contrib:session:"
    OWNER_TOTAL_KEY = "contrib:owner_total:"
    PEER_TOTAL_KEY = "contrib:peer_total:"
    HISTORY_KEY = "contrib:history:"     # sorted set: score=ts, member=session_id
    SESSION_TTL = 86400 * 30            # 30 days

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._r = redis.Redis.from_url(redis_url, decode_responses=True)

    # ------------------------------------------------------------------
    # Recording contributions
    # ------------------------------------------------------------------

    def start_session(
        self,
        peer_id: str,
        owner: str,
        hardware_tier: str,
        task_type: str = "training",
        job_id: Optional[str] = None,
    ) -> str:
        import uuid
        session_id = str(uuid.uuid4())[:12]
        # Store pending session
        self._r.setex(
            f"{self.SESSION_PREFIX}{session_id}",
            self.SESSION_TTL,
            json.dumps({
                "peer_id": peer_id, "owner": owner,
                "session_id": session_id,
                "start_ts": time.time(),
                "end_ts": 0,
                "hardware_tier": hardware_tier,
                "compute_units_earned": 0,
                "task_type": task_type,
                "job_id": job_id,
                "status": "active",
            }),
        )
        logger.info(f"Contribution session started: {session_id} owner={owner} tier={hardware_tier}")
        return session_id

    def end_session(self, session_id: str) -> Optional[ContributionRecord]:
        key = f"{self.SESSION_PREFIX}{session_id}"
        raw = self._r.get(key)
        if not raw:
            logger.warning(f"Session {session_id} not found")
            return None

        data = json.loads(raw)
        data["end_ts"] = time.time()
        duration = data["end_ts"] - data["start_ts"]
        multiplier = TIER_MULTIPLIERS.get(data["hardware_tier"], TIER_MULTIPLIERS["unknown"])
        units = duration * multiplier
        data["compute_units_earned"] = units
        data["status"] = "completed"

        pipe = self._r.pipeline()
        pipe.setex(key, self.SESSION_TTL, json.dumps(data))
        pipe.incrbyfloat(f"{self.OWNER_TOTAL_KEY}{data['owner']}", units)
        pipe.incrbyfloat(f"{self.PEER_TOTAL_KEY}{data['peer_id']}", units)
        pipe.zadd(f"{self.HISTORY_KEY}{data['owner']}", {session_id: data["end_ts"]})
        pipe.execute()

        record = ContributionRecord.from_dict(data)
        logger.info(f"Session {session_id} ended: +{units:.2f} units for {data['owner']}")
        return record

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def owner_total(self, owner: str) -> float:
        val = self._r.get(f"{self.OWNER_TOTAL_KEY}{owner}")
        return float(val) if val else 0.0

    def peer_total(self, peer_id: str) -> float:
        val = self._r.get(f"{self.PEER_TOTAL_KEY}{peer_id}")
        return float(val) if val else 0.0

    def owner_history(self, owner: str, limit: int = 50) -> List[ContributionRecord]:
        session_ids = self._r.zrevrange(f"{self.HISTORY_KEY}{owner}", 0, limit - 1)
        records = []
        for sid in session_ids:
            raw = self._r.get(f"{self.SESSION_PREFIX}{sid}")
            if raw:
                records.append(ContributionRecord.from_dict(json.loads(raw)))
        return records

    def leaderboard(self, top_n: int = 20) -> List[Dict]:
        """Return top contributors across all owners."""
        keys = self._r.keys(f"{self.OWNER_TOTAL_KEY}*")
        entries = []
        for k in keys:
            owner = k[len(self.OWNER_TOTAL_KEY):]
            total = float(self._r.get(k) or 0)
            entries.append({"owner": owner, "compute_units": round(total, 2)})
        return sorted(entries, key=lambda x: x["compute_units"], reverse=True)[:top_n]

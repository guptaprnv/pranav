"""
Model state synchronization manager.

Handles:
  - Aggregating gradient updates from all peers (FedAvg)
  - Broadcasting updated model weights to all peers
  - Versioned checkpointing of the global model
  - Staleness detection: stale peers must re-sync before contributing

The sync manager uses a "round" abstraction:
  1. Coordinator collects gradients from all N peers
  2. Runs FedAvg weighted by contribution score
  3. Increments model_version
  4. Broadcasts updated weights
  5. Records which peers participated in this round
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

import redis

logger = logging.getLogger(__name__)


@dataclass
class RoundRecord:
    round_id: int
    job_id: str
    model_version: int
    participant_peer_ids: List[str]
    aggregation_method: str       # "fedavg" | "median" | "trimmed_mean"
    started_at: float
    completed_at: Optional[float] = None
    model_hash: Optional[str] = None  # SHA256 of serialized weights for integrity check
    stale_peers: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class SyncManager:
    """
    Coordinates model version across the peer network.
    Stores global round history in Redis.
    """

    ROUND_PREFIX = "sync:round:"
    VERSION_KEY = "sync:model_version:"
    ROUND_TTL = 86400 * 14

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._r = redis.Redis.from_url(redis_url, decode_responses=True)

    # ------------------------------------------------------------------
    # Round lifecycle
    # ------------------------------------------------------------------

    def start_round(self, job_id: str, peers: List[str]) -> RoundRecord:
        version = self._increment_version(job_id)
        round_id = version
        record = RoundRecord(
            round_id=round_id,
            job_id=job_id,
            model_version=version,
            participant_peer_ids=peers,
            aggregation_method="fedavg",
            started_at=time.time(),
        )
        self._save_round(record)
        logger.info(f"Sync round {round_id} started for job {job_id} with {len(peers)} peers")
        return record

    def complete_round(
        self,
        job_id: str,
        round_id: int,
        model_weights_bytes: bytes,
        stale_peers: Optional[List[str]] = None,
    ) -> RoundRecord:
        record = self._load_round(job_id, round_id)
        if not record:
            raise ValueError(f"Round {round_id} not found for job {job_id}")

        record.completed_at = time.time()
        record.model_hash = hashlib.sha256(model_weights_bytes).hexdigest()
        record.stale_peers = stale_peers or []
        self._save_round(record)

        elapsed = record.completed_at - record.started_at
        logger.info(
            f"Sync round {round_id} completed in {elapsed:.2f}s | "
            f"hash={record.model_hash[:16]} stale_peers={len(record.stale_peers)}"
        )
        return record

    # ------------------------------------------------------------------
    # Staleness detection
    # ------------------------------------------------------------------

    def is_peer_stale(self, job_id: str, peer_version: int) -> bool:
        current = self.current_version(job_id)
        # Allow peers to be 1 round behind (network lag tolerance)
        return peer_version < current - 1

    def current_version(self, job_id: str) -> int:
        val = self._r.get(f"{self.VERSION_KEY}{job_id}")
        return int(val) if val else 0

    # ------------------------------------------------------------------
    # Aggregation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def fedavg(
        gradient_dicts: List[Dict[str, list]],
        weights: Optional[List[float]] = None,
    ) -> Dict[str, list]:
        """
        Weighted FedAvg.
        gradient_dicts: list of {layer_name: [grad_values]}
        weights: contribution weights per peer (defaults to uniform)
        """
        if not gradient_dicts:
            return {}
        n = len(gradient_dicts)
        w = weights if weights and len(weights) == n else [1.0 / n] * n
        total_w = sum(w)
        w = [x / total_w for x in w]

        averaged: Dict[str, list] = {}
        for peer_grads, peer_w in zip(gradient_dicts, w):
            for layer, grads in peer_grads.items():
                if layer not in averaged:
                    averaged[layer] = [0.0] * len(grads)
                averaged[layer] = [a + peer_w * g for a, g in zip(averaged[layer], grads)]
        return averaged

    @staticmethod
    def verify_integrity(weights_bytes: bytes, expected_hash: str) -> bool:
        actual = hashlib.sha256(weights_bytes).hexdigest()
        return actual == expected_hash

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _increment_version(self, job_id: str) -> int:
        return int(self._r.incr(f"{self.VERSION_KEY}{job_id}"))

    def _save_round(self, record: RoundRecord) -> None:
        key = f"{self.ROUND_PREFIX}{record.job_id}:{record.round_id}"
        self._r.setex(key, self.ROUND_TTL, json.dumps(record.to_dict()))

    def _load_round(self, job_id: str, round_id: int) -> Optional[RoundRecord]:
        key = f"{self.ROUND_PREFIX}{job_id}:{round_id}"
        raw = self._r.get(key)
        if not raw:
            return None
        d = json.loads(raw)
        return RoundRecord(**d)

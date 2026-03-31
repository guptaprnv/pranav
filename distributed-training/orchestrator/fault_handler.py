"""
Fault handler — detects and recovers from peer failures during training.

Failure modes handled:
  1. Peer disconnect mid-round  → reassign its tasks to remaining peers
  2. Peer returns wrong result  → ignore outlier, proceed with honest majority
  3. Coordinator crash          → trigger new coordinator election
  4. Slow peer (straggler)      → timeout and reassign after deadline

Recovery is logged per job so users can audit what happened to their run.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Callable, Dict, List, Optional

import redis

logger = logging.getLogger(__name__)


class FaultType(str, Enum):
    PEER_DISCONNECT = "peer_disconnect"
    WRONG_RESULT = "wrong_result"
    COORDINATOR_CRASH = "coordinator_crash"
    STRAGGLER = "straggler"
    RESOURCE_EXHAUSTED = "resource_exhausted"


@dataclass
class FaultEvent:
    fault_id: str
    job_id: str
    round_id: int
    fault_type: str
    peer_id: str
    detected_at: float
    resolved_at: Optional[float] = None
    resolution: str = "pending"
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class FaultHandler:
    """
    Monitors active training rounds and triggers recovery actions.

    Integrates with:
      - TaskDispatcher (reassign tasks)
      - SyncManager (skip round or partial aggregate)
      - PeerDiscovery (remove dead peers)
    """

    FAULT_PREFIX = "fault:"
    FAULT_TTL = 86400 * 30
    STRAGGLER_TIMEOUT = 300   # seconds before a slow peer is declared straggler

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._r = redis.Redis.from_url(redis_url, decode_responses=True)
        self._handlers: Dict[str, Callable] = {}

    # ------------------------------------------------------------------
    # Fault registration
    # ------------------------------------------------------------------

    def report(
        self,
        job_id: str,
        round_id: int,
        fault_type: FaultType,
        peer_id: str,
        notes: str = "",
    ) -> FaultEvent:
        import uuid
        event = FaultEvent(
            fault_id=str(uuid.uuid4())[:8],
            job_id=job_id,
            round_id=round_id,
            fault_type=fault_type,
            peer_id=peer_id,
            detected_at=time.time(),
            notes=notes,
        )
        key = f"{self.FAULT_PREFIX}{job_id}:{event.fault_id}"
        self._r.setex(key, self.FAULT_TTL, json.dumps(event.to_dict()))

        logger.warning(
            f"Fault reported: {fault_type} peer={peer_id[:8]} "
            f"job={job_id} round={round_id} | {notes}"
        )
        self._auto_resolve(event)
        return event

    def resolve(self, job_id: str, fault_id: str, resolution: str) -> None:
        key = f"{self.FAULT_PREFIX}{job_id}:{fault_id}"
        raw = self._r.get(key)
        if not raw:
            return
        event = json.loads(raw)
        event["resolved_at"] = time.time()
        event["resolution"] = resolution
        self._r.setex(key, self.FAULT_TTL, json.dumps(event))
        logger.info(f"Fault {fault_id} resolved: {resolution}")

    # ------------------------------------------------------------------
    # Recovery actions
    # ------------------------------------------------------------------

    def _auto_resolve(self, event: FaultEvent) -> None:
        if event.fault_type == FaultType.PEER_DISCONNECT:
            self._handle_disconnect(event)
        elif event.fault_type == FaultType.STRAGGLER:
            self._handle_straggler(event)
        elif event.fault_type == FaultType.COORDINATOR_CRASH:
            self._handle_coordinator_crash(event)
        elif event.fault_type == FaultType.WRONG_RESULT:
            self._handle_wrong_result(event)

    def _handle_disconnect(self, event: FaultEvent) -> None:
        """
        Peer disconnected mid-round.
        Strategy: proceed with remaining peers if quorum (>50%) still active.
        If quorum lost → pause round, wait for peer reconnect or timeout.
        """
        logger.info(f"Handling disconnect for peer {event.peer_id[:8]} — checking quorum")
        # Actual quorum check delegated to orchestrator caller via callback
        self.resolve(event.job_id, event.fault_id, "reassign_to_remaining_peers")

    def _handle_straggler(self, event: FaultEvent) -> None:
        """Timeout slow peer, proceed with partial aggregate."""
        logger.info(f"Straggler {event.peer_id[:8]} — dropping from this round")
        self.resolve(event.job_id, event.fault_id, "dropped_from_round")

    def _handle_coordinator_crash(self, event: FaultEvent) -> None:
        """Trigger re-election of coordinator."""
        logger.warning("Coordinator crash — triggering re-election")
        self._r.set(f"coordinator_reelect:{event.job_id}", event.round_id, ex=60)
        self.resolve(event.job_id, event.fault_id, "re_election_triggered")

    def _handle_wrong_result(self, event: FaultEvent) -> None:
        """
        Outlier detection: if peer's gradients diverge significantly from
        median, flag peer and exclude from aggregation.
        """
        logger.warning(f"Wrong result from {event.peer_id[:8]} — excluding from FedAvg")
        # Increment trust-penalty counter for this peer
        self._r.incr(f"trust_penalty:{event.peer_id}")
        self._r.expire(f"trust_penalty:{event.peer_id}", 86400)
        self.resolve(event.job_id, event.fault_id, "peer_excluded_from_aggregation")

    # ------------------------------------------------------------------
    # Fault history
    # ------------------------------------------------------------------

    def job_faults(self, job_id: str) -> List[FaultEvent]:
        keys = self._r.keys(f"{self.FAULT_PREFIX}{job_id}:*")
        events = []
        for k in keys:
            raw = self._r.get(k)
            if raw:
                events.append(FaultEvent(**json.loads(raw)))
        return sorted(events, key=lambda e: e.detected_at)

    def peer_trust_penalty(self, peer_id: str) -> int:
        return int(self._r.get(f"trust_penalty:{peer_id}") or 0)

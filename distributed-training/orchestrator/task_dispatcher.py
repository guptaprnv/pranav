"""
Task dispatcher — assigns training micro-tasks to available peers
based on their hardware tier and current contribution score.

Dispatch strategies:
  "capability"  : best hardware gets the most compute-intensive tasks
  "round_robin" : fair rotation regardless of hardware (for testing)
  "weighted"    : probability proportional to contribution score

The dispatcher is run by whoever is the current "coordinator" peer —
a role that rotates every N rounds to avoid single-point-of-failure.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from p2p.peer import PeerInfo
from ledger.contribution import TIER_MULTIPLIERS

logger = logging.getLogger(__name__)


class DispatchStrategy(str, Enum):
    CAPABILITY = "capability"
    ROUND_ROBIN = "round_robin"
    WEIGHTED = "weighted"


@dataclass
class MicroTask:
    """Smallest unit of work assigned to a single peer."""
    task_id: str
    job_id: str
    task_type: str          # "forward" | "backward" | "validation" | "data_shard"
    shard_ids: List[int]    # data shard indices assigned to this peer
    model_version: int
    assigned_peer: Optional[str] = None
    assigned_at: Optional[float] = None
    completed_at: Optional[float] = None
    status: str = "pending"
    retries: int = 0


@dataclass
class DispatchPlan:
    job_id: str
    round_id: int
    tasks: List[MicroTask]
    coordinator_peer_id: str
    created_at: float = field(default_factory=time.time)


class TaskDispatcher:
    """
    Builds and tracks dispatch plans for a training job across a peer set.
    """

    MAX_RETRIES = 3

    def __init__(
        self,
        local_peer_id: str,
        strategy: DispatchStrategy = DispatchStrategy.CAPABILITY,
    ):
        self.local_peer_id = local_peer_id
        self.strategy = strategy
        self._active_tasks: Dict[str, MicroTask] = {}  # task_id → MicroTask

    def build_plan(
        self,
        job_id: str,
        round_id: int,
        peers: List[PeerInfo],
        total_shards: int,
    ) -> DispatchPlan:
        """
        Partition `total_shards` data shards across available peers
        according to the chosen strategy.
        """
        if not peers:
            raise ValueError("No peers available for dispatch")

        shard_lists = self._partition_shards(total_shards, peers)
        import uuid
        tasks = []
        for peer, shards in zip(peers, shard_lists):
            if not shards:
                continue
            task = MicroTask(
                task_id=str(uuid.uuid4())[:8],
                job_id=job_id,
                task_type="data_shard",
                shard_ids=shards,
                model_version=round_id,
                assigned_peer=peer.peer_id,
                assigned_at=time.time(),
                status="assigned",
            )
            self._active_tasks[task.task_id] = task
            tasks.append(task)

        plan = DispatchPlan(
            job_id=job_id,
            round_id=round_id,
            tasks=tasks,
            coordinator_peer_id=self.local_peer_id,
        )
        logger.info(
            f"Dispatch plan round={round_id} tasks={len(tasks)} "
            f"strategy={self.strategy} peers={len(peers)}"
        )
        return plan

    def mark_complete(self, task_id: str) -> None:
        if task_id in self._active_tasks:
            self._active_tasks[task_id].status = "completed"
            self._active_tasks[task_id].completed_at = time.time()

    def mark_failed(self, task_id: str) -> Optional[str]:
        """Returns peer_id that needs re-assignment, or None if max retries hit."""
        task = self._active_tasks.get(task_id)
        if not task:
            return None
        task.retries += 1
        if task.retries >= self.MAX_RETRIES:
            task.status = "failed"
            logger.error(f"Task {task_id} exceeded max retries — marking failed")
            return None
        task.status = "retry"
        return task.assigned_peer

    def pending_tasks(self) -> List[MicroTask]:
        return [t for t in self._active_tasks.values() if t.status in ("assigned", "retry")]

    def is_round_complete(self, round_id: int) -> bool:
        round_tasks = [t for t in self._active_tasks.values() if t.model_version == round_id]
        return all(t.status in ("completed", "failed") for t in round_tasks)

    # ------------------------------------------------------------------
    # Partitioning
    # ------------------------------------------------------------------

    def _partition_shards(
        self, total_shards: int, peers: List[PeerInfo]
    ) -> List[List[int]]:
        shards = list(range(total_shards))

        if self.strategy == DispatchStrategy.ROUND_ROBIN:
            return self._round_robin(shards, peers)

        elif self.strategy == DispatchStrategy.CAPABILITY:
            weights = [self._capability_weight(p) for p in peers]
            return self._weighted_partition(shards, peers, weights)

        elif self.strategy == DispatchStrategy.WEIGHTED:
            weights = [max(p.contribution_score, 0.1) for p in peers]
            return self._weighted_partition(shards, peers, weights)

        return self._round_robin(shards, peers)

    @staticmethod
    def _round_robin(shards: List[int], peers: List[PeerInfo]) -> List[List[int]]:
        result: List[List[int]] = [[] for _ in peers]
        for i, s in enumerate(shards):
            result[i % len(peers)].append(s)
        return result

    @staticmethod
    def _weighted_partition(
        shards: List[int], peers: List[PeerInfo], weights: List[float]
    ) -> List[List[int]]:
        total_w = sum(weights)
        counts = [max(1, round(w / total_w * len(shards))) for w in weights]
        # Adjust for rounding
        diff = len(shards) - sum(counts)
        counts[0] += diff
        result = []
        idx = 0
        for c in counts:
            result.append(shards[idx: idx + c])
            idx += c
        return result

    @staticmethod
    def _capability_weight(peer: PeerInfo) -> float:
        """Higher-tier hardware gets proportionally more shards."""
        gpu_score = peer.gpu_count * 10.0
        mem_score = peer.memory_gb * 0.1
        return max(gpu_score + mem_score, 1.0)

    @staticmethod
    def elect_coordinator(peers: List[PeerInfo]) -> Optional[str]:
        """
        Deterministic coordinator election: peer with highest contribution_score.
        Ties broken by peer_id lexicographic order (stable across the network).
        """
        if not peers:
            return None
        return max(peers, key=lambda p: (p.contribution_score, p.peer_id)).peer_id

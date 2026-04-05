"""
Placement planner and assignment store for multi-peer launches.

This is the first control-plane pass:
  - choose a compatible set of nodes for a job
  - reserve per-node slots/resources
  - enqueue one launch assignment per selected peer
  - aggregate per-peer completion back into job status
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from src.scheduler.job_queue import Job, JobQueue
from src.scheduler.resource_manager import Allocation, ResourceManager


@dataclass
class NodePlacement:
    peer_id: str
    hostname: str
    ip: str
    node_rank: int
    assigned_slots: int
    accelerator_family: str
    hardware_tier: str
    allocation_id: str


@dataclass
class PlacementPlan:
    job_id: str
    owner: str
    config_path: str
    world_size: int
    nnodes: int
    backend_family: str
    master_peer_id: str
    master_addr: str
    master_port: int
    placements: List[NodePlacement]
    created_at: float = field(default_factory=time.time)

    def to_json(self) -> str:
        payload = asdict(self)
        payload["placements"] = [asdict(p) for p in self.placements]
        return json.dumps(payload)

    @classmethod
    def from_json(cls, raw: str) -> "PlacementPlan":
        data = json.loads(raw)
        data["placements"] = [NodePlacement(**p) for p in data["placements"]]
        return cls(**data)


@dataclass
class LaunchAssignment:
    job_id: str
    job_name: str
    owner: str
    config_path: str
    peer_id: str
    node_rank: int
    nnodes: int
    world_size: int
    local_world_size: int
    global_rank_offset: int
    master_addr: str
    master_port: int
    backend_family: str
    allocation_id: str

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "LaunchAssignment":
        return cls(**json.loads(raw))


@dataclass
class AssignmentResult:
    job_id: str
    peer_id: str
    success: bool
    error: str = ""
    completed_at: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class PlacementPlanner:
    PLAN_KEY = "placement:plan:"

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.resource_manager = ResourceManager(redis_url=redis_url)
        self.job_queue = JobQueue(redis_url=redis_url)

    def dispatch_job(self, job: Job) -> Optional[PlacementPlan]:
        plan = self.plan_job(job)
        if not plan:
            return None

        assignments: List[LaunchAssignment] = []
        rank_offset = 0
        for placement in plan.placements:
            assignments.append(
                LaunchAssignment(
                    job_id=job.job_id,
                    job_name=job.job_name,
                    owner=job.owner,
                    config_path=job.config_path,
                    peer_id=placement.peer_id,
                    node_rank=placement.node_rank,
                    nnodes=plan.nnodes,
                    world_size=plan.world_size,
                    local_world_size=placement.assigned_slots,
                    global_rank_offset=rank_offset,
                    master_addr=plan.master_addr,
                    master_port=plan.master_port,
                    backend_family=plan.backend_family,
                    allocation_id=placement.allocation_id,
                )
            )
            rank_offset += placement.assigned_slots

        self._store_plan(plan)
        for assignment in assignments:
            self._enqueue_assignment(assignment)

        self.job_queue.start_job(job.job_id)
        return plan

    def dispatch_pending_jobs(self, limit: int = 10) -> List[str]:
        dispatched: List[str] = []
        for job in self.job_queue.list_pending()[:limit]:
            plan = self.dispatch_job(job)
            if plan:
                dispatched.append(job.job_id)
        return dispatched

    def plan_job(self, job: Job) -> Optional[PlacementPlan]:
        nodes = self.resource_manager.list_nodes()
        required_slots = max(job.num_gpus, job.num_nodes, 1)
        min_nodes = max(job.num_nodes, 1)

        grouped: Dict[str, List[dict]] = {}
        for node in nodes:
            free_slots = node["total_slots"] - node["used_slots"]
            if free_slots <= 0:
                continue
            family = node.get("accelerator_family", "cpu")
            grouped.setdefault(family, []).append(node)

        for family in ("cuda", "mps", "cpu"):
            candidates = grouped.get(family, [])
            plan = self._plan_for_family(job, candidates, family, required_slots, min_nodes)
            if plan:
                return plan
        return None

    def _plan_for_family(
        self,
        job: Job,
        candidates: List[dict],
        family: str,
        required_slots: int,
        min_nodes: int,
    ) -> Optional[PlacementPlan]:
        if len(candidates) < min_nodes:
            return None

        candidates = sorted(
            candidates,
            key=lambda n: (
                n["total_slots"] - n["used_slots"],
                n["total_memory_gb"] - n["used_memory_gb"],
                n["total_cpus"] - n["used_cpus"],
            ),
            reverse=True,
        )
        if sum(n["total_slots"] - n["used_slots"] for n in candidates) < required_slots:
            return None

        placements: List[NodePlacement] = []
        selected: List[dict] = []
        slots_available = 0
        for node in candidates:
            selected.append(node)
            slots_available += node["total_slots"] - node["used_slots"]
            if len(selected) >= min_nodes and slots_available >= required_slots:
                break
        if len(selected) < min_nodes or slots_available < required_slots:
            return None

        remaining = required_slots
        assigned = {node["node_id"]: 0 for node in selected}

        for node in selected:
            assigned[node["node_id"]] = 1
            remaining -= 1

        idx = 0
        while remaining > 0:
            node = selected[idx % len(selected)]
            free_slots = node["total_slots"] - node["used_slots"]
            if assigned[node["node_id"]] < free_slots:
                assigned[node["node_id"]] += 1
                remaining -= 1
            idx += 1
            if idx > required_slots * max(len(selected), 1) * 2:
                return None

        master = selected[0]
        master_addr = master.get("ip") or "127.0.0.1"
        master_port = random.randint(29500, 29999)
        world_size = sum(assigned.values())

        for node_rank, node in enumerate(selected):
            slots = assigned[node["node_id"]]
            alloc = self.resource_manager.reserve_node(
                node_id=node["node_id"],
                job_id=job.job_id,
                slots_needed=slots,
                gpus_needed=slots if family == "cuda" else 0,
                cpus_needed=max(1, slots * 2),
                memory_gb_needed=max(4, slots * 4),
            )
            if not alloc:
                for placement in placements:
                    self.resource_manager.release(placement.allocation_id)
                return None

            placements.append(
                NodePlacement(
                    peer_id=node["node_id"],
                    hostname=node["hostname"],
                    ip=node.get("ip", ""),
                    node_rank=node_rank,
                    assigned_slots=slots,
                    accelerator_family=family,
                    hardware_tier=node.get("hardware_tier", "unknown"),
                    allocation_id=alloc.allocation_id,
                )
            )

        return PlacementPlan(
            job_id=job.job_id,
            owner=job.owner,
            config_path=job.config_path,
            world_size=world_size,
            nnodes=len(placements),
            backend_family=family,
            master_peer_id=master["node_id"],
            master_addr=master_addr,
            master_port=master_port,
            placements=placements,
        )

    def _store_plan(self, plan: PlacementPlan) -> None:
        self.job_queue._redis.setex(
            f"{self.PLAN_KEY}{plan.job_id}",
            self.job_queue.JOB_TTL,
            plan.to_json(),
        )

    def _enqueue_assignment(self, assignment: LaunchAssignment) -> None:
        self.job_queue._redis.rpush(
            f"assignments:{assignment.peer_id}",
            assignment.to_json(),
        )


class AssignmentStore:
    PLAN_KEY = PlacementPlanner.PLAN_KEY
    RESULT_KEY = "placement:result:"

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.job_queue = JobQueue(redis_url=redis_url)
        self.resource_manager = ResourceManager(redis_url=redis_url)
        self._redis = self.job_queue._redis

    def pop_assignment(self, peer_id: str) -> Optional[LaunchAssignment]:
        raw = self._redis.lpop(f"assignments:{peer_id}")
        return LaunchAssignment.from_json(raw) if raw else None

    def requeue_assignment(self, assignment: LaunchAssignment) -> None:
        self._redis.lpush(f"assignments:{assignment.peer_id}", assignment.to_json())

    def get_plan(self, job_id: str) -> Optional[PlacementPlan]:
        raw = self._redis.get(f"{self.PLAN_KEY}{job_id}")
        return PlacementPlan.from_json(raw) if raw else None

    def complete_assignment(self, result: AssignmentResult) -> None:
        self._redis.setex(
            f"{self.RESULT_KEY}{result.job_id}:{result.peer_id}",
            self.job_queue.JOB_TTL,
            result.to_json(),
        )

        plan = self.get_plan(result.job_id)
        if not plan:
            return

        completed: List[AssignmentResult] = []
        for placement in plan.placements:
            raw = self._redis.get(f"{self.RESULT_KEY}{result.job_id}:{placement.peer_id}")
            if not raw:
                return
            completed.append(AssignmentResult(**json.loads(raw)))

        for placement in plan.placements:
            self.resource_manager.release(placement.allocation_id)

        success = all(entry.success for entry in completed)
        error = "; ".join(entry.error for entry in completed if entry.error)
        self.job_queue.finish_job(result.job_id, success=success, error=error)

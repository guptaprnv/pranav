"""
Resource manager — tracks GPU/CPU availability across nodes.

Current implementation: in-process with Redis as shared state.
Path to 1000 users: integrate with Kubernetes resource quotas or SLURM.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import redis

logger = logging.getLogger(__name__)


@dataclass
class NodeSpec:
    node_id: str
    hostname: str
    total_gpus: int
    total_cpus: int
    total_memory_gb: int
    gpu_model: str = "unknown"
    ip: str = ""
    hardware_tier: str = "unknown"
    accelerator_family: str = "cpu"
    total_slots: int = 1


@dataclass
class Allocation:
    allocation_id: str
    job_id: str
    node_id: str
    slots: int
    gpus: int
    cpus: int
    memory_gb: int
    allocated_at: float


class ResourceManager:
    """
    Tracks cluster resources and allocates them to jobs.

    Design for scale:
    - All state in Redis → multiple API/scheduler instances share view
    - Allocation is atomic via Redis Lua script (no race conditions)
    - Supports up to 1000 concurrent users by adding nodes
    """

    NODE_TTL = 60          # nodes must heartbeat every 60s or are marked offline
    ALLOC_PREFIX = "alloc:"
    NODE_PREFIX = "node:"

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)

    # ------------------------------------------------------------------
    # Node registration (called by each compute node at startup)
    # ------------------------------------------------------------------

    def register_node(self, spec: NodeSpec) -> None:
        key = f"{self.NODE_PREFIX}{spec.node_id}"
        data = asdict(spec)
        data["total_slots"] = max(1, data.get("total_slots", 1))
        data["registered_at"] = time.time()
        data["used_gpus"] = 0
        data["used_slots"] = 0
        data["used_cpus"] = 0
        data["used_memory_gb"] = 0
        self._redis.setex(key, self.NODE_TTL * 2, json.dumps(data))
        logger.info(f"Node registered: {spec.node_id} ({spec.total_gpus} GPUs)")

    def node_heartbeat(self, node_id: str) -> None:
        self._redis.expire(f"{self.NODE_PREFIX}{node_id}", self.NODE_TTL * 2)

    # ------------------------------------------------------------------
    # Allocation
    # ------------------------------------------------------------------

    def allocate(
        self,
        job_id: str,
        gpus_needed: int,
        cpus_needed: int,
        memory_gb_needed: int,
    ) -> Optional[Allocation]:
        """
        Find a node with enough free resources and allocate atomically.
        Returns None if no node can satisfy the request.
        """
        nodes = self._list_nodes()
        for node in nodes:
            free_gpus = node["total_gpus"] - node["used_gpus"]
            free_cpus = node["total_cpus"] - node["used_cpus"]
            free_mem = node["total_memory_gb"] - node["used_memory_gb"]

            if free_gpus >= gpus_needed and free_cpus >= cpus_needed and free_mem >= memory_gb_needed:
                alloc = self._atomic_allocate(
                    node,
                    job_id,
                    gpus_needed,
                    gpus_needed,
                    cpus_needed,
                    memory_gb_needed,
                )
                if alloc:
                    return alloc

        logger.warning(f"No resources available for job {job_id} "
                       f"(need {gpus_needed} GPUs, {cpus_needed} CPUs, {memory_gb_needed}GB)")
        return None

    def release(self, allocation_id: str) -> None:
        key = f"{self.ALLOC_PREFIX}{allocation_id}"
        raw = self._redis.get(key)
        if not raw:
            return
        alloc = json.loads(raw)
        node_key = f"{self.NODE_PREFIX}{alloc['node_id']}"
        # Atomic release
        script = """
        local node = redis.call('GET', KEYS[1])
        if not node then return 0 end
        local n = cjson.decode(node)
        n['used_slots'] = (n['used_slots'] or 0) - tonumber(ARGV[1])
        n['used_gpus'] = n['used_gpus'] - tonumber(ARGV[2])
        n['used_cpus'] = n['used_cpus'] - tonumber(ARGV[3])
        n['used_memory_gb'] = n['used_memory_gb'] - tonumber(ARGV[4])
        redis.call('SET', KEYS[1], cjson.encode(n), 'KEEPTTL')
        redis.call('DEL', KEYS[2])
        return 1
        """
        self._redis.eval(
            script, 2,
            node_key, key,
            alloc.get("slots", alloc["gpus"]),
            alloc["gpus"],
            alloc["cpus"],
            alloc["memory_gb"],
        )
        logger.info(f"Allocation {allocation_id} released for job {alloc['job_id']}")

    # ------------------------------------------------------------------
    # Cluster view
    # ------------------------------------------------------------------

    def cluster_summary(self) -> Dict:
        nodes = self._list_nodes()
        total_gpus = sum(n["total_gpus"] for n in nodes)
        used_gpus = sum(n["used_gpus"] for n in nodes)
        total_slots = sum(n["total_slots"] for n in nodes)
        used_slots = sum(n["used_slots"] for n in nodes)
        return {
            "nodes_online": len(nodes),
            "total_gpus": total_gpus,
            "used_gpus": used_gpus,
            "free_gpus": total_gpus - used_gpus,
            "utilization_pct": round(used_gpus / max(total_gpus, 1) * 100, 1),
            "total_slots": total_slots,
            "used_slots": used_slots,
            "free_slots": total_slots - used_slots,
        }

    def list_nodes(self) -> List[dict]:
        """Public node listing for placement planners and inspection APIs."""
        return self._list_nodes()

    def reserve_node(
        self,
        node_id: str,
        job_id: str,
        slots_needed: int,
        gpus_needed: int,
        cpus_needed: int,
        memory_gb_needed: int,
    ) -> Optional[Allocation]:
        node_key = f"{self.NODE_PREFIX}{node_id}"
        raw = self._redis.get(node_key)
        if not raw:
            return None
        node = json.loads(raw)
        return self._atomic_allocate(node, job_id, slots_needed, gpus_needed, cpus_needed, memory_gb_needed)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _list_nodes(self) -> List[dict]:
        keys = self._redis.keys(f"{self.NODE_PREFIX}*")
        nodes = []
        for k in keys:
            raw = self._redis.get(k)
            if raw:
                node = json.loads(raw)
                node.setdefault("total_slots", max(node.get("total_gpus", 0), 1))
                node.setdefault("used_slots", node.get("used_gpus", 0))
                node.setdefault("accelerator_family", "cpu")
                node.setdefault("hardware_tier", "unknown")
                node.setdefault("ip", "")
                nodes.append(node)
        return nodes

    def _atomic_allocate(
        self,
        node: dict,
        job_id: str,
        slots: int,
        gpus: int,
        cpus: int,
        memory_gb: int,
    ) -> Optional[Allocation]:
        import uuid
        alloc_id = str(uuid.uuid4())[:8]
        node_key = f"{self.NODE_PREFIX}{node['node_id']}"
        alloc_key = f"{self.ALLOC_PREFIX}{alloc_id}"

        script = """
        local node = redis.call('GET', KEYS[1])
        if not node then return 0 end
        local n = cjson.decode(node)
        local free_slots = (n['total_slots'] or 1) - (n['used_slots'] or 0)
        local free_gpus = n['total_gpus'] - n['used_gpus']
        local free_cpus = n['total_cpus'] - n['used_cpus']
        local free_mem = n['total_memory_gb'] - n['used_memory_gb']
        if free_slots < tonumber(ARGV[1]) then return 0 end
        if free_gpus < tonumber(ARGV[2]) then return 0 end
        if free_cpus < tonumber(ARGV[3]) then return 0 end
        if free_mem < tonumber(ARGV[4]) then return 0 end
        n['used_slots'] = (n['used_slots'] or 0) + tonumber(ARGV[1])
        n['used_gpus'] = n['used_gpus'] + tonumber(ARGV[2])
        n['used_cpus'] = n['used_cpus'] + tonumber(ARGV[3])
        n['used_memory_gb'] = n['used_memory_gb'] + tonumber(ARGV[4])
        redis.call('SET', KEYS[1], cjson.encode(n), 'KEEPTTL')
        redis.call('SETEX', KEYS[2], 86400, ARGV[5])
        return 1
        """
        alloc_data = json.dumps({
            "allocation_id": alloc_id, "job_id": job_id,
            "node_id": node["node_id"], "slots": slots,
            "gpus": gpus,
            "cpus": cpus, "memory_gb": memory_gb,
            "allocated_at": time.time(),
        })
        result = self._redis.eval(
            script,
            2,
            node_key,
            alloc_key,
            slots,
            gpus,
            cpus,
            memory_gb,
            alloc_data,
        )
        if result == 1:
            return Allocation(
                allocation_id=alloc_id, job_id=job_id,
                node_id=node["node_id"], slots=slots, gpus=gpus,
                cpus=cpus, memory_gb=memory_gb,
                allocated_at=time.time(),
            )
        return None

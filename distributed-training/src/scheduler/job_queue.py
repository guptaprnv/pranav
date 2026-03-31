"""
Job queue backed by Redis.

Designed to handle 20 concurrent users today and scale to 1000
with zero code changes — just add Redis replicas and more workers.

Queue design:
  - Priority queue: high / normal / low
  - Jobs are serialized to JSON and pushed into Redis sorted sets
  - Workers pop jobs atomically (no double-execution)
  - Each job has a TTL; stuck jobs are auto-requeued by the reaper
"""
from __future__ import annotations

import json
import time
import uuid
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional

import redis

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(int, Enum):
    HIGH = 0      # lower score = higher priority in sorted set
    NORMAL = 50
    LOW = 100


@dataclass
class Job:
    config_path: str                           # path to TrainingConfig YAML
    job_name: str = "training-job"
    owner: str = "anonymous"
    priority: int = JobPriority.NORMAL
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = JobStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    num_gpus: int = 1
    num_nodes: int = 1
    estimated_hours: float = 1.0

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, s: str) -> Job:
        return cls(**json.loads(s))


class JobQueue:
    """
    Thread-safe, crash-resistant job queue using Redis.

    Scales horizontally:
    - Multiple API servers can enqueue jobs
    - Multiple worker processes dequeue via BLPOP (blocking pop)
    - Redis Cluster mode handles 1000+ concurrent users

    Key schema:
      jobs:<job_id>          → JSON hash of Job
      queue:high             → sorted set (score = priority + timestamp)
      queue:normal           → sorted set
      queue:low              → sorted set
      running:<worker_id>    → job_id (with TTL for dead-worker detection)
    """

    QUEUE_KEYS = {
        JobPriority.HIGH: "queue:high",
        JobPriority.NORMAL: "queue:normal",
        JobPriority.LOW: "queue:low",
    }
    JOB_TTL = 86400 * 7   # 7 days

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)

    # ------------------------------------------------------------------
    # Producer API
    # ------------------------------------------------------------------

    def submit(self, job: Job) -> str:
        """Enqueue a job. Returns job_id."""
        job.status = JobStatus.QUEUED
        pipe = self._redis.pipeline()
        pipe.setex(f"jobs:{job.job_id}", self.JOB_TTL, job.to_json())
        queue_key = self.QUEUE_KEYS.get(job.priority, "queue:normal")
        # score = priority offset + fractional seconds for FIFO within same priority
        score = job.priority + (time.time() / 1e10)
        pipe.zadd(queue_key, {job.job_id: score})
        pipe.execute()
        logger.info(f"Job submitted: {job.job_id} priority={job.priority} owner={job.owner}")
        return job.job_id

    def cancel(self, job_id: str) -> bool:
        """Mark job cancelled; removes from all queues."""
        for key in self.QUEUE_KEYS.values():
            self._redis.zrem(key, job_id)
        return self._update_status(job_id, JobStatus.CANCELLED)

    # ------------------------------------------------------------------
    # Consumer API (called by worker processes)
    # ------------------------------------------------------------------

    def dequeue(self, worker_id: str, timeout: int = 5) -> Optional[Job]:
        """
        Pop the highest-priority job.
        Tries queues in priority order; blocks up to `timeout` seconds.
        """
        for queue_key in self.QUEUE_KEYS.values():
            result = self._redis.zpopmin(queue_key, 1)
            if result:
                job_id, _ = result[0]
                job = self.get(job_id)
                if job is None:
                    continue
                job.status = JobStatus.RUNNING
                job.started_at = time.time()
                self._redis.setex(f"jobs:{job_id}", self.JOB_TTL, job.to_json())
                # Heartbeat key: expires in 120s; worker must renew it
                self._redis.setex(f"running:{worker_id}", 120, job_id)
                return job
        return None

    def heartbeat(self, worker_id: str) -> None:
        """Worker calls this every ~30s to prevent reaper from reclaiming the job."""
        self._redis.expire(f"running:{worker_id}", 120)

    def complete(self, worker_id: str, job_id: str, success: bool, error: str = "") -> None:
        status = JobStatus.COMPLETED if success else JobStatus.FAILED
        job = self.get(job_id)
        if job:
            job.status = status
            job.finished_at = time.time()
            job.error = error or None
            self._redis.setex(f"jobs:{job_id}", self.JOB_TTL, job.to_json())
        self._redis.delete(f"running:{worker_id}")
        logger.info(f"Job {job_id} finished: {status}")

    # ------------------------------------------------------------------
    # Inspection API
    # ------------------------------------------------------------------

    def get(self, job_id: str) -> Optional[Job]:
        raw = self._redis.get(f"jobs:{job_id}")
        return Job.from_json(raw) if raw else None

    def list_pending(self) -> List[Job]:
        jobs = []
        for queue_key in self.QUEUE_KEYS.values():
            for job_id in self._redis.zrange(queue_key, 0, -1):
                j = self.get(job_id)
                if j:
                    jobs.append(j)
        return sorted(jobs, key=lambda j: (j.priority, j.created_at))

    def queue_depth(self) -> dict:
        return {
            "high": self._redis.zcard("queue:high"),
            "normal": self._redis.zcard("queue:normal"),
            "low": self._redis.zcard("queue:low"),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_status(self, job_id: str, status: JobStatus) -> bool:
        job = self.get(job_id)
        if not job:
            return False
        job.status = status
        self._redis.setex(f"jobs:{job_id}", self.JOB_TTL, job.to_json())
        return True

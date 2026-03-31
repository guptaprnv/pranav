"""
FastAPI server — REST interface for submitting and monitoring training jobs.

Designed to handle 20 concurrent users today; scales to 1000 via:
  - Multiple replicas behind a load balancer (see k8s/api-deployment.yaml)
  - Async endpoints (no blocking I/O in request handlers)
  - Redis-backed job queue shared across all replicas
"""
from __future__ import annotations

import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.scheduler.job_queue import JobQueue, Job, JobStatus, JobPriority
from src.scheduler.resource_manager import ResourceManager

app = FastAPI(
    title="Distributed Training API",
    version="0.1.0",
    description="Submit and manage distributed ML training jobs.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten this in production
    allow_methods=["*"],
    allow_headers=["*"],
)

_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def get_queue() -> JobQueue:
    return JobQueue(redis_url=_REDIS_URL)


def get_resource_manager() -> ResourceManager:
    return ResourceManager(redis_url=_REDIS_URL)


# ------------------------------------------------------------------
# Request / response models
# ------------------------------------------------------------------

class SubmitJobRequest(BaseModel):
    job_name: str = Field(..., example="resnet50-imagenet")
    config_path: str = Field(..., example="/configs/medium.yaml",
                              description="Path to TrainingConfig YAML file on the server")
    owner: str = Field("anonymous", example="alice")
    priority: str = Field("normal", example="high", description="high | normal | low")
    num_gpus: int = Field(1, ge=1, le=64)
    num_nodes: int = Field(1, ge=1, le=32)
    estimated_hours: float = Field(1.0, gt=0)


class JobResponse(BaseModel):
    job_id: str
    job_name: str
    status: str
    owner: str
    priority: int
    num_gpus: int
    num_nodes: int
    created_at: float
    started_at: Optional[float]
    finished_at: Optional[float]
    error: Optional[str]


class ClusterSummary(BaseModel):
    nodes_online: int
    total_gpus: int
    used_gpus: int
    free_gpus: int
    utilization_pct: float
    queue_depth: dict


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/jobs", response_model=JobResponse, status_code=201)
async def submit_job(req: SubmitJobRequest, queue: JobQueue = Depends(get_queue)):
    priority_map = {
        "high": JobPriority.HIGH,
        "normal": JobPriority.NORMAL,
        "low": JobPriority.LOW,
    }
    priority = priority_map.get(req.priority.lower(), JobPriority.NORMAL)

    job = Job(
        job_name=req.job_name,
        config_path=req.config_path,
        owner=req.owner,
        priority=priority,
        num_gpus=req.num_gpus,
        num_nodes=req.num_nodes,
        estimated_hours=req.estimated_hours,
    )
    queue.submit(job)
    return _to_response(job)


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, queue: JobQueue = Depends(get_queue)):
    job = queue.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return _to_response(job)


@app.delete("/jobs/{job_id}", status_code=204)
async def cancel_job(job_id: str, queue: JobQueue = Depends(get_queue)):
    if not queue.cancel(job_id):
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")


@app.get("/jobs", response_model=List[JobResponse])
async def list_jobs(
    owner: Optional[str] = Query(None),
    queue: JobQueue = Depends(get_queue),
):
    jobs = queue.list_pending()
    if owner:
        jobs = [j for j in jobs if j.owner == owner]
    return [_to_response(j) for j in jobs]


@app.get("/cluster", response_model=ClusterSummary)
async def cluster_status(
    rm: ResourceManager = Depends(get_resource_manager),
    queue: JobQueue = Depends(get_queue),
):
    summary = rm.cluster_summary()
    summary["queue_depth"] = queue.queue_depth()
    return summary


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _to_response(job: Job) -> JobResponse:
    return JobResponse(
        job_id=job.job_id,
        job_name=job.job_name,
        status=job.status,
        owner=job.owner,
        priority=job.priority,
        num_gpus=job.num_gpus,
        num_nodes=job.num_nodes,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=job.error,
    )

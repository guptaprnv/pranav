"""
Worker process — polls the job queue and launches torchrun for each job.

Run: python -m src.worker
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
import uuid

from src.scheduler.job_queue import Job, JobQueue
from src.scheduler.resource_manager import ResourceManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
POLL_INTERVAL = int(os.environ.get("WORKER_POLL_INTERVAL", 5))   # seconds
WORKER_ID = os.environ.get("WORKER_ID", str(uuid.uuid4())[:8])


def launch_training(job: Job) -> subprocess.Popen:
    """Launch torchrun for the given job config."""
    cmd = [
        "torchrun",
        f"--nproc_per_node={job.num_gpus}",
        f"--nnodes={job.num_nodes}",
        "--rdzv_backend=c10d",
        f"--rdzv_endpoint={os.environ.get('RDZV_ENDPOINT', 'localhost:29500')}",
        f"--rdzv_id={job.job_id}",
        "-m", "src.train",
        f"--config={job.config_path}",
        f"--job_id={job.job_id}",
    ]
    logger.info(f"Launching: {' '.join(cmd)}")
    return subprocess.Popen(cmd, env=os.environ.copy())


def run() -> None:
    queue = JobQueue(redis_url=REDIS_URL)
    rm = ResourceManager(redis_url=REDIS_URL)
    current_proc: subprocess.Popen | None = None
    current_job: Job | None = None

    def _handle_sigterm(sig, frame):
        logger.info("SIGTERM received — shutting down worker")
        if current_proc:
            current_proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)
    logger.info(f"Worker {WORKER_ID} started, polling {REDIS_URL}")

    while True:
        # If we have a running process, check if it's done
        if current_proc is not None and current_job is not None:
            ret = current_proc.poll()
            if ret is not None:
                success = ret == 0
                error = "" if success else f"Process exited with code {ret}"
                queue.complete(WORKER_ID, current_job.job_id, success, error)
                rm.release(f"alloc:{current_job.job_id}")
                current_proc = None
                current_job = None
            else:
                queue.heartbeat(WORKER_ID)
                time.sleep(POLL_INTERVAL)
                continue

        # Try to pick up a new job
        job = queue.dequeue(worker_id=WORKER_ID, timeout=POLL_INTERVAL)
        if job is None:
            time.sleep(POLL_INTERVAL)
            continue

        alloc = rm.allocate(
            job_id=job.job_id,
            gpus_needed=job.num_gpus,
            cpus_needed=4,
            memory_gb_needed=32,
        )
        if alloc is None:
            logger.warning(f"No resources for job {job.job_id} — requeueing")
            queue.submit(job)   # put back in queue
            time.sleep(30)
            continue

        try:
            current_proc = launch_training(job)
            current_job = job
        except Exception as e:
            queue.complete(WORKER_ID, job.job_id, success=False, error=str(e))
            rm.release(f"alloc:{job.job_id}")
            logger.error(f"Failed to launch job {job.job_id}: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()

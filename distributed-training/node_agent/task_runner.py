"""
Task runner — executes training tasks assigned by the orchestrator.
Runs as a subprocess via torchrun to avoid blocking the agent event loop.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from typing import Optional

from p2p.peer import Peer

logger = logging.getLogger(__name__)


class TaskRunner:
    """
    Manages a single training subprocess per node.
    On task completion, reports back via callback.
    """

    def __init__(self, owner: str, peer: Peer, redis_url: str):
        self.owner = owner
        self.peer = peer
        self.redis_url = redis_url
        self._proc: Optional[subprocess.Popen] = None
        self._current_job_id: Optional[str] = None
        self._running = True
        self._lock = threading.Lock()

    def run_task(self, job_id: str, config_path: str, num_gpus: int = 1) -> bool:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                logger.warning(f"Already running job {self._current_job_id}, refusing {job_id}")
                return False

            env = {**os.environ, "REDIS_URL": self.redis_url}
            cmd = [
                "torchrun",
                f"--nproc_per_node={num_gpus}",
                "--rdzv_backend=c10d",
                f"--rdzv_endpoint=localhost:{self._pick_port()}",
                f"--rdzv_id={job_id}",
                "-m", "src.train",
                f"--config={config_path}",
                f"--job_id={job_id}",
                f"--owner={self.owner}",
            ]
            self._proc = subprocess.Popen(cmd, env=env)
            self._current_job_id = job_id
            logger.info(f"Task runner launched job {job_id} with {num_gpus} GPU(s)")

            threading.Thread(
                target=self._monitor_proc, args=(job_id,), daemon=True
            ).start()
            return True

    def is_busy(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        self._running = False
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                self._proc.wait(timeout=10)

    def _monitor_proc(self, job_id: str) -> None:
        proc = self._proc
        if proc:
            ret = proc.wait()
            logger.info(f"Job {job_id} finished with return code {ret}")
        with self._lock:
            if self._current_job_id == job_id:
                self._proc = None
                self._current_job_id = None

    @staticmethod
    def _pick_port() -> int:
        import socket
        s = socket.socket()
        s.bind(("", 0))
        port = s.getsockname()[1]
        s.close()
        return port

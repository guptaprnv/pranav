"""
Task runner — executes distributed training assignments assigned to a peer.

Instead of shelling out to torchrun, this launches one local process per
assigned rank and relies on PyTorch's default env:// initialization.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
from pathlib import Path
from typing import Callable, List, Optional

from src.scheduler.placement import LaunchAssignment

logger = logging.getLogger(__name__)


class TaskRunner:
    """
    Manages a single distributed job per peer.
    Each assignment may launch one or more local ranks depending on the
    slots granted to that peer by the placement planner.
    """

    def __init__(
        self,
        owner: str,
        redis_url: str,
        workdir: Optional[str] = None,
        on_job_finished: Optional[Callable[[LaunchAssignment, bool, str], None]] = None,
    ):
        self.owner = owner
        self.redis_url = redis_url
        self.workdir = workdir or os.getcwd()
        self.on_job_finished = on_job_finished
        self._procs: List[subprocess.Popen] = []
        self._assignment: Optional[LaunchAssignment] = None
        self._lock = threading.Lock()

    def run_assignment(self, assignment: LaunchAssignment) -> bool:
        with self._lock:
            if self.is_busy():
                logger.warning("Already running job %s, refusing %s", self._assignment.job_id, assignment.job_id)
                return False

            config_path = self._resolve_config_path(assignment.config_path)
            if not config_path.exists():
                logger.error("Config path not found for job %s: %s", assignment.job_id, config_path)
                return False

            self._assignment = assignment
            self._procs = []

            for local_rank in range(assignment.local_world_size):
                env = {
                    **os.environ,
                    "REDIS_URL": self.redis_url,
                    "MASTER_ADDR": assignment.master_addr,
                    "MASTER_PORT": str(assignment.master_port),
                    "RANK": str(assignment.global_rank_offset + local_rank),
                    "LOCAL_RANK": str(local_rank),
                    "WORLD_SIZE": str(assignment.world_size),
                    "PYTHONPATH": self._pythonpath(),
                }
                cmd = [
                    "python",
                    "-m",
                    "src.train",
                    f"--config={config_path}",
                    f"--job_id={assignment.job_id}",
                    f"--owner={assignment.owner}",
                ]
                logger.info(
                    "Launching rank %s/%s for job %s on node rank %s",
                    env["RANK"],
                    assignment.world_size,
                    assignment.job_id,
                    assignment.node_rank,
                )
                proc = subprocess.Popen(
                    cmd,
                    cwd=self.workdir,
                    env=env,
                    start_new_session=True,
                )
                self._procs.append(proc)

            threading.Thread(target=self._monitor_assignment, daemon=True).start()
            return True

    def is_busy(self) -> bool:
        return any(proc.poll() is None for proc in self._procs)

    def stop(self) -> None:
        with self._lock:
            for proc in self._procs:
                if proc.poll() is None:
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        proc.terminate()
            for proc in self._procs:
                if proc.poll() is None:
                    proc.wait(timeout=10)
            self._procs = []
            self._assignment = None

    def current_job_id(self) -> Optional[str]:
        return self._assignment.job_id if self._assignment else None

    def _monitor_assignment(self) -> None:
        assignment = self._assignment
        if not assignment:
            return

        codes: List[int] = []
        for proc in self._procs:
            codes.append(proc.wait())

        success = all(code == 0 for code in codes)
        error = "" if success else f"exit_codes={codes}"
        logger.info("Job %s finished on peer %s with %s", assignment.job_id, assignment.peer_id, codes)

        with self._lock:
            self._procs = []
            self._assignment = None

        if self.on_job_finished:
            self.on_job_finished(assignment, success, error)

    def _resolve_config_path(self, config_path: str) -> Path:
        path = Path(config_path)
        if path.is_absolute():
            return path
        return (Path(self.workdir) / path).resolve()

    def _pythonpath(self) -> str:
        parts = [self.workdir]
        if os.environ.get("PYTHONPATH"):
            parts.append(os.environ["PYTHONPATH"])
        return os.pathsep.join(parts)

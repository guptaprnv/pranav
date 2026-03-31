"""Structured training logger — rank-aware, JSON-compatible."""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any


def _make_handler(log_dir: str, job_id: str, rank: int) -> logging.FileHandler:
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, f"{job_id}_rank{rank}.log")
    h = logging.FileHandler(path)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    return h


class TrainingLogger:
    """
    Per-rank logger. Main rank (0) also emits structured JSON to stdout
    so log aggregators (Loki, CloudWatch, etc.) can parse it.
    """

    def __init__(self, job_id: str, rank: int = 0):
        self.job_id = job_id
        self.rank = rank
        log_dir = os.environ.get("LOG_DIR", "/tmp/dt_logs")

        self._logger = logging.getLogger(f"dt.{job_id}.rank{rank}")
        self._logger.setLevel(logging.DEBUG)
        if not self._logger.handlers:
            self._logger.addHandler(_make_handler(log_dir, job_id, rank))
            if rank == 0:
                sh = logging.StreamHandler(sys.stdout)
                sh.setLevel(logging.INFO)
                self._logger.addHandler(sh)

    def _emit(self, level: str, msg: str, **extra: Any) -> None:
        payload = {
            "ts": time.time(),
            "job_id": self.job_id,
            "rank": self.rank,
            "level": level,
            "msg": msg,
            **extra,
        }
        getattr(self._logger, level.lower())(json.dumps(payload))

    def info(self, msg: str, **kw) -> None:
        self._emit("INFO", msg, **kw)

    def warning(self, msg: str, **kw) -> None:
        self._emit("WARNING", msg, **kw)

    def error(self, msg: str, **kw) -> None:
        self._emit("ERROR", msg, **kw)

    def debug(self, msg: str, **kw) -> None:
        self._emit("DEBUG", msg, **kw)

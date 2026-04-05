"""Metrics collection — writes to local log + pushes to MLflow/W&B (pluggable)."""
from __future__ import annotations

import logging
import os
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Collects training metrics and forwards them to configured backends.

    Backends (enabled via env vars):
      MLFLOW_TRACKING_URI  → MLflow
      WANDB_API_KEY        → Weights & Biases  [TECH: add later]
      TENSORBOARD_LOG_DIR  → TensorBoard       [TECH: add later]
    """

    def __init__(self, job_id: str, rank: int = 0):
        self.job_id = job_id
        self.rank = rank
        self._mlflow_run = None
        self._step_history: list = []

        if rank == 0:
            self._init_mlflow()

    def _init_mlflow(self) -> None:
        tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
        if not tracking_uri:
            return
        try:
            import mlflow
            mlflow.set_tracking_uri(tracking_uri)
            mlflow.set_experiment(os.environ.get("MLFLOW_EXPERIMENT", "distributed-training"))
            self._mlflow_run = mlflow.start_run(run_name=self.job_id)
            logger.info(f"MLflow run started: {self._mlflow_run.info.run_id}")
        except ImportError:
            logger.warning("mlflow not installed — skipping MLflow logging")

    def log_step(self, step: int, metrics: Dict[str, float]) -> None:
        if self.rank != 0:
            return
        self._step_history.append({"step": step, "ts": time.time(), **metrics})
        if self._mlflow_run:
            try:
                import mlflow
                mlflow.log_metrics(metrics, step=step)
            except Exception as e:
                logger.debug(f"MLflow log_step error: {e}")

    def log_epoch(self, epoch: int, metrics: Dict[str, float]) -> None:
        if self.rank != 0:
            return
        logger.info(f"[epoch {epoch}] " + " | ".join(f"{k}={v:.4f}" for k, v in metrics.items()))
        if self._mlflow_run:
            try:
                import mlflow
                mlflow.log_metrics({f"epoch_{k}": v for k, v in metrics.items()}, step=epoch)
            except Exception as e:
                logger.debug(f"MLflow log_epoch error: {e}")

    def log_params(self, params: Dict) -> None:
        if self.rank != 0 or not self._mlflow_run:
            return
        try:
            import mlflow
            mlflow.log_params(params)
        except Exception as e:
            logger.debug(f"MLflow log_params error: {e}")

    def close(self) -> None:
        if self._mlflow_run:
            try:
                import mlflow
                mlflow.end_run()
            except Exception:
                pass

    def summary(self) -> Dict:
        if not self._step_history:
            return {}
        losses = [s.get("loss", 0) for s in self._step_history]
        return {
            "steps_logged": len(self._step_history),
            "min_loss": min(losses),
            "final_loss": losses[-1],
        }

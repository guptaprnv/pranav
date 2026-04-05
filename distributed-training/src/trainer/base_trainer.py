"""Base trainer defining the contract for all distributed training strategies."""
import os
import time
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import torch
import torch.nn as nn
from torch.optim import Optimizer
from torch.utils.data import DataLoader

from src.config import TrainingConfig
from src.monitoring import MetricsCollector, TrainingLogger
from src.utils import CheckpointManager

logger = logging.getLogger(__name__)


class BaseTrainer(ABC):
    """
    Abstract base trainer. Subclass this to implement a specific
    distributed strategy (DDP, FSDP, DeepSpeed, etc.).
    """

    def __init__(
        self,
        model: nn.Module,
        optimizer: Optimizer,
        config: TrainingConfig,
        train_loader: DataLoader,
        val_loader: Optional[DataLoader] = None,
    ):
        self.model = model
        self.optimizer = optimizer
        self.config = config
        self.train_loader = train_loader
        self.val_loader = val_loader

        self.rank = int(os.environ.get("RANK", 0))
        self.world_size = int(os.environ.get("WORLD_SIZE", 1))
        self.local_rank = int(os.environ.get("LOCAL_RANK", 0))
        self.is_main = self.rank == 0

        self.metrics = MetricsCollector(job_id=config.job_id, rank=self.rank)
        self.log = TrainingLogger(job_id=config.job_id, rank=self.rank)
        self.checkpointer = CheckpointManager(
            checkpoint_dir=config.checkpoint_dir,
            keep_last_n=config.keep_last_n_checkpoints,
        )

        self.global_step = 0
        self.current_epoch = 0

    @abstractmethod
    def setup(self) -> None:
        """Initialize process group, wrap model, move to device."""

    @abstractmethod
    def teardown(self) -> None:
        """Destroy process group and free resources."""

    @abstractmethod
    def train_step(self, batch: Any) -> Dict[str, float]:
        """Run one forward+backward pass. Return dict of scalar metrics."""

    def train(self) -> Dict[str, Any]:
        self.setup()
        try:
            return self._training_loop()
        finally:
            self.teardown()

    def _training_loop(self) -> Dict[str, Any]:
        self.log.info(
            f"Starting training | rank={self.rank} world_size={self.world_size} "
            f"epochs={self.config.num_epochs}"
        )
        start = time.time()

        for epoch in range(self.current_epoch, self.config.num_epochs):
            self.current_epoch = epoch
            epoch_metrics = self._run_epoch(epoch)

            if self.val_loader is not None:
                val_metrics = self.validate()
                epoch_metrics.update(val_metrics)

            if self.is_main:
                self.metrics.log_epoch(epoch, epoch_metrics)
                self.checkpointer.save(
                    epoch=epoch,
                    model=self.model,
                    optimizer=self.optimizer,
                    metrics=epoch_metrics,
                )

        elapsed = time.time() - start
        self.log.info(f"Training complete in {elapsed:.1f}s")
        return {"total_time": elapsed, "epochs": self.config.num_epochs}

    def _run_epoch(self, epoch: int) -> Dict[str, float]:
        self.model.train()
        total_loss = 0.0
        n_batches = 0

        # Distributed sampler needs epoch set for proper shuffling
        if hasattr(self.train_loader.sampler, "set_epoch"):
            self.train_loader.sampler.set_epoch(epoch)

        for batch in self.train_loader:
            step_metrics = self.train_step(batch)
            total_loss += step_metrics.get("loss", 0.0)
            n_batches += 1
            self.global_step += 1

            if self.global_step % self.config.log_every_n_steps == 0 and self.is_main:
                self.metrics.log_step(self.global_step, step_metrics)

        return {"train_loss": total_loss / max(n_batches, 1)}

    def validate(self) -> Dict[str, float]:
        self.model.eval()
        total_loss = 0.0
        n_batches = 0

        with torch.no_grad():
            for batch in self.val_loader:
                step_metrics = self.train_step(batch)
                total_loss += step_metrics.get("loss", 0.0)
                n_batches += 1

        return {"val_loss": total_loss / max(n_batches, 1)}

    def load_checkpoint(self, path: str) -> None:
        state = self.checkpointer.load(path)
        self.model.load_state_dict(state["model"])
        self.optimizer.load_state_dict(state["optimizer"])
        self.current_epoch = state.get("epoch", 0) + 1
        self.global_step = state.get("global_step", 0)
        self.log.info(f"Resumed from checkpoint: {path} (epoch {self.current_epoch})")

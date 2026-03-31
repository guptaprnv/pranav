"""DistributedDataParallel trainer — the standard multi-GPU strategy."""
import os
from typing import Any, Dict, Optional

import torch
import torch.distributed as dist
import torch.nn as nn
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.optim import Optimizer
from torch.utils.data import DataLoader

from src.config import TrainingConfig
from .base_trainer import BaseTrainer


class DDPTrainer(BaseTrainer):
    """
    PyTorch DDP trainer.

    Best for:
    - Models that fit on a single GPU
    - Synchronous data-parallel training
    - Up to ~8-16 GPUs per node, multi-node via NCCL

    Limitations addressed by FSDPTrainer:
    - Cannot handle models larger than single-GPU VRAM
    """

    def __init__(
        self,
        model: nn.Module,
        optimizer: Optimizer,
        config: TrainingConfig,
        train_loader: DataLoader,
        val_loader: Optional[DataLoader] = None,
    ):
        super().__init__(model, optimizer, config, train_loader, val_loader)
        self._wrapped_model: Optional[DDP] = None

    def setup(self) -> None:
        if not dist.is_initialized():
            backend = self.config.distributed.backend  # "nccl" for GPU, "gloo" for CPU
            dist.init_process_group(backend=backend)

        device = torch.device(f"cuda:{self.local_rank}" if torch.cuda.is_available() else "cpu")
        self.model = self.model.to(device)
        self._wrapped_model = DDP(
            self.model,
            device_ids=[self.local_rank] if torch.cuda.is_available() else None,
            output_device=self.local_rank if torch.cuda.is_available() else None,
            find_unused_parameters=self.config.distributed.find_unused_parameters,
        )
        self.device = device
        self.log.info(f"DDP setup complete | rank={self.rank} device={device}")

    def teardown(self) -> None:
        if dist.is_initialized():
            dist.destroy_process_group()

    def train_step(self, batch: Any) -> Dict[str, float]:
        inputs, targets = batch[0].to(self.device), batch[1].to(self.device)

        self.optimizer.zero_grad()
        outputs = self._wrapped_model(inputs)
        loss = self._compute_loss(outputs, targets)
        loss.backward()

        if self.config.max_grad_norm is not None:
            nn.utils.clip_grad_norm_(self._wrapped_model.parameters(), self.config.max_grad_norm)

        self.optimizer.step()
        return {"loss": loss.item()}

    def _compute_loss(self, outputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        # Default: cross-entropy. Override in subclass for custom losses.
        return nn.CrossEntropyLoss()(outputs, targets)

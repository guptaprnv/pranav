"""Fully Sharded Data Parallel trainer — for large models exceeding single-GPU VRAM."""
from typing import Any, Dict, Optional

import torch
import torch.distributed as dist
import torch.nn as nn
from torch.distributed.fsdp import (
    FullyShardedDataParallel as FSDP,
    MixedPrecision,
    ShardingStrategy,
    StateDictType,
    FullStateDictConfig,
)
from torch.distributed.fsdp.wrap import size_based_auto_wrap_policy
from torch.optim import Optimizer
from torch.utils.data import DataLoader
import functools

from src.config import TrainingConfig
from .base_trainer import BaseTrainer


_SHARDING_STRATEGIES = {
    "full": ShardingStrategy.FULL_SHARD,          # max memory savings
    "hybrid": ShardingStrategy.HYBRID_SHARD,      # intra-node shard, inter-node replicate
    "no_shard": ShardingStrategy.NO_SHARD,         # equivalent to DDP
    "shard_grad_op": ShardingStrategy.SHARD_GRAD_OP,
}


class FSDPTrainer(BaseTrainer):
    """
    PyTorch FSDP trainer.

    Best for:
    - Models too large to fit on a single GPU (LLMs, large vision models)
    - Mixed precision training (bf16/fp16)
    - Activation checkpointing for extreme memory efficiency

    Trade-offs vs DDP:
    - Slower due to all-gather / reduce-scatter communication overhead
    - More complex checkpoint handling (must consolidate shards)
    """

    def __init__(
        self,
        model: nn.Module,
        optimizer_cls: type,
        optimizer_kwargs: dict,
        config: TrainingConfig,
        train_loader: DataLoader,
        val_loader: Optional[DataLoader] = None,
    ):
        # NOTE: optimizer is created AFTER FSDP wrapping for correct param groups
        # We pass a placeholder and replace it in setup()
        dummy_opt = optimizer_cls(model.parameters(), **optimizer_kwargs)
        super().__init__(model, dummy_opt, config, train_loader, val_loader)
        self._optimizer_cls = optimizer_cls
        self._optimizer_kwargs = optimizer_kwargs
        self._wrapped_model: Optional[FSDP] = None

    def setup(self) -> None:
        if not dist.is_initialized():
            dist.init_process_group(backend="nccl")

        device = torch.device(f"cuda:{self.local_rank}")
        torch.cuda.set_device(device)

        # Mixed precision policy
        mp_policy = None
        if self.config.distributed.mixed_precision:
            dtype = torch.bfloat16 if self.config.distributed.use_bf16 else torch.float16
            mp_policy = MixedPrecision(
                param_dtype=dtype,
                reduce_dtype=dtype,
                buffer_dtype=dtype,
            )

        # Auto-wrap policy: shard layers with >100M params by default
        min_params = self.config.distributed.fsdp_min_params_to_wrap
        wrap_policy = functools.partial(size_based_auto_wrap_policy, min_num_params=min_params)

        sharding = _SHARDING_STRATEGIES.get(
            self.config.distributed.fsdp_sharding_strategy, ShardingStrategy.FULL_SHARD
        )

        self._wrapped_model = FSDP(
            self.model.to(device),
            sharding_strategy=sharding,
            mixed_precision=mp_policy,
            auto_wrap_policy=wrap_policy,
            device_id=device,
        )

        # Recreate optimizer on FSDP-wrapped params
        self.optimizer = self._optimizer_cls(
            self._wrapped_model.parameters(), **self._optimizer_kwargs
        )
        self.device = device
        self.log.info(
            f"FSDP setup complete | rank={self.rank} device={device} "
            f"sharding={sharding} mp={self.config.distributed.mixed_precision}"
        )

    def teardown(self) -> None:
        if dist.is_initialized():
            dist.destroy_process_group()

    def train_step(self, batch: Any) -> Dict[str, float]:
        inputs, targets = batch[0].to(self.device), batch[1].to(self.device)

        self.optimizer.zero_grad()
        outputs = self._wrapped_model(inputs)
        loss = nn.CrossEntropyLoss()(outputs, targets)
        loss.backward()

        if self.config.max_grad_norm is not None:
            self._wrapped_model.clip_grad_norm_(self.config.max_grad_norm)

        self.optimizer.step()
        return {"loss": loss.item()}

    def save_consolidated_checkpoint(self, path: str) -> None:
        """Save a full (non-sharded) state dict — only runs on rank 0."""
        cfg = FullStateDictConfig(offload_to_cpu=True, rank0_only=True)
        with FSDP.state_dict_type(self._wrapped_model, StateDictType.FULL_STATE_DICT, cfg):
            state = self._wrapped_model.state_dict()
        if self.is_main:
            torch.save(state, path)
            self.log.info(f"Consolidated checkpoint saved to {path}")

"""Distributed-aware data loader factory."""
from __future__ import annotations

import os
from typing import Optional

import torch
from torch.utils.data import DataLoader, Dataset, DistributedSampler


def make_distributed_loader(
    dataset: Dataset,
    batch_size: int,
    num_workers: int = 4,
    pin_memory: bool = True,
    shuffle: bool = True,
    rank: Optional[int] = None,
    world_size: Optional[int] = None,
    drop_last: bool = True,
) -> DataLoader:
    """
    Build a DataLoader with DistributedSampler when running in multi-process mode.

    When world_size=1 (single GPU / CPU), falls back to a standard DataLoader
    with a regular shuffled sampler — no code change needed.
    """
    _rank = rank if rank is not None else int(os.environ.get("RANK", 0))
    _world_size = world_size if world_size is not None else int(os.environ.get("WORLD_SIZE", 1))

    if _world_size > 1:
        sampler = DistributedSampler(
            dataset,
            num_replicas=_world_size,
            rank=_rank,
            shuffle=shuffle,
            drop_last=drop_last,
        )
        _shuffle = False   # sampler handles shuffle
    else:
        sampler = None
        _shuffle = shuffle

    return DataLoader(
        dataset,
        batch_size=batch_size,
        sampler=sampler,
        shuffle=_shuffle if sampler is None else False,
        num_workers=num_workers,
        pin_memory=pin_memory and torch.cuda.is_available(),
        drop_last=drop_last,
        persistent_workers=num_workers > 0,
    )

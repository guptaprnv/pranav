"""Checkpoint manager — saves, loads, and rotates model checkpoints."""
from __future__ import annotations

import glob
import logging
import os
from typing import Any, Dict, Optional

import torch
import torch.nn as nn
from torch.optim import Optimizer

logger = logging.getLogger(__name__)


class CheckpointManager:
    """
    Saves checkpoints as:
      <checkpoint_dir>/epoch_<N>_step_<S>.pt

    Keeps only the last N checkpoints to cap disk usage.
    Also maintains a symlink `latest.pt` for easy resumption.
    """

    def __init__(self, checkpoint_dir: str, keep_last_n: int = 3):
        self.checkpoint_dir = checkpoint_dir
        self.keep_last_n = keep_last_n
        os.makedirs(checkpoint_dir, exist_ok=True)

    def save(
        self,
        epoch: int,
        model: nn.Module,
        optimizer: Optimizer,
        metrics: Optional[Dict[str, float]] = None,
        global_step: int = 0,
    ) -> str:
        filename = f"epoch_{epoch:04d}_step_{global_step:08d}.pt"
        path = os.path.join(self.checkpoint_dir, filename)
        state = {
            "epoch": epoch,
            "global_step": global_step,
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "metrics": metrics or {},
        }
        torch.save(state, path)
        self._update_latest_symlink(path)
        self._rotate()
        logger.info(f"Checkpoint saved: {path}")
        return path

    def load(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Checkpoint not found: {path}")
        state = torch.load(path, map_location="cpu")
        logger.info(f"Checkpoint loaded: {path}")
        return state

    def load_latest(self) -> Optional[Dict[str, Any]]:
        latest = os.path.join(self.checkpoint_dir, "latest.pt")
        if os.path.exists(latest):
            return self.load(latest)
        return None

    def list_checkpoints(self):
        pattern = os.path.join(self.checkpoint_dir, "epoch_*.pt")
        return sorted(glob.glob(pattern))

    def _update_latest_symlink(self, path: str) -> None:
        link = os.path.join(self.checkpoint_dir, "latest.pt")
        if os.path.islink(link):
            os.remove(link)
        os.symlink(os.path.abspath(path), link)

    def _rotate(self) -> None:
        checkpoints = self.list_checkpoints()
        while len(checkpoints) > self.keep_last_n:
            old = checkpoints.pop(0)
            os.remove(old)
            logger.debug(f"Rotated old checkpoint: {old}")

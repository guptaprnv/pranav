"""
Training entry point — launched by torchrun or the worker process.

Usage:
  # Single GPU (Mac mini, local dev)
  python -m src.train --config configs/small.yaml

  # Multi-GPU via torchrun
  torchrun --nproc_per_node=1 -m src.train --config configs/small.yaml

  # AWS 5-minute smoke run
  python -m src.train --config configs/small.yaml --max_minutes 5
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import signal

import torch
import torch.nn as nn
import torchvision
import torchvision.transforms as T
from torch.optim import AdamW
from torch.optim.lr_scheduler import OneCycleLR

from src.config import TrainingConfig
from src.utils.checkpoint import CheckpointManager
from src.utils.data_loader import make_distributed_loader
from src.monitoring.logger import TrainingLogger
from src.monitoring.metrics import MetricsCollector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("train")

# ── Registry: model_name → constructor ──────────────────────────────────────
MODEL_REGISTRY = {
    "resnet18":  lambda nc: torchvision.models.resnet18(num_classes=nc),
    "resnet50":  lambda nc: torchvision.models.resnet50(num_classes=nc),
    "resnet101": lambda nc: torchvision.models.resnet101(num_classes=nc),
}

DATASET_REGISTRY = {
    "cifar10":  (torchvision.datasets.CIFAR10,  10,  (0.4914, 0.4822, 0.4465), (0.247, 0.243, 0.261)),
    "cifar100": (torchvision.datasets.CIFAR100, 100, (0.5071, 0.4867, 0.4408), (0.267, 0.256, 0.276)),
    "synthetic": None,   # built-in, no download needed
}


def build_model(config: TrainingConfig) -> nn.Module:
    name = config.model_name.lower()
    if name not in MODEL_REGISTRY:
        raise ValueError(f"Unknown model '{name}'. Available: {list(MODEL_REGISTRY)}")
    ds_info = DATASET_REGISTRY.get(config.dataset.lower())
    num_classes = ds_info[1] if ds_info else 10
    return MODEL_REGISTRY[name](num_classes)


class SyntheticDataset(torch.utils.data.Dataset):
    """In-memory random dataset — no download needed. Same shape as CIFAR-10."""
    def __init__(self, size: int = 5000, num_classes: int = 10):
        self.data    = torch.randn(size, 3, 32, 32)
        self.targets = torch.randint(0, num_classes, (size,))
    def __len__(self): return len(self.data)
    def __getitem__(self, idx): return self.data[idx], self.targets[idx]


def build_dataloaders(config: TrainingConfig):
    ds_key = config.dataset.lower()
    if ds_key not in DATASET_REGISTRY:
        raise ValueError(f"Unknown dataset '{ds_key}'. Available: {list(DATASET_REGISTRY)}")

    # Synthetic dataset — no internet required
    if ds_key == "synthetic" or DATASET_REGISTRY[ds_key] is None:
        num_classes = 10
        train_ds = SyntheticDataset(size=5000, num_classes=num_classes)
        val_ds   = SyntheticDataset(size=1000, num_classes=num_classes)
        train_loader = make_distributed_loader(train_ds, batch_size=config.batch_size, shuffle=True)
        val_loader   = make_distributed_loader(val_ds,   batch_size=config.batch_size * 2, shuffle=False)
        return train_loader, val_loader, num_classes

    cls, num_classes, mean, std = DATASET_REGISTRY[ds_key]

    train_tf = T.Compose([
        T.RandomCrop(32, padding=4),
        T.RandomHorizontalFlip(),
        T.ToTensor(),
        T.Normalize(mean, std),
    ])
    val_tf = T.Compose([
        T.ToTensor(),
        T.Normalize(mean, std),
    ])

    data_dir = config.data_dir
    try:
        train_ds = cls(data_dir, train=True,  download=True, transform=train_tf)
        val_ds   = cls(data_dir, train=False, download=True, transform=val_tf)
    except Exception:
        logger.warning(f"Could not download {ds_key} — falling back to synthetic dataset")
        train_ds = SyntheticDataset(size=5000, num_classes=num_classes)
        val_ds   = SyntheticDataset(size=1000, num_classes=num_classes)

    train_loader = make_distributed_loader(train_ds, batch_size=config.batch_size, shuffle=True)
    val_loader   = make_distributed_loader(val_ds,   batch_size=config.batch_size * 2, shuffle=False)
    return train_loader, val_loader, num_classes


def accuracy(outputs: torch.Tensor, targets: torch.Tensor) -> float:
    preds = outputs.argmax(dim=1)
    return (preds == targets).float().mean().item()


def run(config: TrainingConfig, max_minutes: float | None = None) -> None:
    rank       = int(os.environ.get("RANK", 0))
    world_size = int(os.environ.get("WORLD_SIZE", 1))
    local_rank = int(os.environ.get("LOCAL_RANK", 0))
    is_main    = rank == 0

    # ── Device ──────────────────────────────────────────────────────────────
    if torch.cuda.is_available():
        device = torch.device(f"cuda:{local_rank}")
        torch.cuda.set_device(device)
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = torch.device("mps")    # Apple Silicon
    else:
        device = torch.device("cpu")

    # ── Distributed init ────────────────────────────────────────────────────
    if world_size > 1:
        import torch.distributed as dist
        backend = "nccl" if device.type == "cuda" else "gloo"
        if not dist.is_initialized():
            dist.init_process_group(backend=backend)

    log    = TrainingLogger(job_id=config.job_id, rank=rank)
    metrics = MetricsCollector(job_id=config.job_id, rank=rank)
    ckpt   = CheckpointManager(config.checkpoint_dir, config.keep_last_n_checkpoints)

    log.info(f"Starting | job={config.job_id} device={device} world={world_size} "
             f"model={config.model_name} dataset={config.dataset}")

    # ── Data ────────────────────────────────────────────────────────────────
    train_loader, val_loader, num_classes = build_dataloaders(config)

    # ── Model ───────────────────────────────────────────────────────────────
    model = build_model(config).to(device)
    if world_size > 1:
        from torch.nn.parallel import DistributedDataParallel as DDP
        model = DDP(model, device_ids=[local_rank] if device.type == "cuda" else None)

    # ── Optimizer + scheduler ───────────────────────────────────────────────
    optimizer = AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    total_steps = len(train_loader) * config.num_epochs
    scheduler = OneCycleLR(optimizer, max_lr=config.learning_rate, total_steps=total_steps)
    criterion = nn.CrossEntropyLoss()

    # ── Deadline for time-boxed runs (e.g. 5 minutes on AWS) ───────────────
    deadline = time.time() + (max_minutes * 60) if max_minutes else None

    global_step = 0
    best_val_acc = 0.0
    training_start = time.time()

    for epoch in range(config.num_epochs):
        # Check deadline
        if deadline and time.time() >= deadline:
            log.info(f"Time limit reached after {epoch} epoch(s) — stopping cleanly.")
            break

        model.train()
        if hasattr(train_loader.sampler, "set_epoch"):
            train_loader.sampler.set_epoch(epoch)

        epoch_loss = 0.0
        epoch_acc  = 0.0
        n_batches  = 0

        for batch in train_loader:
            if deadline and time.time() >= deadline:
                break

            inputs, targets = batch[0].to(device), batch[1].to(device)
            optimizer.zero_grad()
            outputs = model(inputs)
            loss    = criterion(outputs, targets)
            loss.backward()

            if config.max_grad_norm:
                nn.utils.clip_grad_norm_(model.parameters(), config.max_grad_norm)

            optimizer.step()
            scheduler.step()

            acc         = accuracy(outputs.detach(), targets)
            epoch_loss += loss.item()
            epoch_acc  += acc
            n_batches  += 1
            global_step += 1

            if global_step % config.log_every_n_steps == 0 and is_main:
                elapsed = time.time() - training_start
                remaining = f"{(deadline - time.time()):.0f}s left" if deadline else ""
                log.info(
                    f"step={global_step} epoch={epoch} "
                    f"loss={loss.item():.4f} acc={acc:.3f} "
                    f"lr={scheduler.get_last_lr()[0]:.6f} "
                    f"elapsed={elapsed:.0f}s {remaining}"
                )
                metrics.log_step(global_step, {"loss": loss.item(), "acc": acc})

        # Validation
        model.eval()
        val_loss, val_acc, val_n = 0.0, 0.0, 0
        with torch.no_grad():
            for batch in val_loader:
                if deadline and time.time() >= deadline:
                    break
                inputs, targets = batch[0].to(device), batch[1].to(device)
                outputs = model(inputs)
                val_loss += criterion(outputs, targets).item()
                val_acc  += accuracy(outputs, targets)
                val_n    += 1

        if val_n > 0:
            val_loss /= val_n
            val_acc  /= val_n
            if is_main:
                log.info(f"[epoch {epoch}] val_loss={val_loss:.4f} val_acc={val_acc:.3f}")
                metrics.log_epoch(epoch, {
                    "train_loss": epoch_loss / max(n_batches, 1),
                    "train_acc":  epoch_acc  / max(n_batches, 1),
                    "val_loss":   val_loss,
                    "val_acc":    val_acc,
                })

                if val_acc > best_val_acc:
                    best_val_acc = val_acc
                    ckpt.save(epoch, model, optimizer,
                              {"val_acc": val_acc, "val_loss": val_loss}, global_step)

    elapsed_total = time.time() - training_start
    if is_main:
        log.info(f"Training finished | elapsed={elapsed_total:.0f}s "
                 f"steps={global_step} best_val_acc={best_val_acc:.3f}")
        metrics.close()

    if world_size > 1:
        import torch.distributed as dist
        dist.destroy_process_group()


def main() -> None:
    parser = argparse.ArgumentParser(description="Distributed Training entry point")
    parser.add_argument("--config",      required=True,  help="Path to TrainingConfig YAML")
    parser.add_argument("--job_id",      default=None,   help="Override job ID")
    parser.add_argument("--owner",       default=None,   help="Job owner username")
    parser.add_argument("--max_minutes", type=float, default=None,
                        help="Stop training after N minutes (used for timed AWS runs)")
    args = parser.parse_args()

    config = TrainingConfig.from_yaml(args.config)
    if args.job_id:
        config.job_id = args.job_id
    if args.owner:
        config.job_name = f"{args.owner}/{config.job_name}"

    run(config, max_minutes=args.max_minutes)


if __name__ == "__main__":
    main()

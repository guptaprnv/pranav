"""Training configuration — loaded from YAML, validated with dataclasses."""
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from typing import Optional
import yaml


@dataclass
class DistributedConfig:
    backend: str = "nccl"                      # nccl | gloo | mpi
    strategy: str = "ddp"                       # ddp | fsdp
    find_unused_parameters: bool = False

    # FSDP-specific
    fsdp_sharding_strategy: str = "full"        # full | hybrid | shard_grad_op | no_shard
    fsdp_min_params_to_wrap: int = 100_000_000

    # Mixed precision
    mixed_precision: bool = True
    use_bf16: bool = True                       # False → fp16


@dataclass
class ResourceConfig:
    gpus_per_node: int = 1
    num_nodes: int = 1
    cpus_per_task: int = 4
    memory_gb: int = 32
    timeout_hours: int = 24

    @property
    def world_size(self) -> int:
        return self.gpus_per_node * self.num_nodes


@dataclass
class TrainingConfig:
    # Job identity
    job_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    job_name: str = "training-job"

    # Model & data
    model_name: str = "resnet50"
    dataset: str = "imagenet"
    data_dir: str = "/data"

    # Training hyperparams
    num_epochs: int = 10
    batch_size: int = 64               # per-GPU batch size
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    max_grad_norm: Optional[float] = 1.0
    warmup_steps: int = 500

    # Checkpointing
    checkpoint_dir: str = "/checkpoints"
    keep_last_n_checkpoints: int = 3
    save_every_n_epochs: int = 1

    # Logging
    log_every_n_steps: int = 10
    log_dir: str = "/logs"

    # Sub-configs
    distributed: DistributedConfig = field(default_factory=DistributedConfig)
    resources: ResourceConfig = field(default_factory=ResourceConfig)

    @classmethod
    def from_yaml(cls, path: str) -> TrainingConfig:
        with open(path) as f:
            raw = yaml.safe_load(f)

        dist_raw = raw.pop("distributed", {})
        res_raw = raw.pop("resources", {})

        config = cls(**raw)
        config.distributed = DistributedConfig(**dist_raw)
        config.resources = ResourceConfig(**res_raw)
        return config

    def to_yaml(self, path: str) -> None:
        import dataclasses
        d = dataclasses.asdict(self)
        with open(path, "w") as f:
            yaml.dump(d, f, default_flow_style=False)

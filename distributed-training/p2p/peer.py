"""
Peer identity and connection management.

Every node generates a persistent Ed25519 keypair stored locally.
The public key IS the node's identity — no central authority needed.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import time
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PublicFormat, PrivateFormat, NoEncryption,
    )
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False
    logger.warning("cryptography not installed — peer identity will use UUID fallback")


@dataclass
class PeerInfo:
    """Serializable description of a peer, shared via gossip."""
    peer_id: str
    public_key_hex: str
    hostname: str
    ip: str
    port: int
    device_type: str          # "mac_mini" | "ipad" | "cloud" | "workstation"
    gpu_count: int
    cpu_count: int
    memory_gb: float
    os_info: str
    version: str
    last_seen: float = field(default_factory=time.time)
    contribution_score: float = 0.0   # updated by ledger

    def is_stale(self, ttl: float = 120.0) -> bool:
        return (time.time() - self.last_seen) > ttl

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> PeerInfo:
        return cls(**d)


class PeerIdentity:
    """
    Persistent node identity backed by an Ed25519 keypair.
    On first run, a new key is generated and saved to ~/.dt_node/identity.json.
    """

    IDENTITY_FILE = Path.home() / ".dt_node" / "identity.json"

    def __init__(self):
        self._key_file = self.IDENTITY_FILE
        self._key_file.parent.mkdir(parents=True, exist_ok=True)
        self._private_key, self.peer_id, self.public_key_hex = self._load_or_generate()

    def _load_or_generate(self):
        if self._key_file.exists():
            try:
                data = json.loads(self._key_file.read_text())
                peer_id = data["peer_id"]
                pub_hex = data["public_key_hex"]
                priv_bytes = bytes.fromhex(data["private_key_hex"])
                if _CRYPTO_AVAILABLE:
                    priv = Ed25519PrivateKey.from_private_bytes(priv_bytes)
                else:
                    priv = None
                logger.info(f"Loaded identity: {peer_id}")
                return priv, peer_id, pub_hex
            except Exception as e:
                logger.warning(f"Could not load identity ({e}), regenerating")

        return self._generate()

    def _generate(self):
        if _CRYPTO_AVAILABLE:
            priv = Ed25519PrivateKey.generate()
            pub = priv.public_key()
            pub_bytes = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
            priv_bytes = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
            peer_id = str(uuid.UUID(bytes=pub_bytes[:16]))
            pub_hex = pub_bytes.hex()
            priv_hex = priv_bytes.hex()
        else:
            priv = None
            peer_id = str(uuid.uuid4())
            pub_hex = peer_id.replace("-", "")
            priv_hex = str(uuid.uuid4()).replace("-", "")

        self._key_file.write_text(json.dumps({
            "peer_id": peer_id,
            "public_key_hex": pub_hex,
            "private_key_hex": priv_hex,
        }))
        logger.info(f"Generated new identity: {peer_id}")
        return priv, peer_id, pub_hex

    def sign(self, data: bytes) -> bytes:
        if not _CRYPTO_AVAILABLE or self._private_key is None:
            return b""
        return self._private_key.sign(data)


class Peer:
    """
    Local node — wraps identity, builds PeerInfo, manages known peers table.
    """

    def __init__(
        self,
        port: int = 7777,
        device_type: str = "workstation",
        version: str = "0.1.0",
    ):
        self.identity = PeerIdentity()
        self.port = port
        self.device_type = device_type
        self.version = version

        self._peers: Dict[str, PeerInfo] = {}   # peer_id → PeerInfo

        self.info = PeerInfo(
            peer_id=self.identity.peer_id,
            public_key_hex=self.identity.public_key_hex,
            hostname=socket.gethostname(),
            ip=self._local_ip(),
            port=port,
            device_type=device_type,
            gpu_count=self._detect_gpus(),
            cpu_count=os.cpu_count() or 1,
            memory_gb=self._detect_memory_gb(),
            os_info=self._os_info(),
            version=version,
        )

    # ------------------------------------------------------------------
    # Peer table management
    # ------------------------------------------------------------------

    def add_or_update(self, info: PeerInfo) -> None:
        if info.peer_id == self.identity.peer_id:
            return
        info.last_seen = time.time()
        self._peers[info.peer_id] = info

    def remove_stale(self, ttl: float = 120.0) -> List[str]:
        stale = [pid for pid, p in self._peers.items() if p.is_stale(ttl)]
        for pid in stale:
            del self._peers[pid]
            logger.info(f"Peer gone: {pid}")
        return stale

    def all_peers(self) -> List[PeerInfo]:
        return list(self._peers.values())

    def get_peer(self, peer_id: str) -> Optional[PeerInfo]:
        return self._peers.get(peer_id)

    def peer_count(self) -> int:
        return len(self._peers)

    # ------------------------------------------------------------------
    # System detection helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _local_ip() -> str:
        override = os.environ.get("DT_NODE_IP")
        if override:
            return override
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    @staticmethod
    def _detect_gpus() -> int:
        try:
            import torch
            return torch.cuda.device_count()
        except ImportError:
            pass
        try:
            import subprocess
            out = subprocess.check_output(["nvidia-smi", "-L"], stderr=subprocess.DEVNULL)
            return len(out.splitlines())
        except Exception:
            return 0

    @staticmethod
    def _detect_memory_gb() -> float:
        try:
            import psutil
            return round(psutil.virtual_memory().total / 1e9, 1)
        except ImportError:
            return 0.0

    @staticmethod
    def _os_info() -> str:
        import platform
        return f"{platform.system()} {platform.release()} {platform.machine()}"

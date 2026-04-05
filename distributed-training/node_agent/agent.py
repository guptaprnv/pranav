"""
Node agent — the main process that runs on each contributing device.

Lifecycle:
  start() → registers identity → joins P2P network → starts contribution
  run()   → event loop: poll queue, execute tasks, report contribution
  stop()  → graceful shutdown, end contribution session
"""
from __future__ import annotations

import logging
import os
import platform
import signal
import subprocess
import sys
import threading
import time
from typing import Optional

from p2p.peer import Peer, PeerInfo
from p2p.discovery import PeerDiscovery
from p2p.gossip import GossipProtocol
from ledger.contribution import ContributionLedger
from ledger.credits import CreditEngine
from node_agent.compute import detect_hardware_tier
from node_agent.task_runner import TaskRunner
from node_agent.local_api import start_local_api
from src.scheduler.placement import AssignmentResult, AssignmentStore
from src.scheduler.resource_manager import ResourceManager, NodeSpec

logger = logging.getLogger(__name__)


class NodeAgent:
    """
    The main agent that runs persistently on each device.
    Designed to be started by the desktop menu bar app (Mac)
    or background service (iPad via the companion app).
    """

    VERSION = "0.1.0"

    def __init__(
        self,
        owner: str,
        redis_url: str = "redis://localhost:6379/0",
        api_port: int = 7777,
        seeds: Optional[list] = None,
        device_type: Optional[str] = None,
    ):
        self.owner = owner
        self.redis_url = redis_url
        self.api_port = api_port
        self.seeds = seeds or []

        # Auto-detect device type
        self.device_type = device_type or self._detect_device_type()

        self.peer = Peer(
            port=api_port,
            device_type=self.device_type,
            version=self.VERSION,
        )
        self.discovery = PeerDiscovery(
            local_peer=self.peer,
            on_peer_found=self._on_peer_discovered,
            seeds=self.seeds,
            enable_mdns=True,
        )
        self.gossip = GossipProtocol(local_peer=self.peer)
        self.ledger = ContributionLedger(redis_url=redis_url)
        self.credits = CreditEngine(redis_url=redis_url)
        self.resource_manager = ResourceManager(redis_url=redis_url)
        self.assignment_store = AssignmentStore(redis_url=redis_url)
        self.task_runner = TaskRunner(
            owner=owner,
            redis_url=redis_url,
            workdir=os.getcwd(),
            on_job_finished=self._on_assignment_finished,
        )

        self._running = False
        self._session_id: Optional[str] = None
        self._hardware_tier = detect_hardware_tier()
        self._heartbeat_at = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        logger.info(
            f"NodeAgent starting | owner={self.owner} "
            f"device={self.device_type} tier={self._hardware_tier} "
            f"peer={self.peer.identity.peer_id[:8]}"
        )
        self._running = True

        # Start contribution session
        self._session_id = self.ledger.start_session(
            peer_id=self.peer.identity.peer_id,
            owner=self.owner,
            hardware_tier=self._hardware_tier,
        )
        self.resource_manager.register_node(
            NodeSpec(
                node_id=self.peer.identity.peer_id,
                hostname=self.peer.info.hostname,
                total_gpus=self.peer.info.gpu_count,
                total_cpus=self.peer.info.cpu_count,
                total_memory_gb=max(1, int(self.peer.info.memory_gb)),
                ip=self.peer.info.ip,
                hardware_tier=self._hardware_tier,
                accelerator_family=self._accelerator_family(),
                total_slots=self._total_slots(),
            )
        )

        # Join P2P network
        self.discovery.start()
        self.gossip.start()

        # Start local HTTP API for UI
        threading.Thread(
            target=start_local_api,
            args=(self, self.api_port),
            daemon=True,
            name="local-api",
        ).start()

        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGINT, self._handle_sigterm)

    def run(self) -> None:
        """Blocking event loop — call after start()."""
        self.start()
        logger.info("Node agent running. Press Ctrl+C to stop.")
        try:
            while self._running:
                now = time.time()
                if now - self._heartbeat_at >= 10:
                    self._heartbeat()
                    self._heartbeat_at = now
                if not self.task_runner.is_busy():
                    assignment = self.assignment_store.pop_assignment(self.peer.identity.peer_id)
                    if assignment and not self.task_runner.run_assignment(assignment):
                        self.assignment_store.requeue_assignment(assignment)
                time.sleep(2)
        finally:
            self.stop()

    def stop(self) -> None:
        if not self._running:
            return
        logger.info("Node agent shutting down…")
        self._running = False
        self.discovery.stop()
        self.gossip.stop()
        self.task_runner.stop()

        if self._session_id:
            record = self.ledger.end_session(self._session_id)
            if record:
                credits = self.credits.award(
                    owner=self.owner,
                    compute_units=record.compute_units_earned,
                    reason=f"session:{record.session_id}",
                )
                logger.info(
                    f"Contribution session ended: +{record.compute_units_earned:.2f} units "
                    f"({record.duration_seconds:.0f}s @ {self._hardware_tier}), "
                    f"+{credits:.2f} credits"
                )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_peer_discovered(self, info: PeerInfo) -> None:
        self.peer.add_or_update(info)
        logger.info(
            f"Peer discovered: {info.peer_id[:8]} @ {info.ip} "
            f"({info.device_type}, {info.gpu_count} GPU)"
        )

    def _on_assignment_finished(self, assignment, success: bool, error: str) -> None:
        self.assignment_store.complete_assignment(
            AssignmentResult(
                job_id=assignment.job_id,
                peer_id=self.peer.identity.peer_id,
                success=success,
                error=error,
            )
        )

    def _heartbeat(self) -> None:
        """Periodic tasks: refresh gossip, update peer info."""
        self.peer.info.last_seen = time.time()
        self.resource_manager.node_heartbeat(self.peer.identity.peer_id)

    def _handle_sigterm(self, sig, frame) -> None:
        self.stop()
        sys.exit(0)

    # ------------------------------------------------------------------
    # Status for UI
    # ------------------------------------------------------------------

    def status(self) -> dict:
        total_units = self.ledger.owner_total(self.owner)
        return {
            "peer_id": self.peer.identity.peer_id,
            "owner": self.owner,
            "device_type": self.device_type,
            "hardware_tier": self._hardware_tier,
            "accelerator_family": self._accelerator_family(),
            "total_slots": self._total_slots(),
            "peers_known": self.peer.peer_count(),
            "gossip_round": self.gossip.round_number,
            "session_id": self._session_id,
            "total_compute_units": round(total_units, 2),
            "current_job_id": self.task_runner.current_job_id(),
            "running": self._running,
        }

    # ------------------------------------------------------------------
    # Device detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_device_type() -> str:
        system = platform.system()
        machine = platform.machine()

        if system == "Darwin":
            # Check for iPad (when running Catalyst) vs Mac
            model = ""
            try:
                result = subprocess.check_output(
                    ["sysctl", "-n", "hw.model"], stderr=subprocess.DEVNULL
                ).decode().strip()
                model = result.lower()
            except Exception:
                pass
            if "mac mini" in model:
                return "mac_mini"
            if "macbook" in model:
                return "mac_laptop"
            return "mac"

        if system == "Linux":
            if "aarch64" in machine:
                return "arm_server"
            return "linux_workstation"

        if system == "Windows":
            return "windows_workstation"

        return "unknown"

    def _accelerator_family(self) -> str:
        override = os.environ.get("DT_ACCELERATOR_FAMILY")
        if override:
            return override
        if self.peer.info.gpu_count > 0:
            return "cuda"
        if self._hardware_tier.startswith("apple_") or self._hardware_tier.startswith("ipad_"):
            return "mps"
        return "cpu"

    def _total_slots(self) -> int:
        if self.peer.info.gpu_count > 0:
            return self.peer.info.gpu_count
        return 1

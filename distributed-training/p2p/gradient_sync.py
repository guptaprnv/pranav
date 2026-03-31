"""
Gradient synchronization channel — direct P2P gradient exchange.

Used during federated / split training across heterogeneous devices.
Protocol:
  1. Coordinator sends "SYNC_START" + round_id to all participants
  2. Each peer computes local gradients and sends them to coordinator
  3. Coordinator aggregates (FedAvg by default) and broadcasts averaged gradients
  4. All peers apply the update

Transport: TCP for reliability (unlike gossip which uses UDP).
"""
from __future__ import annotations

import io
import json
import logging
import socket
import struct
import threading
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

SYNC_PORT = 7780
HEADER_FMT = "!I"    # 4-byte big-endian message length prefix
HEADER_SIZE = struct.calcsize(HEADER_FMT)


def _send_msg(sock: socket.socket, data: bytes) -> None:
    """Length-prefixed framing."""
    header = struct.pack(HEADER_FMT, len(data))
    sock.sendall(header + data)


def _recv_msg(sock: socket.socket) -> bytes:
    header = _recv_exact(sock, HEADER_SIZE)
    length = struct.unpack(HEADER_FMT, header)[0]
    return _recv_exact(sock, length)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Peer disconnected")
        buf += chunk
    return buf


class GradientSyncChannel:
    """
    Coordinator-side gradient aggregation server.

    Workers connect, send serialized gradients, receive averaged result.
    Uses FedAvg weighted by each peer's contribution score so that
    high-contributors have proportional influence on the model.
    """

    def __init__(self, local_peer, round_id: str = "0", num_peers: int = 1):
        self.local = local_peer
        self.round_id = round_id
        self.num_peers = num_peers
        self._received: Dict[str, dict] = {}   # peer_id → {grads, weight}
        self._lock = threading.Lock()
        self._ready = threading.Event()

    def serve_aggregation(
        self,
        port: int = SYNC_PORT,
        on_aggregate: Optional[Callable[[dict], None]] = None,
    ) -> None:
        """Start accepting gradient submissions (blocking until num_peers received)."""
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("", port))
        srv.listen(self.num_peers)
        srv.settimeout(60)
        logger.info(f"Gradient aggregation server on port {port}, waiting for {self.num_peers} peers")

        threads = []
        while len(self._received) < self.num_peers:
            try:
                conn, addr = srv.accept()
                t = threading.Thread(
                    target=self._handle_peer, args=(conn, addr), daemon=True
                )
                t.start()
                threads.append(t)
            except socket.timeout:
                logger.warning("Timeout waiting for peers")
                break

        for t in threads:
            t.join(timeout=30)

        averaged = self._fedavg()
        if on_aggregate:
            on_aggregate(averaged)
        srv.close()
        return averaged

    def submit_gradients(
        self,
        coordinator_ip: str,
        gradients: dict,
        weight: float = 1.0,
        port: int = SYNC_PORT,
    ) -> dict:
        """
        Worker: send local gradients to coordinator and receive averaged result.
        `gradients` is a dict: layer_name → list[float]
        `weight`    is this peer's contribution score (used in FedAvg weighting)
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(60)
        sock.connect((coordinator_ip, port))

        payload = json.dumps({
            "peer_id": self.local.identity.peer_id,
            "round_id": self.round_id,
            "weight": weight,
            "gradients": gradients,
        }).encode()
        _send_msg(sock, payload)

        response = _recv_msg(sock)
        sock.close()
        return json.loads(response.decode())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _handle_peer(self, conn: socket.socket, addr) -> None:
        try:
            data = _recv_msg(conn)
            msg = json.loads(data.decode())
            peer_id = msg["peer_id"]
            with self._lock:
                self._received[peer_id] = {
                    "gradients": msg["gradients"],
                    "weight": msg.get("weight", 1.0),
                }
            logger.info(f"Received gradients from {peer_id} ({addr[0]})")

            # Wait for all peers then send averaged result back
            while len(self._received) < self.num_peers:
                threading.Event().wait(0.1)
            averaged = self._fedavg()
            _send_msg(conn, json.dumps(averaged).encode())
        except Exception as e:
            logger.error(f"Gradient sync error from {addr}: {e}")
        finally:
            conn.close()

    def _fedavg(self) -> dict:
        """Weighted FedAvg: Σ(weight_i * grads_i) / Σ(weight_i)."""
        if not self._received:
            return {}
        total_weight = sum(v["weight"] for v in self._received.values())
        averaged: Dict[str, list] = {}
        for peer_data in self._received.values():
            w = peer_data["weight"] / total_weight
            for layer, grads in peer_data["gradients"].items():
                if layer not in averaged:
                    averaged[layer] = [0.0] * len(grads)
                averaged[layer] = [a + w * g for a, g in zip(averaged[layer], grads)]
        return averaged

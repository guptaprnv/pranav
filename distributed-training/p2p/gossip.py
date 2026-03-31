"""
Gossip protocol — epidemic dissemination of cluster state.

Every GOSSIP_INTERVAL seconds each node:
  1. Picks 3 random peers (fan-out)
  2. Sends its full known-peer table (compressed JSON)
  3. Merges incoming tables, keeping freshest entries

This gives eventual consistency with O(log N) convergence time.
No central coordinator — works purely P2P.
"""
from __future__ import annotations

import json
import logging
import random
import socket
import threading
import time
import zlib
from typing import Dict, List

from .peer import Peer, PeerInfo

logger = logging.getLogger(__name__)

GOSSIP_PORT = 7779
GOSSIP_INTERVAL = 10      # seconds
GOSSIP_FAN_OUT = 3        # peers to gossip with per round
MAX_PAYLOAD = 65000       # UDP safe limit


class GossipProtocol:
    """
    Runs in background threads; keeps every node's view of the cluster
    eventually consistent without any central server.
    """

    def __init__(self, local_peer: Peer):
        self.local = local_peer
        self._running = False
        self._lock = threading.Lock()
        self._round = 0

    def start(self) -> None:
        self._running = True
        threading.Thread(target=self._sender, daemon=True, name="gossip-send").start()
        threading.Thread(target=self._receiver, daemon=True, name="gossip-recv").start()
        logger.info("Gossip protocol started")

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Sender — push our view to random peers
    # ------------------------------------------------------------------

    def _sender(self) -> None:
        while self._running:
            time.sleep(GOSSIP_INTERVAL)
            peers = self.local.all_peers()
            if not peers:
                continue

            targets = random.sample(peers, min(GOSSIP_FAN_OUT, len(peers)))
            payload = self._encode_table()

            for peer in targets:
                self._send_udp(peer.ip, GOSSIP_PORT, payload)

            self._round += 1
            self.local.remove_stale()

    def _encode_table(self) -> bytes:
        table = [p.to_dict() for p in self.local.all_peers()]
        table.append(self.local.info.to_dict())   # include self
        raw = json.dumps(table).encode()
        compressed = zlib.compress(raw, level=6)
        if len(compressed) > MAX_PAYLOAD:
            # If table is too large, gossip a random subset
            subset = random.sample(table, max(1, len(table) // 2))
            compressed = zlib.compress(json.dumps(subset).encode(), level=6)
        return compressed

    def _send_udp(self, ip: str, port: int, payload: bytes) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(payload, (ip, port))
            sock.close()
        except Exception as e:
            logger.debug(f"Gossip send to {ip}:{port} failed: {e}")

    # ------------------------------------------------------------------
    # Receiver — accept incoming gossip and merge
    # ------------------------------------------------------------------

    def _receiver(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass
        sock.bind(("", GOSSIP_PORT))
        sock.settimeout(2.0)

        while self._running:
            try:
                data, _ = sock.recvfrom(MAX_PAYLOAD + 100)
                self._merge(data)
            except socket.timeout:
                continue
            except Exception as e:
                logger.debug(f"Gossip recv error: {e}")

    def _merge(self, payload: bytes) -> None:
        try:
            raw = zlib.decompress(payload)
            table: List[Dict] = json.loads(raw)
        except Exception as e:
            logger.debug(f"Gossip decode error: {e}")
            return

        for entry in table:
            try:
                info = PeerInfo.from_dict(entry)
                existing = self.local.get_peer(info.peer_id)
                if existing is None or info.last_seen > existing.last_seen:
                    self.local.add_or_update(info)
            except Exception as e:
                logger.debug(f"Bad gossip entry: {e}")

    @property
    def round_number(self) -> int:
        return self._round

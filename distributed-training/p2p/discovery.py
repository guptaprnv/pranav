"""
Peer discovery — finds other nodes on the same LAN or configured seed list.

Strategy (layered, most local first):
  1. mDNS/Bonjour  — zero-config LAN discovery (works great for Mac mini clusters)
  2. UDP broadcast  — fallback for environments without mDNS
  3. Static seeds   — list of known IPs/hostnames (for cloud / multi-site)

On iPad: only UDP broadcast + static seeds (mDNS requires entitlement).
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
from typing import Callable, List, Optional

from .peer import Peer, PeerInfo

logger = logging.getLogger(__name__)

DISCOVERY_PORT = 7778
BROADCAST_INTERVAL = 15          # seconds
MDNS_SERVICE = "_dtrain._tcp.local."


class PeerDiscovery:
    """
    Discovers peers and calls `on_peer_found(PeerInfo)` for each new one.
    """

    def __init__(
        self,
        local_peer: Peer,
        on_peer_found: Callable[[PeerInfo], None],
        seeds: Optional[List[str]] = None,
        enable_mdns: bool = True,
    ):
        self.local = local_peer
        self.on_peer_found = on_peer_found
        self.seeds = seeds or []
        self.enable_mdns = enable_mdns
        self._running = False
        self._threads: List[threading.Thread] = []

    def start(self) -> None:
        self._running = True
        self._threads = [
            threading.Thread(target=self._udp_listener, daemon=True, name="udp-listen"),
            threading.Thread(target=self._udp_broadcaster, daemon=True, name="udp-bcast"),
            threading.Thread(target=self._seed_dialer, daemon=True, name="seed-dial"),
        ]
        if self.enable_mdns:
            self._threads.append(
                threading.Thread(target=self._mdns_advertise, daemon=True, name="mdns")
            )
        for t in self._threads:
            t.start()
        logger.info(f"Discovery started | peer={self.local.identity.peer_id[:8]} "
                    f"seeds={self.seeds}")

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # UDP broadcast (LAN-wide)
    # ------------------------------------------------------------------

    def _udp_broadcaster(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        payload = json.dumps(self.local.info.to_dict()).encode()
        while self._running:
            try:
                sock.sendto(payload, ("<broadcast>", DISCOVERY_PORT))
            except Exception as e:
                logger.debug(f"Broadcast error: {e}")
            time.sleep(BROADCAST_INTERVAL)

    def _udp_listener(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass
        sock.bind(("", DISCOVERY_PORT))
        sock.settimeout(2.0)
        while self._running:
            try:
                data, addr = sock.recvfrom(4096)
                info = PeerInfo.from_dict(json.loads(data.decode()))
                if info.peer_id != self.local.identity.peer_id:
                    info.ip = addr[0]    # trust the actual source IP
                    self.on_peer_found(info)
            except socket.timeout:
                continue
            except Exception as e:
                logger.debug(f"UDP listener error: {e}")

    # ------------------------------------------------------------------
    # Static seed dialer
    # ------------------------------------------------------------------

    def _seed_dialer(self) -> None:
        """Connect to known seed nodes and fetch their peer table."""
        while self._running:
            for seed in self.seeds:
                try:
                    host, port = (seed.split(":") + ["7777"])[:2]
                    self._fetch_peer_info(host, int(port))
                except Exception as e:
                    logger.debug(f"Seed {seed} unreachable: {e}")
            time.sleep(30)

    def _fetch_peer_info(self, host: str, port: int) -> None:
        """HTTP GET /peer_info from a seed node (handled by node_agent HTTP server)."""
        import urllib.request
        url = f"http://{host}:{port}/peer_info"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
            info = PeerInfo.from_dict(data)
            self.on_peer_found(info)

    # ------------------------------------------------------------------
    # mDNS (Bonjour) — zero-config LAN
    # ------------------------------------------------------------------

    def _mdns_advertise(self) -> None:
        try:
            from zeroconf import ServiceInfo, Zeroconf
            import socket as _socket
            zc = Zeroconf()
            svc = ServiceInfo(
                MDNS_SERVICE,
                f"{self.local.identity.peer_id[:8]}.{MDNS_SERVICE}",
                addresses=[_socket.inet_aton(self.local.info.ip)],
                port=self.local.port,
                properties={
                    "peer_id": self.local.identity.peer_id,
                    "version": self.local.version,
                    "device": self.local.device_type,
                },
            )
            zc.register_service(svc)
            logger.info("mDNS service registered")
            while self._running:
                time.sleep(5)
            zc.unregister_service(svc)
            zc.close()
        except ImportError:
            logger.debug("zeroconf not installed — mDNS disabled")
        except Exception as e:
            logger.warning(f"mDNS error: {e}")

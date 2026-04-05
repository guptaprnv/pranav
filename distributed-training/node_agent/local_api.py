"""
Local HTTP API — lightweight server for the desktop/mobile UI to query.

Endpoints:
  GET /status       → agent status + contribution summary
  GET /peer_info    → this node's PeerInfo (used by seed dialer)
  GET /peers        → list of known peers
  POST /start       → start contributing compute
  POST /stop        → stop contributing
  GET /credits      → credit balance

Intentionally minimal — may be bound to localhost for single-device use or
0.0.0.0 when other LAN devices need to reach the agent.
"""
from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from node_agent.agent import NodeAgent

logger = logging.getLogger(__name__)


def start_local_api(agent: "NodeAgent", port: int = 7777, host: str = "0.0.0.0") -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # silence default request log

        def do_GET(self):
            if self.path == "/status":
                self._json(agent.status())
            elif self.path == "/peer_info":
                self._json(agent.peer.info.to_dict())
            elif self.path == "/peers":
                self._json([p.to_dict() for p in agent.peer.all_peers()])
            elif self.path == "/credits":
                from ledger.credits import CreditEngine
                ce = CreditEngine(redis_url=agent.redis_url)
                bal = ce.balance(agent.owner)
                from dataclasses import asdict
                self._json(asdict(bal))
            else:
                self._error(404, "not found")

        def do_POST(self):
            if self.path == "/stop":
                agent.stop()
                self._json({"ok": True, "message": "Agent stopping"})
            else:
                self._error(404, "not found")

        def _json(self, data: dict, status: int = 200) -> None:
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status: int, msg: str) -> None:
            self._json({"error": msg}, status)

    server = HTTPServer((host, port), Handler)
    logger.info(f"Local API listening on http://{host}:{port}")
    server.serve_forever()

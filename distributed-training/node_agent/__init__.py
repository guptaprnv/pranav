"""
Node agent — runs on every device (Mac mini, iPad, cloud VM).

Responsibilities:
  1. Register with the P2P network and maintain identity
  2. Report hardware capabilities and availability
  3. Accept and execute assigned training tasks
  4. Report contribution back to the ledger
  5. Expose a local HTTP API for the desktop/mobile UI
"""
from .agent import NodeAgent

__all__ = ["NodeAgent"]

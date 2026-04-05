"""
P2P networking layer — peer discovery, identity, and cluster state gossip.

Architecture:
  - Each node has a stable Ed25519 keypair (identity)
  - Discovery: mDNS for LAN (Mac mini cluster) + UDP broadcast fallback
  - Gossip: periodic exchange of peer tables and cluster health
  - Direct connections: used for gradient sync during training

Scales naturally: adding more Mac minis just adds more peers.
"""
from .peer import Peer, PeerIdentity
from .discovery import PeerDiscovery
from .gossip import GossipProtocol
from .gradient_sync import GradientSyncChannel

__all__ = ["Peer", "PeerIdentity", "PeerDiscovery", "GossipProtocol", "GradientSyncChannel"]

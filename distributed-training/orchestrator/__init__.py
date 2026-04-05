"""
Orchestration layer — dispatches training tasks across peers,
manages model state synchronization, and handles node failures.
"""
from .task_dispatcher import TaskDispatcher
from .sync_manager import SyncManager
from .fault_handler import FaultHandler

__all__ = ["TaskDispatcher", "SyncManager", "FaultHandler"]

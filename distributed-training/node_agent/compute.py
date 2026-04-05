"""
Hardware detection — identifies the device tier for contribution weighting.
"""
from __future__ import annotations

import os
import platform
import subprocess
import logging

logger = logging.getLogger(__name__)


def detect_hardware_tier() -> str:
    """
    Returns one of the tier keys defined in ledger/contribution.py TIER_MULTIPLIERS.
    """
    override = os.environ.get("DT_HARDWARE_TIER")
    if override:
        return override

    system = platform.system()

    # macOS Apple Silicon detection
    if system == "Darwin":
        return _detect_apple_silicon()

    # NVIDIA GPU detection
    gpu = _detect_nvidia_gpu()
    if gpu:
        return gpu

    return "cpu_server" if _is_server() else "cpu_laptop"


def _detect_apple_silicon() -> str:
    try:
        chip = subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], stderr=subprocess.DEVNULL
        ).decode().strip().lower()
    except Exception:
        chip = ""

    if not chip:
        try:
            chip = subprocess.check_output(
                ["system_profiler", "SPHardwareDataType"],
                stderr=subprocess.DEVNULL,
            ).decode().strip().lower()
        except Exception:
            chip = ""

    try:
        model = subprocess.check_output(
            ["sysctl", "-n", "hw.model"], stderr=subprocess.DEVNULL
        ).decode().strip().lower()
    except Exception:
        model = ""

    # iPad detection (running via Catalyst or iOS)
    if "ipad" in model:
        if "m2" in chip:
            return "ipad_m2"
        return "ipad_m1"

    # Mac Silicon tiers
    if "m3" in chip:
        return "apple_m3"
    if "m2" in chip:
        return "apple_m2"
    if "m1" in chip:
        return "apple_m1"

    # Fallback: if we are on arm64 macOS, treat as Apple Silicon even when the
    # chip string is unavailable from sysctl on this machine/runtime.
    if platform.machine().lower() == "arm64":
        return "apple_m1"

    return "cpu_laptop"


def _detect_nvidia_gpu() -> str | None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            stderr=subprocess.DEVNULL,
        ).decode().strip().lower()

        if "h100" in out:
            return "h100"
        if "a100" in out:
            return "a100"
        if "v100" in out:
            return "v100"
        if "4090" in out or "rtx 4090" in out:
            return "rtx4090"
        if "3090" in out or "rtx 3090" in out:
            return "rtx3090"
        return "unknown"
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _is_server() -> bool:
    try:
        import psutil
        return psutil.virtual_memory().total > 32 * 1024 ** 3  # >32GB = server
    except ImportError:
        return False


def get_available_memory_gb() -> float:
    try:
        import psutil
        return round(psutil.virtual_memory().available / 1e9, 1)
    except ImportError:
        return 0.0


def get_cpu_utilization() -> float:
    try:
        import psutil
        return psutil.cpu_percent(interval=1)
    except ImportError:
        return 0.0

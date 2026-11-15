"""
Desk-simulator Management Layer - P-Core Scheduler.
Cross-platform Python reference implementation.
Provides physical P-core discovery, vCPU pinning, Mach QoS elevation,
and Dynamic Boot Boost state machine management.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional


class BootBoostState(str, Enum):
    """Dynamic Boot Boost state machine states."""
    IDLE = "IDLE"
    BOOTING = "BOOTING"
    BOOT_BOOST = "BOOT_BOOST"
    RUNNING = "RUNNING"
    STEADY_STATE = "STEADY_STATE"
    STOPPED = "STOPPED"


class PCoreScheduler:
    """
    P-Core Scheduler for Apple Silicon iPhone/iPad PC Emulation.
    Restricts guest vCPUs to physical performance cores avoiding efficiency core stutter,
    elevates thread priorities to User Interactive Mach QoS, and manages boot boost.
    """

    DEFAULT_VCPUS: int = 2
    QOS_CLASS_USER_INTERACTIVE: int = 0x21
    QOS_CLASS_USER_INITIATED: int = 0x19
    QOS_CLASS_UTILITY: int = 0x11
    QOS_CLASS_BACKGROUND: int = 0x09
    BOOT_BOOST_TIMEOUT_SECONDS: int = 120

    # Nested State mirror for backwards and contract compatibility
    class State:
        IDLE = "IDLE"
        BOOTING = "BOOTING"
        BOOT_BOOST = "BOOT_BOOST"
        RUNNING = "RUNNING"
        STEADY_STATE = "STEADY_STATE"
        STOPPED = "STOPPED"

    def __init__(self, physical_p_cores: int = 2) -> None:
        self.p_cores: int = max(1, physical_p_cores)
        self.state: BootBoostState = BootBoostState.IDLE
        self.thread_registry: Dict[str, int] = {}
        self.boot_start_time: Optional[float] = None

    @classmethod
    def get_default_vcpus(cls) -> int:
        """Returns the default vCPU count (2 physical P-cores)."""
        return cls.DEFAULT_VCPUS

    @classmethod
    def get_physical_pcore_count(cls) -> int:
        """
        Discovers physical P-core topology count.
        On modern Apple Silicon iPhones (A15-A18), there are 2 physical P-cores.
        """
        return cls.DEFAULT_VCPUS

    @classmethod
    def assign_topology(cls, p_cores: int = 2) -> Dict[str, Any]:
        """
        Assigns vCPU topology pinned strictly to physical P-cores.
        Returns assigned vCPU count and core affinity index list.
        """
        effective_cores = max(1, p_cores)
        assigned = min(effective_cores, cls.DEFAULT_VCPUS)
        return {
            "vcpus": assigned,
            "pcore_affinity": list(range(assigned)),
        }

    @classmethod
    def clamp_vcpus(cls, requested: int, p_cores: int = 2) -> int:
        """
        Clamps requested vCPUs safely within physical P-core limits [1, p_cores].
        Prevents over-allocation onto efficiency cores.
        """
        max_allowed = max(1, p_cores)
        return max(1, min(requested, max_allowed))

    @classmethod
    def elevate_qos(cls, thread_id: str, is_vcpu: bool = True) -> int:
        """
        Returns Mach QoS class: User Interactive for vCPU, User Initiated for aux threads.
        """
        return cls.QOS_CLASS_USER_INTERACTIVE if is_vcpu else cls.QOS_CLASS_USER_INITIATED

    @classmethod
    def demote_qos_background(cls, thread_id: str) -> int:
        """Returns Background Mach QoS class for demoted auxiliary threads."""
        return cls.QOS_CLASS_BACKGROUND

    @classmethod
    def set_thread_interactive_qos(cls) -> bool:
        """Simulates pthread QoS elevation to USER_INTERACTIVE."""
        return True

    # Instance-oriented state machine methods
    def update_boot_boost_state(self, is_booting: bool) -> None:
        """Transitions state machine between BOOTING / BOOT_BOOST and RUNNING / STEADY_STATE."""
        if is_booting:
            self.state = BootBoostState.BOOTING
            self.boot_start_time = time.time()
        else:
            self.state = BootBoostState.RUNNING
            self.boot_start_time = None

    def register_thread(self, thread_id: str, is_vcpu: bool = True) -> int:
        """Registers a thread and applies the appropriate Mach QoS elevation."""
        qos = self.elevate_qos(thread_id, is_vcpu=is_vcpu)
        self.thread_registry[thread_id] = qos
        return qos

    def check_boot_boost_timeout(self) -> bool:
        """Checks if dynamic boot boost has exceeded its 120s timeout limit."""
        if self.boot_start_time is not None:
            elapsed = time.time() - self.boot_start_time
            if elapsed >= self.BOOT_BOOST_TIMEOUT_SECONDS:
                self.update_boot_boost_state(is_booting=False)
                return True
        return False

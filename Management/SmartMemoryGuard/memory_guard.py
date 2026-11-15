"""
Desk-simulator Management Layer - Smart Memory Guard.
Cross-platform Python reference implementation.
Provides safe guest RAM calculation, QMP VirtIO-ballooning commands,
and 90% Jetsam emergency auto-pause triggers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MemoryPressureLevel(str, Enum):
    """Memory pressure levels corresponding to Darwin dispatch source notifications."""
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class MemoryEntitlements:
    """Represents iOS entitlements for increased memory and extended virtual addressing."""
    increased_memory_limit: bool = False
    extended_virtual_addressing: bool = False
    ceiling_ratio: float = 0.50

    def to_dict(self) -> Dict[str, Any]:
        return {
            "increased_memory_limit": self.increased_memory_limit,
            "extended_virtual_addressing": self.extended_virtual_addressing,
            "ceiling_ratio": self.ceiling_ratio,
        }


@dataclass
class QMPCommand:
    """Represents a QEMU Monitor Protocol (QMP) JSON-RPC command."""
    execute: str
    arguments: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        if self.arguments:
            return {"execute": self.execute, "arguments": self.arguments}
        return {"execute": self.execute}


class MemoryGuard:
    """
    Smart Memory Guard service.
    Implements memory budget calculation, dynamic ballooning reflex,
    and Jetsam emergency protection.
    """

    # 450 MB reserved for host iOS, Metal shaders, and TCG code cache
    SAFETY_BUFFER_BYTES: int = 450 * 1024 * 1024

    # 1024 MB safe guest floor
    MIN_SAFE_FLOOR_BYTES: int = 1024 * 1024 * 1024

    # 90% danger threshold for Jetsam termination prevention
    DANGER_THRESHOLD_PERCENT: float = 0.90

    INCREASED_MEMORY_KEY: str = "com.apple.developer.kernel.increased-memory-limit"
    EXTENDED_VA_KEY: str = "extended-virtual-addressing"

    def __init__(self, increased_memory: bool = False, extended_va: bool = False) -> None:
        self.entitlements = self._compute_entitlements(increased_memory, extended_va)
        self.last_available_bytes: int = 0
        self.current_usage_bytes: int = 0
        self.memory_ceiling_bytes: int = 0
        self.is_emergency_paused: bool = False
        self.pressure_history: List[Dict[str, Any]] = []

    @staticmethod
    def _compute_entitlements(increased_memory: bool, extended_va: bool) -> MemoryEntitlements:
        if increased_memory and extended_va:
            ratio = 0.80
        elif increased_memory:
            ratio = 0.75
        else:
            ratio = 0.50
        return MemoryEntitlements(
            increased_memory_limit=increased_memory,
            extended_virtual_addressing=extended_va,
            ceiling_ratio=ratio,
        )

    @classmethod
    def detect_entitlements(
        cls, increased_memory: bool = False, extended_va: bool = False
    ) -> Dict[str, Any]:
        """Probes or validates entitlements and returns active ceiling configuration dictionary."""
        ent = cls._compute_entitlements(increased_memory, extended_va)
        return ent.to_dict()

    @classmethod
    def calculate_safe_guest_ram(cls, available_bytes: int) -> int:
        """
        Calculates safe guest RAM adhering to 450MB safety reserve and 1024MB safe floor.
        Guards against unsigned integer underflow when available_bytes <= SAFETY_BUFFER_BYTES.
        """
        if available_bytes > cls.SAFETY_BUFFER_BYTES:
            calculated = available_bytes - cls.SAFETY_BUFFER_BYTES
            return max(calculated, cls.MIN_SAFE_FLOOR_BYTES)
        return cls.MIN_SAFE_FLOOR_BYTES

    @classmethod
    def handle_memory_pressure(
        cls, level: str | MemoryPressureLevel, available_bytes: int
    ) -> Optional[Dict[str, Any]]:
        """
        Processes memory pressure events and generates VirtIO-Balloon QMP command.
        - normal: returns None
        - warning: deflates to safe guest RAM
        - critical: aggressively deflates to emergency safe floor or half of safe RAM
        """
        level_str = level.value.lower() if isinstance(level, MemoryPressureLevel) else str(level).lower()
        if level_str == "normal":
            return None
        elif level_str == "warning":
            safe_ram = cls.calculate_safe_guest_ram(available_bytes)
            return {"execute": "balloon", "arguments": {"value": safe_ram}}
        elif level_str == "critical":
            safe_ram = cls.calculate_safe_guest_ram(available_bytes)
            emergency_ram = max(cls.MIN_SAFE_FLOOR_BYTES, safe_ram // 2)
            return {"execute": "balloon", "arguments": {"value": emergency_ram}}
        else:
            raise ValueError(f"Unknown memory pressure level: {level}")

    @classmethod
    def check_jetsam_emergency(cls, current_usage_bytes: int, memory_ceiling_bytes: int) -> bool:
        """
        Determines whether memory usage has reached 90% danger threshold.
        Returns True if emergency pause is required to avoid SIGKILL.
        """
        if memory_ceiling_bytes <= 0:
            return True
        return current_usage_bytes >= (memory_ceiling_bytes * cls.DANGER_THRESHOLD_PERCENT)

    @classmethod
    def emergency_auto_pause(cls) -> Dict[str, Any]:
        """Returns QMP pause command."""
        return {"execute": "stop"}

    # Instance-oriented methods for stateful runtime service
    def update_usage(self, usage_bytes: int, ceiling_bytes: int) -> bool:
        """Updates internal state and checks for emergency pause."""
        self.current_usage_bytes = usage_bytes
        self.memory_ceiling_bytes = ceiling_bytes
        emergency = self.check_jetsam_emergency(usage_bytes, ceiling_bytes)
        if emergency:
            self.is_emergency_paused = True
        return emergency

    def on_pressure_event(
        self, level: str | MemoryPressureLevel, available_bytes: int
    ) -> Optional[Dict[str, Any]]:
        """Handles pressure event, updates history, and returns QMP balloon command."""
        self.last_available_bytes = available_bytes
        cmd = self.handle_memory_pressure(level, available_bytes)
        self.pressure_history.append({
            "level": str(level),
            "available_bytes": available_bytes,
            "command": cmd,
        })
        return cmd

    def resume_vm(self) -> Dict[str, Any]:
        """Resumes VM execution after memory pressure clears."""
        self.is_emergency_paused = False
        return {"execute": "cont"}

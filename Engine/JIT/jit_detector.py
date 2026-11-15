"""
Desk-simulator Engine Layer - JIT Detector.
Cross-platform Python reference implementation.
Provides runtime JIT entitlement detection (CS_DEBUGGED, TrollStore, AltJIT, SideStore).
Mirrors Engine/JIT/JITDetector.swift.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class JITSource(str, Enum):
    """Runtime JIT activation source classification."""
    TROLLSTORE = "TROLLSTORE"
    ALTJIT = "ALTJIT"
    SIDESTORE = "SIDESTORE"
    NONE = "NONE"

    @property
    def display_name(self) -> str:
        if self == JITSource.TROLLSTORE:
            return "TrollStore (Unrestricted CS_DEBUGGED)"
        elif self == JITSource.ALTJIT:
            return "AltJIT (AltServer JIT Attach)"
        elif self == JITSource.SIDESTORE:
            return "SideStore (Local VPN WireGuard JIT)"
        return "No JIT Active"


@dataclass
class JITStatus:
    """Status container for JIT capability and active source."""
    is_available: bool
    source: JITSource
    advisory: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_available": self.is_available,
            "source": self.source.value,
            "advisory": self.advisory,
        }

    def __getitem__(self, item: str) -> Any:
        # Dictionary-compatible access for backwards compatibility
        return getattr(self, item)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)


class JITDetector:
    """
    JIT Detector service.
    Detects runtime JIT availability for the emulation engine.
    """

    JITSource = JITSource
    JITStatus = JITStatus

    @classmethod
    def detect_jit(
        cls,
        has_cs_debugged: Optional[bool] = None,
        env_marker: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Detects runtime JIT capability and active entitlement mechanism.
        Returns dictionary containing is_available, source, and advisory message.
        """
        if has_cs_debugged is not None:
            is_debugged = has_cs_debugged
        else:
            is_debugged = False

        marker = env_marker if env_marker is not None else os.environ.get("JIT_SOURCE", "")
        lower = marker.lower()

        if is_debugged:
            if "trollstore" in lower:
                source = JITSource.TROLLSTORE
            elif "sidestore" in lower:
                source = JITSource.SIDESTORE
            else:
                source = JITSource.ALTJIT
            return {
                "is_available": True,
                "source": source.value,
                "advisory": f"JIT is active via {source.display_name}. TCG code cache enabled.",
            }
        else:
            return {
                "is_available": False,
                "source": JITSource.NONE.value,
                "advisory": "JIT is not active. Please enable JIT via SideStore or AltStore to launch VM.",
            }


# Backwards compatibility alias for _ContractJITHook and legacy naming
JITHook = JITDetector
JITMethod = JITSource

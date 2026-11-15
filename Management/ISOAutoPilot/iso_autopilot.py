"""
Desk-simulator Management Layer - ISO Auto-Pilot.
Cross-platform Python reference implementation.
Provides ISO header inspection and OS identification, VirtIO-win driver auto-injection
configuration generation, and Windows 11 bypass XML generation.
"""

from __future__ import annotations

import os
import re
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class OperatingSystemType(str, Enum):
    """Identified guest operating system classification."""
    WINDOWS_11 = "WINDOWS_11"
    WINDOWS_10 = "WINDOWS_10"
    LINUX_UBUNTU = "LINUX_UBUNTU"
    UNKNOWN = "UNKNOWN"


class ISOAutoPilot:
    """
    ISO Auto-Pilot service.
    Automatically inspects ISO media, injects appropriate virtualization drivers,
    and synthesizes unattended installation bypasses.
    """

    # Nested type mirror for interface contract compatibility
    OperatingSystemType = OperatingSystemType

    def __init__(self) -> None:
        self.last_detected_os: OperatingSystemType = OperatingSystemType.UNKNOWN
        self.cached_configs: Dict[str, Any] = {}

    @classmethod
    def identify_operating_system(cls, header_bytes: bytes) -> str:
        """
        Inspects ISO header bytes (typically primary volume descriptor around offset 0x8000)
        and identifies OS type. Handles ASCII, UTF-8, and UTF-16 LE/BE encodings.
        """
        if not header_bytes or len(header_bytes) < 16:
            return cls.OperatingSystemType.UNKNOWN

        # Strip null bytes to normalize UTF-16 LE/BE and Joliet/UDF volume descriptor strings
        upper = header_bytes.replace(b"\x00", b"").upper()
        if b"MICROSOFT WINDOWS 11" in upper or b"WIN11" in upper:
            return cls.OperatingSystemType.WINDOWS_11
        if b"MICROSOFT WINDOWS 10" in upper or b"WIN10" in upper:
            return cls.OperatingSystemType.WINDOWS_10
        if b"UBUNTU" in upper or b"LINUX" in upper:
            return cls.OperatingSystemType.LINUX_UBUNTU
        return cls.OperatingSystemType.UNKNOWN

    @classmethod
    def generate_virtio_injection_config(
        cls, os_type: Union[str, OperatingSystemType]
    ) -> Dict[str, Any]:
        """
        Generates VirtIO driver auto-injection configuration based on guest OS.
        Windows guests receive VirtIO CD-ROM drive parameter with essential drivers;
        Linux guests rely on native in-kernel VirtIO modules.
        """
        os_key = os_type.value if isinstance(os_type, OperatingSystemType) else str(os_type).upper()

        if os_key in (
            cls.OperatingSystemType.WINDOWS_11,
            cls.OperatingSystemType.WINDOWS_10,
            "WINDOWS_11",
            "WINDOWS_10",
            "WIN11",
            "WIN10",
        ):
            return {
                "inject_drivers": True,
                "native_drivers": False,
                "target_os": os_key,
                "drivers": ["viostor", "netkvm", "balloon", "vioscsi", "qxl"],
                "drive_param": "-drive file=virtio-win.iso,media=cdrom,readonly=on",
            }
        elif os_key in (cls.OperatingSystemType.LINUX_UBUNTU, "LINUX_UBUNTU", "UBUNTU", "LINUX"):
            return {
                "inject_drivers": False,
                "native_drivers": True,
                "target_os": os_key,
                "drivers": ["virtio_pci", "virtio_blk", "virtio_net"],
                "drive_param": "",
            }
        else:
            return {
                "inject_drivers": False,
                "native_drivers": False,
                "target_os": cls.OperatingSystemType.UNKNOWN,
                "drivers": [],
                "drive_param": "",
            }

    @classmethod
    def generate_windows11_bypass_xml(cls, local_username: str = "DeskUser") -> str:
        """
        Generates unattended answer file (autounattend.xml) that automatically bypasses
        Windows 11 hardware checks (TPM 2.0, SecureBoot, RAM, CPU) and creates a local
        administrator account.
        Properly strips control characters and escapes XML entities to prevent XML injection
        and ensure well-formed XML parsing.
        """
        raw = str(local_username) if local_username is not None else "DeskUser"
        # Strip ASCII control characters (including \r, \n, \t, etc.)
        cleaned = re.sub(r"[\x00-\x1f\x7f]", "", raw).strip()
        if not cleaned:
            cleaned = "DeskUser"

        # XML entity escaping: ampersand MUST be replaced first
        username = (
            cleaned.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

        xml_template = f"""<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend">
    <settings pass="windowsPE">
        <component name="Microsoft-Windows-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
            <RunSynchronous>
                <RunSynchronousCommand wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
                    <Order>1</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassTPMCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
                    <Order>2</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassSecureBootCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
                    <Order>3</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassRAMCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
                    <Order>4</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassCPUCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
                    <Order>5</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassStorageCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
            </RunSynchronous>
            <UserData>
                <AcceptEula>true</AcceptEula>
            </UserData>
        </component>
    </settings>
    <settings pass="oobeSystem">
        <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
            <UserAccounts>
                <LocalAccounts>
                    <LocalAccount wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
                        <Name>{username}</Name>
                        <Group>Administrators</Group>
                    </LocalAccount>
                </LocalAccounts>
            </UserAccounts>
        </component>
    </settings>
</unattend>"""
        return xml_template

    def inspect_file(self, path: Union[str, Path], sample_bytes: int = 65536) -> str:
        """Inspects an ISO file from disk and records identified OS."""
        file_path = Path(path)
        if not file_path.exists() or not file_path.is_file():
            self.last_detected_os = OperatingSystemType.UNKNOWN
            return OperatingSystemType.UNKNOWN

        try:
            with open(file_path, "rb") as f:
                header = f.read(sample_bytes)
            detected = self.identify_operating_system(header)
            self.last_detected_os = OperatingSystemType(detected)
            return detected
        except Exception:
            self.last_detected_os = OperatingSystemType.UNKNOWN
            return OperatingSystemType.UNKNOWN

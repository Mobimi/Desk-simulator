"""
Desk-simulator Management Layer - Storage Bridge.
Cross-platform Python reference implementation.
Provides APFS Sparse Disk manager configuration and allocation,
as well as 2-way file sharing and clipboard bridge support.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import sys
import tempfile
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class DiskFormat(str, Enum):
    """Supported virtual disk image formats."""
    APFS_SPARSE = "APFS_SPARSE"
    RAW = "RAW"
    QCOW2 = "QCOW2"


class StorageBridge:
    """
    Storage Bridge service.
    Manages APFS sparse disk image provisioning and two-way host/guest file
    and clipboard synchronization.
    """

    DiskFormat = DiskFormat

    def __init__(self, staging_dir: Optional[Union[str, Path]] = None) -> None:
        if staging_dir:
            self.staging_dir = Path(staging_dir)
        else:
            self.staging_dir = Path(tempfile.gettempdir()) / "DeskSimulatorShares"
        self.staging_dir.mkdir(parents=True, exist_ok=True)

        self.clipboard_content: str = ""
        self.mounted_disks: Dict[str, int] = {}
        self.shared_files: List[str] = []

    @classmethod
    def get_supported_formats(cls) -> List[str]:
        """Returns the list of supported disk image formats."""
        return [
            cls.DiskFormat.APFS_SPARSE,
            cls.DiskFormat.RAW,
            cls.DiskFormat.QCOW2,
        ]

    @classmethod
    def create_sparse_disk_config(cls, virtual_size_bytes: int) -> Dict[str, Any]:
        """
        Generates APFS sparse disk configuration.
        Initial allocation is minimal (512 KB header) while virtual capacity matches
        requested size.
        Validates that virtual_size_bytes is strictly positive (> 0).
        """
        if virtual_size_bytes <= 0:
            raise ValueError(f"virtual_size_bytes must be strictly positive (> 0), got {virtual_size_bytes}")
        return {
            "format": cls.DiskFormat.APFS_SPARSE,
            "virtual_size_bytes": virtual_size_bytes,
            "initial_allocation_bytes": 512 * 1024,
            "sparse_flag": True,
        }

    @classmethod
    def allocate_sparse_disk(cls, target_path: Union[str, Path], size_bytes: int) -> bool:
        """
        Allocates a sparse file on disk of the specified size.
        Uses sparse seeking and write of 1 byte at the end to avoid preallocating
        physical disk blocks. On Windows NTFS, sets FSCTL_SET_SPARSE to ensure
        virtual disk sizes up to 1TB allocate without requiring physical blocks.
        Rejects non-positive sizes (<= 0) without creating dummy files.
        """
        if size_bytes <= 0:
            return False

        p = Path(target_path)
        p.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(p, "wb") as f:
                if sys.platform == "win32":
                    try:
                        import msvcrt

                        handle = msvcrt.get_osfhandle(f.fileno())
                        bytes_returned = ctypes.c_ulong(0)
                        FSCTL_SET_SPARSE = 0x000900C4
                        ctypes.windll.kernel32.DeviceIoControl(
                            handle,
                            FSCTL_SET_SPARSE,
                            None,
                            0,
                            None,
                            0,
                            ctypes.byref(bytes_returned),
                            None,
                        )
                    except Exception:
                        pass

                f.seek(size_bytes - 1)
                f.write(b"\0")
            return True
        except Exception:
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass
            return False

    def share_file_to_guest(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Copies host file to shared staging directory for guest consumption."""
        src = Path(file_path)
        if not src.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        dst = self.staging_dir / src.name
        shutil.copy2(src, dst)
        self.shared_files.append(str(dst))
        return {
            "status": "staged",
            "source": str(src),
            "destination": str(dst),
            "size_bytes": dst.stat().st_size,
        }

    def sharesheet_export(self, file_path: str) -> Dict[str, Any]:
        """Simulates exporting a file via iOS Share Sheet."""
        return {
            "action": "sharesheet_export",
            "file": file_path,
            "available_activities": ["AirDrop", "SaveToFiles", "Mail", "Copy"],
        }

    def files_import(self, file_path: str) -> Dict[str, Any]:
        """Simulates importing a file via iOS Files document picker."""
        return {
            "action": "files_import",
            "file": file_path,
            "imported": True,
        }

    def sync_to_guest(self, text: str) -> str:
        """Sets clipboard content from host to guest."""
        self.clipboard_content = text
        return self.clipboard_content

    def sync_from_guest(self) -> str:
        """Retrieves clipboard content from guest."""
        return self.clipboard_content

    def sync_clipboard(self, text: str) -> None:
        """Synchronizes clipboard text."""
        self.clipboard_content = text

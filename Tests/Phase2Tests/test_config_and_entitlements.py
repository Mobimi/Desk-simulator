#!/usr/bin/env python3
"""
Unit tests validating configuration plists, entitlements, and C bridging headers.
Ensures compliance with:
- Config/DeskSimulator-TrollStore.entitlements (unrestricted memory, dynamic-codesigning, extended-va)
- Config/DeskSimulator-Sideload.entitlements (sandbox safe, get-task-allow only)
- Config/Info.plist (ProMotion 120Hz, arm64+metal, file sharing, ISO document types)
- Engine/DeskSimulator-Bridging-Header.h & DarwinRuntimeBridge.h/.c
"""

import plistlib
import unittest
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent


class TestConfigAndEntitlements(unittest.TestCase):
    """Validates configuration files, entitlements plists, and bridging headers."""

    def test_trollstore_entitlements(self):
        plist_path = WORKSPACE_ROOT / "Config" / "DeskSimulator-TrollStore.entitlements"
        self.assertTrue(plist_path.exists(), "DeskSimulator-TrollStore.entitlements must exist")
        with open(plist_path, "rb") as f:
            data = plistlib.load(f)

        self.assertTrue(data.get("com.apple.developer.kernel.increased-memory-limit"),
                        "TrollStore must have increased-memory-limit enabled")
        self.assertTrue(data.get("com.apple.developer.kernel.extended-virtual-addressing"),
                        "TrollStore must have extended-virtual-addressing enabled")
        self.assertTrue(data.get("dynamic-codesigning"),
                        "TrollStore must have dynamic-codesigning enabled")
        self.assertTrue(data.get("get-task-allow"),
                        "TrollStore must have get-task-allow enabled")

    def test_sideload_entitlements(self):
        plist_path = WORKSPACE_ROOT / "Config" / "DeskSimulator-Sideload.entitlements"
        self.assertTrue(plist_path.exists(), "DeskSimulator-Sideload.entitlements must exist")
        with open(plist_path, "rb") as f:
            data = plistlib.load(f)

        self.assertTrue(data.get("get-task-allow"),
                        "Sideload build must have get-task-allow enabled for debugging/JIT")
        # Critical: increased-memory-limit and extended-virtual-addressing MUST be omitted
        self.assertNotIn("com.apple.developer.kernel.increased-memory-limit", data,
                         "Sideload build must NOT include increased-memory-limit (causes signing rejection)")
        self.assertNotIn("com.apple.developer.kernel.extended-virtual-addressing", data,
                         "Sideload build must NOT include extended-virtual-addressing")

    def test_info_plist_configuration(self):
        plist_path = WORKSPACE_ROOT / "Config" / "Info.plist"
        self.assertTrue(plist_path.exists(), "Info.plist must exist")
        with open(plist_path, "rb") as f:
            data = plistlib.load(f)

        # ProMotion 120Hz support
        self.assertTrue(data.get("CADisableMinimumFrameDurationOnPhone"),
                        "Info.plist must set CADisableMinimumFrameDurationOnPhone to true for ProMotion 120Hz")

        # Required device capabilities
        caps = data.get("UIRequiredDeviceCapabilities", [])
        self.assertIn("arm64", caps)
        self.assertIn("metal", caps)

        # File sharing enabled
        self.assertTrue(data.get("UIFileSharingEnabled"),
                        "Info.plist must enable UIFileSharingEnabled for document management")
        self.assertTrue(data.get("LSSupportsOpeningDocumentsInPlace"),
                        "Info.plist must enable LSSupportsOpeningDocumentsInPlace")

        # Document types for ISO / image loading
        doc_types = data.get("CFBundleDocumentTypes", [])
        self.assertTrue(len(doc_types) > 0, "Info.plist must declare document types for disk images")

    def test_c_bridging_header(self):
        header_path = WORKSPACE_ROOT / "Engine" / "DeskSimulator-Bridging-Header.h"
        self.assertTrue(header_path.exists(), "DeskSimulator-Bridging-Header.h must exist")
        content = header_path.read_text(encoding="utf-8")
        self.assertIn("BootstrapBridge.h", content)
        self.assertIn("DarwinRuntimeBridge.h", content)

    def test_darwin_runtime_bridge_declarations(self):
        header_path = WORKSPACE_ROOT / "Engine" / "QEMU" / "DarwinRuntimeBridge.h"
        impl_path = WORKSPACE_ROOT / "Engine" / "QEMU" / "DarwinRuntimeBridge.c"
        self.assertTrue(header_path.exists())
        self.assertTrue(impl_path.exists())

        header_content = header_path.read_text(encoding="utf-8")
        impl_content = impl_path.read_text(encoding="utf-8")

        required_symbols = [
            "desk_is_jit_enabled",
            "desk_available_memory_bytes",
            "desk_process_footprint_bytes",
            "desk_physical_memory_bytes",
            "desk_probe_increased_memory_entitlement",
            "desk_probe_extended_va_entitlement",
        ]
        for sym in required_symbols:
            self.assertIn(sym, header_content, f"DarwinRuntimeBridge.h missing symbol {sym}")
            self.assertIn(sym, impl_content, f"DarwinRuntimeBridge.c missing implementation {sym}")

        # Check non-Apple fallback stubs exist in .c
        self.assertIn("#else", impl_content)
        self.assertIn("2ULL * 1024ULL * 1024ULL * 1024ULL", impl_content)


if __name__ == "__main__":
    unittest.main()

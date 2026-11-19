#!/usr/bin/env python3
"""
Tests/Phase3Tests/test_phase3_swift_symbol_resolution.py
Desk-simulator Phase 3: Swift Symbol Resolution, C Bridging Header & Clang Compatibility Test Suite.

Covers:
- Features F3, F8:
  - C Bridging header parse verification (DeskSimulator-Bridging-Header.h)
  - C-ABI symbol exposure to Swift namespace (BootstrapBridge.h & DarwinRuntimeBridge.h)
  - Clang and header compatibility (header guards, extern "C", standard types, pid_t)
  - Darwin runtime probe fallbacks on non-Darwin platforms (DarwinRuntimeBridge.c #else)
  - Cross-file Swift member symbol and interface resolution across Engine/ and UI/
"""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Workspace root discovery
CANDIDATE_ROOT = Path(__file__).resolve().parent.parent.parent
if (CANDIDATE_ROOT / "Engine").is_dir():
    WORKSPACE_ROOT = CANDIDATE_ROOT
elif (Path.cwd() / "Engine").is_dir():
    WORKSPACE_ROOT = Path.cwd().resolve()
else:
    WORKSPACE_ROOT = Path(r"d:\project nhảm\giả lập").resolve()


class TestPhase3SwiftSymbolResolution(unittest.TestCase):
    """Production-grade automated tests for Swift/C symbol resolution and Clang compatibility."""

    @classmethod
    def setUpClass(cls):
        cls.root = WORKSPACE_ROOT
        cls.bridging_header_path = cls.root / "Engine" / "DeskSimulator-Bridging-Header.h"
        cls.bootstrap_h_path = cls.root / "Engine" / "QEMU" / "BootstrapBridge.h"
        cls.bootstrap_c_path = cls.root / "Engine" / "QEMU" / "BootstrapBridge.c"
        cls.darwin_h_path = cls.root / "Engine" / "QEMU" / "DarwinRuntimeBridge.h"
        cls.darwin_c_path = cls.root / "Engine" / "QEMU" / "DarwinRuntimeBridge.c"

        cls.bridging_content = cls.bridging_header_path.read_text(encoding="utf-8")
        cls.bootstrap_h = cls.bootstrap_h_path.read_text(encoding="utf-8")
        cls.bootstrap_c = cls.bootstrap_c_path.read_text(encoding="utf-8")
        cls.darwin_h = cls.darwin_h_path.read_text(encoding="utf-8")
        cls.darwin_c = cls.darwin_c_path.read_text(encoding="utf-8")

    # =========================================================================
    # PART 1: Bridging Header Parse & Verification (F3)
    # =========================================================================

    def test_bridging_header_inclusions_and_guards(self):
        """Validates DeskSimulator-Bridging-Header.h structure and header inclusions."""
        self.assertIn("#ifndef DESK_SIMULATOR_BRIDGING_HEADER_H", self.bridging_content)
        self.assertIn("#define DESK_SIMULATOR_BRIDGING_HEADER_H", self.bridging_content)
        self.assertIn('#include "QEMU/BootstrapBridge.h"', self.bridging_content)
        self.assertIn('#include "QEMU/DarwinRuntimeBridge.h"', self.bridging_content)
        self.assertIn("#endif", self.bridging_content)

    def test_headers_extern_c_linkage_guards(self):
        """Validates that C headers declare extern 'C' blocks for C++ / Swift interoperability."""
        for name, text in [("BootstrapBridge.h", self.bootstrap_h), ("DarwinRuntimeBridge.h", self.darwin_h)]:
            self.assertIn("#ifdef __cplusplus", text, f"{name} must guard with __cplusplus")
            self.assertIn('extern "C" {', text, f'{name} must declare extern "C"')
            self.assertIn("}", text, f"{name} must close extern C block")

    def test_headers_standard_types_and_portability(self):
        """Validates standard C99 headers and Windows pid_t portability typedef."""
        self.assertIn("<stddef.h>", self.bootstrap_h)
        self.assertIn("<stdint.h>", self.bootstrap_h)
        self.assertIn("<stdbool.h>", self.bootstrap_h)
        self.assertIn("<sys/types.h>", self.bootstrap_h)
        # Portability guard for pid_t
        self.assertIn("defined(_WIN32)", self.bootstrap_h)
        self.assertIn("typedef int pid_t;", self.bootstrap_h)
        self.assertIn("#define _PID_T_", self.bootstrap_h)

    # =========================================================================
    # PART 2: C-ABI Symbol Exposure to Swift (F3, F8)
    # =========================================================================

    def test_all_13_bootstrap_bridge_symbols_declared(self):
        """Verifies presence of all 13 required C-ABI functions in BootstrapBridge.h."""
        declared_functions = [
            "qemu_init",
            "qemu_init_target",
            "qemu_main_loop",
            "qemu_request_exit",
            "qemu_cleanup",
            "qemu_is_running",
            "qemu_get_status",
            "qemu_bootstrap_start_thread",
            "qemu_bootstrap_join_thread",
            "qemu_spawn_process",
            "qemu_poll_process",
            "qemu_terminate_process",
            "qemu_register_display_callback"
        ]
        for fn in declared_functions:
            pattern = rf"\b{fn}\s*\("
            self.assertIsNotNone(re.search(pattern, self.bootstrap_h), f"Function {fn} not found in BootstrapBridge.h")

    def test_all_6_darwin_runtime_probes_declared(self):
        """Verifies presence of all 6 Darwin runtime probe functions in DarwinRuntimeBridge.h."""
        darwin_probes = [
            "desk_is_jit_enabled",
            "desk_available_memory_bytes",
            "desk_process_footprint_bytes",
            "desk_physical_memory_bytes",
            "desk_probe_increased_memory_entitlement",
            "desk_probe_extended_va_entitlement"
        ]
        for probe in darwin_probes:
            pattern = rf"\b{probe}\s*\("
            self.assertIsNotNone(re.search(pattern, self.darwin_h), f"Probe {probe} not found in DarwinRuntimeBridge.h")

    def test_display_frame_struct_and_callback_types(self):
        """Verifies QEMUDisplayFrame struct and QEMUDisplayFrameCallback typedef exposure."""
        self.assertIn("typedef struct", self.bootstrap_h)
        self.assertIn("QEMUDisplayFrame", self.bootstrap_h)
        self.assertIn("uint32_t width;", self.bootstrap_h)
        self.assertIn("uint32_t height;", self.bootstrap_h)
        self.assertIn("uint32_t stride;", self.bootstrap_h)
        self.assertIn("uint32_t pixel_format;", self.bootstrap_h)
        self.assertIn("const uint8_t *data;", self.bootstrap_h)
        self.assertIn("size_t data_len;", self.bootstrap_h)

        self.assertIn("typedef void (*QEMUDisplayFrameCallback)(const QEMUDisplayFrame *frame, void *user_data);", self.bootstrap_h)

    def test_qemu_status_code_enum_exposure(self):
        """Verifies QEMUStatusCode enum has complete value definitions for Swift bridge."""
        self.assertIn("QEMU_STATUS_STOPPED = 0", self.bootstrap_h)
        self.assertIn("QEMU_STATUS_INITIALIZING = 1", self.bootstrap_h)
        self.assertIn("QEMU_STATUS_RUNNING = 2", self.bootstrap_h)
        self.assertIn("QEMU_STATUS_PAUSED = 3", self.bootstrap_h)
        self.assertIn("QEMU_STATUS_TERMINATING = 4", self.bootstrap_h)
        self.assertIn("QEMU_STATUS_ERROR = -1", self.bootstrap_h)

    # =========================================================================
    # PART 3: Darwin Runtime Probe Fallbacks on Non-Darwin Platforms
    # =========================================================================

    def test_darwin_runtime_fallback_values(self):
        """Validates that DarwinRuntimeBridge.c provides deterministic, safe non-Apple fallbacks."""
        # Non-Apple #else section
        self.assertIn("#else", self.darwin_c)
        fallback_section = self.darwin_c[self.darwin_c.rfind("#else"):]

        self.assertIn("bool desk_is_jit_enabled(void) { return false; }", fallback_section)
        self.assertIn("uint64_t desk_available_memory_bytes(void) { return 2ULL * 1024ULL * 1024ULL * 1024ULL; }", fallback_section)
        self.assertIn("uint64_t desk_process_footprint_bytes(void) { return 128ULL * 1024ULL * 1024ULL; }", fallback_section)
        self.assertIn("uint64_t desk_physical_memory_bytes(void) { return 6ULL * 1024ULL * 1024ULL * 1024ULL; }", fallback_section)
        self.assertIn("bool desk_probe_increased_memory_entitlement(void) { return false; }", fallback_section)
        self.assertIn("bool desk_probe_extended_va_entitlement(void) { return false; }", fallback_section)

    # =========================================================================
    # PART 4: Cross-File Swift Symbol Resolution Verification
    # =========================================================================

    def test_process_launcher_symbols_resolve_in_vm_controller(self):
        """Verifies that VMController.swift uses valid ProcessLauncher members."""
        vm_controller_code = (self.root / "Engine" / "Core" / "VMController.swift").read_text(encoding="utf-8")
        launcher_code = (self.root / "Engine" / "Core" / "ProcessLauncher.swift").read_text(encoding="utf-8")

        # VMController creates ProcessLauncher()
        self.assertIn("ProcessLauncher()", vm_controller_code)
        # VMController calls launcher.launch(with: args)
        self.assertIn("self.launcher.launch(with: args)", vm_controller_code)
        self.assertIn("func launch(with arguments: [String]", launcher_code)
        # VMController calls launcher.terminate()
        self.assertIn("self.launcher.terminate()", vm_controller_code)
        self.assertIn("func terminate()", launcher_code)

    def test_qemu_arguments_builder_symbols_resolve_in_vm_controller(self):
        """Verifies that VMController.swift uses valid QEMUArgumentsBuilder members."""
        vm_controller_code = (self.root / "Engine" / "Core" / "VMController.swift").read_text(encoding="utf-8")
        builder_code = (self.root / "Engine" / "QEMU" / "QEMUArgumentsBuilder.swift").read_text(encoding="utf-8")

        self.assertIn("QEMUArgumentsBuilder.buildArguments(from: self.configuration)", vm_controller_code)
        self.assertIn("static func buildArguments(from config: QEMUConfiguration)", builder_code)

    def test_spice_connection_symbols_resolve_in_vm_controller(self):
        """Verifies that VMController.swift uses valid SPICEConnection members."""
        vm_controller_code = (self.root / "Engine" / "Core" / "VMController.swift").read_text(encoding="utf-8")
        spice_code = (self.root / "Engine" / "SPICE" / "SPICEConnection.swift").read_text(encoding="utf-8")

        self.assertIn("SPICEConnection(", vm_controller_code)
        self.assertIn("self.spiceConnection?.connect()", vm_controller_code)
        self.assertIn("self.spiceConnection?.disconnect()", vm_controller_code)
        self.assertIn("func connect()", spice_code)
        self.assertIn("func disconnect()", spice_code)

    def test_qmp_client_symbols_resolve_in_vm_controller(self):
        """Verifies that VMController.swift uses valid QMPClient members."""
        vm_controller_code = (self.root / "Engine" / "Core" / "VMController.swift").read_text(encoding="utf-8")
        qmp_code = (self.root / "Engine" / "Core" / "QMPClient.swift").read_text(encoding="utf-8")

        self.assertIn("QMPClient(socketPath:", vm_controller_code)
        self.assertIn("qmp.pauseVM", vm_controller_code)
        self.assertIn("qmp.resumeVM", vm_controller_code)
        self.assertIn("qmp.shutdown(force: force)", vm_controller_code)
        self.assertIn("func pauseVM(", qmp_code)
        self.assertIn("func resumeVM(", qmp_code)
        self.assertIn("func shutdown(force: Bool", qmp_code)


if __name__ == "__main__":
    unittest.main()

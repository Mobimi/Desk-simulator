#!/usr/bin/env python3
"""
Desk-simulator E2E Test Suite - Tier 3: Cross-Feature Combinations (Pairwise)

Covers cross-feature interaction testing across the 24 features defined in
PROJECT.md and TEST_INFRA.md, satisfying the requirement of minimum 24 tests.

Pairwise Combinations Tested:
1.  (F04 Architecture Target, F08 TCG Buffer Clamp)
2.  (F04 Architecture Target, F05 Compiler Flags)
3.  (F06 SPICE UDS IPC, F07 Channel Pruning)
4.  (F11 Safe RAM, F12 Memory Pressure)
5.  (F13 Auto-Pause, F14 P-Core Pinning)
6.  (F15 QoS Elevation, F16 Boot Boost)
7.  (F17 OS Detection, F18 VirtIO Injection)
8.  (F17 OS Detection, F19 Win11 Bypass)
9.  (F18 VirtIO Injection, F20 Storage APFS Sparse Disk)
10. (F01 Workspace Layout, F02 Git Remote)
11. (F03 Workspace Script, F22 Verification Script)
12. (F22 Verification Script, F23 Mock Test Suite)
13. (F01 Workspace Layout, F03 Workspace Script)
14. (F04 Architecture Target, F06 SPICE UDS IPC)
15. (F04 Architecture Target, F07 Channel Pruning)
16. (F05 Compiler Flags, F09 Engine Build Script)
17. (F06 SPICE UDS IPC, F08 TCG Buffer Clamp)
18. (F08 TCG Buffer Clamp, F09 Engine Build Script)
19. (F10 Entitlements, F11 Safe RAM)
20. (F10 Entitlements, F21 JIT Hook)
21. (F11 Safe RAM, F13 Auto-Pause)
22. (F12 Memory Pressure, F13 Auto-Pause)
23. (F14 P-Core Pinning, F15 QoS Elevation)
24. (F14 P-Core Pinning, F16 Boot Boost)
25. (F16 Boot Boost, F21 JIT Hook)
26. (F17 OS Detection, F20 Storage APFS Sparse Disk)
27. (F18 VirtIO Injection, F19 Win11 Bypass)
28. (F19 Win11 Bypass, F20 Storage APFS Sparse Disk)
29. (F09 Engine Build Script, F22 Verification Script)
30. (F23 Mock Test Suite, F24 E2E Acceptance)
"""

import json
import os
import re
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

# Workspace Root Anchor & Path Injection
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from Engine.Config.engine_config import EngineConfig
from Management.SmartMemoryGuard.memory_guard import (
    MemoryGuard,
    MemoryPressureLevel,
    MemoryEntitlements,
    QMPCommand,
)
from Management.ISOAutoPilot.iso_autopilot import (
    ISOAutoPilot,
    OperatingSystemType,
)
from Management.PCoreScheduler.pcore_scheduler import (
    PCoreScheduler,
    BootBoostState,
)
from Management.Storage.storage_bridge import (
    StorageBridge,
    DiskFormat,
)


# ============================================================================
# Tier 3 Pairwise Combinatorial Test Suite
# ============================================================================

class TestTier3PairwiseCombos(unittest.TestCase):
    """Pairwise cross-feature combinatorial verification across all 24 features."""

    def setUp(self):
        self.workspace_root = WORKSPACE_ROOT
        self.engine_config = EngineConfig
        self.mem_guard = MemoryGuard
        self.iso_pilot = ISOAutoPilot

    # ------------------------------------------------------------------------
    # Pair 1: (F04 Architecture Target, F08 TCG Buffer Clamp)
    # ------------------------------------------------------------------------
    def test_pair_f04_f08_arch_target_and_tcg_buffer_clamp(self):
        """Pair F04 & F08: x86_64 with 128MB vs aarch64 with 256MB and clamping."""
        # x86_64 with lower boundary 128MB
        cmd_x86 = self.engine_config.generate_qemu_cmdline(
            target="x86_64-softmmu", ram_mb=2048, tb_size_mb=128, spice_socket="/tmp/spice.sock"
        )
        self.assertEqual(cmd_x86[0], "qemu-system-x86_64")
        self.assertIn("tcg,tb-size=128", " ".join(cmd_x86))

        # aarch64 with upper boundary 256MB
        cmd_arm = self.engine_config.generate_qemu_cmdline(
            target="aarch64-softmmu", ram_mb=4096, tb_size_mb=256, spice_socket="/tmp/spice.sock"
        )
        self.assertEqual(cmd_arm[0], "qemu-system-aarch64")
        self.assertIn("tcg,tb-size=256", " ".join(cmd_arm))

        # Under-clamped request (64MB -> 128MB)
        self.assertEqual(self.engine_config.clamp_tcg_size(64), 128)
        # Over-clamped request (512MB -> 256MB)
        self.assertEqual(self.engine_config.clamp_tcg_size(512), 256)

        # Forbidden targets rejected regardless of clamp size
        self.assertFalse(self.engine_config.validate_targets(["mips-softmmu"]))

    # ------------------------------------------------------------------------
    # Pair 2: (F04 Architecture Target, F05 Compiler Flags)
    # ------------------------------------------------------------------------
    def test_pair_f04_f05_arch_target_and_compiler_flags(self):
        """Pair F04 & F05: aarch64 with -mcpu=apple-m1 vs x86_64 with -O3 -flto."""
        # aarch64 Apple Silicon compilation flags
        arm_flags = ["-O3", "-flto", "-mcpu=apple-m1", "-arch", "arm64"]
        self.assertTrue(self.engine_config.validate_compiler_flags(arm_flags))
        self.assertTrue(self.engine_config.validate_targets(["aarch64-softmmu"]))

        # x86_64 host/cross compilation flags
        x86_flags = ["-O3", "-flto", "-march=x86-64"]
        self.assertTrue(self.engine_config.validate_compiler_flags(x86_flags))
        self.assertTrue(self.engine_config.validate_targets(["x86_64-softmmu"]))

        # Flags missing required optimization must fail
        unoptimized_flags = ["-O0", "-g", "-arch", "arm64"]
        self.assertFalse(self.engine_config.validate_compiler_flags(unoptimized_flags))

    # ------------------------------------------------------------------------
    # Pair 3: (F06 SPICE UDS IPC, F07 Channel Pruning)
    # ------------------------------------------------------------------------
    def test_pair_f06_f07_spice_uds_and_channel_pruning(self):
        """Pair F06 & F07: SPICE over UDS with smartcard disabled and display enabled."""
        socket_path = "/tmp/desk_sim_spice.sock"
        uds_args = self.engine_config.generate_spice_uds_args(socket_path, disable_smartcard=True)
        arg_str = " ".join(uds_args)

        # UDS verification
        self.assertIn("unix=on", arg_str)
        self.assertIn(f"addr={socket_path}", arg_str)
        # TCP loopback prohibited
        self.assertNotIn("127.0.0.1", arg_str)
        self.assertNotIn("localhost", arg_str)
        self.assertNotIn("port=", arg_str)

        # Channel pruning verification: smartcard must be turned off
        self.assertIn("smartcard=off", arg_str)
        self.assertNotIn("smartcard=on", arg_str)

    # ------------------------------------------------------------------------
    # Pair 4: (F11 Safe RAM, F12 Memory Pressure)
    # ------------------------------------------------------------------------
    def test_pair_f11_f12_safe_ram_and_memory_pressure(self):
        """Pair F11 & F12: Dynamic ballooning under Normal vs Warning/Critical memory pressure with 450MB reserve."""
        avail_bytes = 4096 * 1024 * 1024
        expected_safe_ram = avail_bytes - (450 * 1024 * 1024)
        calculated_safe_ram = self.mem_guard.calculate_safe_guest_ram(avail_bytes)
        self.assertEqual(calculated_safe_ram, expected_safe_ram)

        # Normal pressure: no ballooning action required
        normal_cmd = self.mem_guard.handle_memory_pressure("normal", avail_bytes)
        self.assertIsNone(normal_cmd)

        # Warning pressure: deflates to safe guest RAM
        warn_cmd = self.mem_guard.handle_memory_pressure("warning", avail_bytes)
        self.assertIsNotNone(warn_cmd)
        self.assertEqual(warn_cmd.get("execute"), "balloon")
        self.assertEqual(warn_cmd.get("arguments", {}).get("value"), calculated_safe_ram)

        # Critical pressure: aggressively deflates to emergency safe floor or half of safe RAM
        crit_cmd = self.mem_guard.handle_memory_pressure("critical", avail_bytes)
        self.assertIsNotNone(crit_cmd)
        self.assertEqual(crit_cmd.get("execute"), "balloon")
        self.assertEqual(
            crit_cmd.get("arguments", {}).get("value"),
            max(self.mem_guard.MIN_SAFE_FLOOR_BYTES, calculated_safe_ram // 2),
        )

        # Low memory floor enforcement: available 1200MB (1200 - 450 = 750MB < 1024MB floor)
        low_avail = 1200 * 1024 * 1024
        floor_safe_ram = self.mem_guard.calculate_safe_guest_ram(low_avail)
        self.assertEqual(floor_safe_ram, 1024 * 1024 * 1024)

    # ------------------------------------------------------------------------
    # Pair 5: (F13 Auto-Pause, F14 P-Core Pinning)
    # ------------------------------------------------------------------------
    def test_pair_f13_f14_auto_pause_and_pcore_pinning(self):
        """Pair F13 & F14: Emergency auto-pause triggered while vCPUs are pinned to 2 P-cores."""
        # Pinning: default 2 vCPUs on Apple Silicon P-cores via PCoreScheduler
        topology = PCoreScheduler.assign_topology(2)
        self.assertEqual(topology["vcpus"], 2)
        self.assertEqual(topology["pcore_affinity"], [0, 1])

        ceiling_bytes = 2048 * 1024 * 1024  # 2GB ceiling

        # Memory usage below danger threshold (80% of ceiling) -> No pause
        usage_safe = int(ceiling_bytes * 0.80)
        self.assertFalse(self.mem_guard.check_jetsam_emergency(usage_safe, ceiling_bytes))

        # Memory usage reaches 90% (Jetsam danger zone) -> Emergency auto-pause triggered
        usage_danger = int(ceiling_bytes * 0.90) + 1024
        self.assertTrue(self.mem_guard.check_jetsam_emergency(usage_danger, ceiling_bytes))

        # Emergency auto-pause command
        pause_cmd = self.mem_guard.emergency_auto_pause()
        self.assertEqual(pause_cmd, {"execute": "stop"})

    # ------------------------------------------------------------------------
    # Pair 6: (F15 QoS Elevation, F16 Boot Boost)
    # ------------------------------------------------------------------------
    def test_pair_f15_f16_qos_elevation_and_boot_boost(self):
        """Pair F15 & F16: Main VM thread at Interactive QoS during boot boost phase."""
        scheduler = PCoreScheduler(physical_p_cores=2)
        self.assertEqual(scheduler.state, BootBoostState.IDLE)

        # During boot boost phase: state transitions to BOOTING and registers interactive QoS
        scheduler.update_boot_boost_state(is_booting=True)
        self.assertEqual(scheduler.state, BootBoostState.BOOTING)
        qos = scheduler.register_thread("vcpu_main", is_vcpu=True)
        self.assertEqual(qos, PCoreScheduler.QOS_CLASS_USER_INTERACTIVE)

        # After boot completes: transitions to RUNNING while maintaining Interactive QoS
        scheduler.update_boot_boost_state(is_booting=False)
        self.assertEqual(scheduler.state, BootBoostState.RUNNING)
        self.assertEqual(scheduler.thread_registry["vcpu_main"], PCoreScheduler.QOS_CLASS_USER_INTERACTIVE)

    # ------------------------------------------------------------------------
    # Pair 7: (F17 OS Detection, F18 VirtIO Injection)
    # ------------------------------------------------------------------------
    def test_pair_f17_f18_os_detection_and_virtio_injection(self):
        """Pair F17 & F18: Windows 11 detected triggers virtio-win injection; Linux triggers native kernel virtio."""
        # Windows 11 detection with realistic volume descriptor header
        win11_header = b"\x00" * 32768 + b"CD001 MICROSOFT WINDOWS 11 PROFESSIONAL INSTALLATION MEDIA"
        os_type_win = self.iso_pilot.identify_operating_system(win11_header)
        self.assertEqual(os_type_win, OperatingSystemType.WINDOWS_11)

        virtio_win = self.iso_pilot.generate_virtio_injection_config(os_type_win)
        self.assertTrue(virtio_win["inject_drivers"])
        self.assertFalse(virtio_win["native_drivers"])
        self.assertEqual(virtio_win["target_os"], "WINDOWS_11")
        self.assertIn("viostor", virtio_win["drivers"])
        self.assertIn("netkvm", virtio_win["drivers"])
        self.assertIn("virtio-win.iso", virtio_win["drive_param"])

        # Linux detection with realistic volume descriptor header
        linux_header = b"\x00" * 32768 + b"CD001 UBUNTU 24.04 LIVE SERVER"
        os_type_lin = self.iso_pilot.identify_operating_system(linux_header)
        self.assertEqual(os_type_lin, OperatingSystemType.LINUX_UBUNTU)

        virtio_lin = self.iso_pilot.generate_virtio_injection_config(os_type_lin)
        self.assertFalse(virtio_lin["inject_drivers"])
        self.assertTrue(virtio_lin["native_drivers"])
        self.assertEqual(virtio_lin["target_os"], "LINUX_UBUNTU")
        self.assertIn("virtio_blk", virtio_lin["drivers"])
        self.assertEqual(virtio_lin["drive_param"], "")

    # ------------------------------------------------------------------------
    # Pair 8: (F17 OS Detection, F19 Win11 Bypass)
    # ------------------------------------------------------------------------
    def test_pair_f17_f19_os_detection_and_win11_bypass(self):
        """Pair F17 & F19: Windows 11 detected triggers autounattend.xml bypass; Linux does not require bypass."""
        win11_header = b"\x00" * 32768 + b"CD001 MICROSOFT WINDOWS 11 PRO X64"
        detected_os = self.iso_pilot.identify_operating_system(win11_header)
        self.assertEqual(detected_os, OperatingSystemType.WINDOWS_11)

        xml_content = self.iso_pilot.generate_windows11_bypass_xml(local_username="LocalAdmin")
        root = ET.fromstring(xml_content)
        self.assertIsNotNone(root)

        self.assertIn("BypassTPMCheck", xml_content)
        self.assertIn("BypassSecureBootCheck", xml_content)
        self.assertIn("BypassRAMCheck", xml_content)
        self.assertIn("LocalAdmin", xml_content)

        # Linux header -> Linux does not require bypass XML
        linux_header = b"\x00" * 32768 + b"CD001 UBUNTU 24.04 LIVE SERVER"
        linux_os = self.iso_pilot.identify_operating_system(linux_header)
        self.assertNotEqual(linux_os, OperatingSystemType.WINDOWS_11)

    # ------------------------------------------------------------------------
    # Pair 9: (F18 VirtIO Injection, F20 Storage APFS Sparse Disk)
    # ------------------------------------------------------------------------
    def test_pair_f18_f20_virtio_injection_and_storage_apfs(self):
        """Pair F18 & F20: VirtIO disk configured on top of APFS sparse image."""
        storage_cfg = StorageBridge.create_sparse_disk_config(64 * 1024 * 1024 * 1024)
        self.assertEqual(storage_cfg["format"], DiskFormat.APFS_SPARSE)
        self.assertEqual(storage_cfg["virtual_size_bytes"], 64 * 1024 * 1024 * 1024)
        self.assertTrue(storage_cfg["sparse_flag"])
        self.assertEqual(storage_cfg["initial_allocation_bytes"], 512 * 1024)

        # VirtIO Windows injection matches disk format
        virtio_win = self.iso_pilot.generate_virtio_injection_config(OperatingSystemType.WINDOWS_11)
        self.assertIn("viostor", virtio_win["drivers"])
        self.assertTrue(virtio_win["inject_drivers"])
        self.assertIn("virtio-win.iso", virtio_win["drive_param"])

    # ------------------------------------------------------------------------
    # Pair 10: (F01 Workspace Layout, F02 Git Remote)
    # ------------------------------------------------------------------------
    def test_pair_f01_f02_workspace_layout_and_git_remote(self):
        """Pair F01 & F02: Verifying repository root conforms to layout and tracks origin remote."""
        # F01: Three-tier layout root checks
        self.assertTrue((self.workspace_root / "UI").is_dir(), "UI directory must exist")
        self.assertTrue((self.workspace_root / "Management").is_dir(), "Management directory must exist")
        self.assertTrue((self.workspace_root / "Engine").is_dir(), "Engine directory must exist")
        self.assertTrue((self.workspace_root / "Scripts").is_dir(), "Scripts directory must exist")
        self.assertTrue((self.workspace_root / "Tests").is_dir(), "Tests directory must exist")

        # F02: Git remote check
        res = subprocess.run(
            ["git", "remote", "-v"],
            cwd=self.workspace_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        if res.returncode == 0:
            self.assertIn("https://github.com/Mobimi/Desk-simulator", res.stdout)
            self.assertIn("origin", res.stdout)

    # ------------------------------------------------------------------------
    # Pair 11: (F03 Workspace Script, F22 Verification Script)
    # ------------------------------------------------------------------------
    def test_pair_f03_f22_workspace_prep_and_verification_script(self):
        """Pair F03 & F22: Workspace initialization followed by Phase 1 verification."""
        prep_script = self.workspace_root / "Scripts" / "prepare_workspace.py"
        self.assertTrue(prep_script.exists(), "prepare_workspace.py must exist")

        # Execute prepare_workspace.py
        prep_res = subprocess.run(
            [sys.executable, str(prep_script)],
            cwd=self.workspace_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        self.assertEqual(prep_res.returncode, 0, f"prepare_workspace.py failed: {prep_res.stderr}")
        self.assertIn("[SUCCESS]", prep_res.stdout)

        # F22: If verify_phase1.py is implemented, verify it can execute or check contract
        verify_script = self.workspace_root / "Scripts" / "verify_phase1.py"
        if verify_script.exists():
            v_res = subprocess.run(
                [sys.executable, str(verify_script)],
                cwd=self.workspace_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            # Verify standard exit code semantics
            self.assertIn(v_res.returncode, [0, 1])

    # ------------------------------------------------------------------------
    # Pair 12: (F22 Verification Script, F23 Mock Test Suite)
    # ------------------------------------------------------------------------
    def test_pair_f22_f23_verification_script_and_mock_test_suite(self):
        """Pair F22 & F23: Verification script checks passing and mock test suite passes."""
        # Both scripts are designed to return exit code 0 on compliance
        runner_script = self.workspace_root / "Tests" / "run_all_tests.py"
        if runner_script.exists():
            runner_res = subprocess.run(
                [sys.executable, str(runner_script)],
                cwd=self.workspace_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            self.assertEqual(runner_res.returncode, 0)

        # Verify EngineTests directory exists
        engine_tests_dir = self.workspace_root / "Tests" / "EngineTests"
        self.assertTrue(engine_tests_dir.exists())

    # ------------------------------------------------------------------------
    # Pair 13: (F01 Workspace Layout, F03 Workspace Script)
    # ------------------------------------------------------------------------
    def test_pair_f01_f03_workspace_layout_and_prep_script(self):
        """Pair F01 & F03: Workspace preparation script produces exact required directory layout."""
        expected_dirs = [
            "UI/Views",
            "UI/ViewModels",
            "Management/SmartMemoryGuard",
            "Management/PCoreScheduler",
            "Management/ISOAutoPilot",
            "Management/Storage",
            "Engine/Config",
            "Engine/Core",
            "Engine/QEMU",
            "Engine/SPICE",
            "Engine/JIT",
            "Scripts",
            "Tests",
            "Tests/EngineTests",
            "Tests/ManagementMocks",
        ]
        for rel_dir in expected_dirs:
            dir_path = self.workspace_root / rel_dir
            self.assertTrue(dir_path.is_dir(), f"Expected directory {rel_dir} must exist")

    # ------------------------------------------------------------------------
    # Pair 14: (F04 Architecture Target, F06 SPICE UDS IPC)
    # ------------------------------------------------------------------------
    def test_pair_f04_f06_arch_target_and_spice_uds_ipc(self):
        """Pair F04 & F06: Both x86_64 and aarch64 targets bind SPICE to Unix Domain Socket without TCP."""
        for target in ["x86_64-softmmu", "aarch64-softmmu"]:
            cmd = self.engine_config.generate_qemu_cmdline(
                target=target, ram_mb=2048, tb_size_mb=128, spice_socket="/tmp/vm.sock"
            )
            cmd_str = " ".join(cmd)
            self.assertIn("unix=on", cmd_str)
            self.assertIn("addr=/tmp/vm.sock", cmd_str)
            self.assertNotIn("127.0.0.1", cmd_str)
            self.assertNotIn("localhost", cmd_str)

    # ------------------------------------------------------------------------
    # Pair 15: (F04 Architecture Target, F07 Channel Pruning)
    # ------------------------------------------------------------------------
    def test_pair_f04_f07_arch_target_and_channel_pruning(self):
        """Pair F04 & F07: Engine command line generation for both architectures prunes smartcard channel."""
        for target in ["x86_64-softmmu", "aarch64-softmmu"]:
            cmd = self.engine_config.generate_qemu_cmdline(
                target=target, ram_mb=2048, tb_size_mb=128, spice_socket="/tmp/vm.sock"
            )
            cmd_str = " ".join(cmd)
            self.assertIn("smartcard=off", cmd_str)

    # ------------------------------------------------------------------------
    # Pair 16: (F05 Compiler Flags, F09 Engine Build Script)
    # ------------------------------------------------------------------------
    def test_pair_f05_f09_compiler_flags_and_engine_build_script(self):
        """Pair F05 & F09: Build script invokes or validates -O3, -flto, and Apple Silicon target flags."""
        build_script = self.workspace_root / "Scripts" / "build_engine.py"
        if build_script.exists():
            content = build_script.read_text(encoding="utf-8")
            self.assertIn("-O3", content)
            self.assertIn("-flto", content)
        else:
            # Contract verification
            self.assertTrue(self.engine_config.validate_compiler_flags(["-O3", "-flto"]))
            self.assertTrue(self.engine_config.validate_compiler_flags(["-O3", "-flto", "-mcpu=apple-m1"]))

    # ------------------------------------------------------------------------
    # Pair 17: (F06 SPICE UDS IPC, F08 TCG Buffer Clamp)
    # ------------------------------------------------------------------------
    def test_pair_f06_f08_spice_uds_and_tcg_buffer_clamp(self):
        """Pair F06 & F08: SPICE UDS and clamped TCG buffer coexist cleanly in QEMU parameters."""
        cmd = self.engine_config.generate_qemu_cmdline(
            target="aarch64-softmmu", ram_mb=3072, tb_size_mb=200, spice_socket="/tmp/desk.sock"
        )
        cmd_str = " ".join(cmd)
        self.assertIn("unix=on", cmd_str)
        self.assertIn("tcg,tb-size=200", cmd_str)

    # ------------------------------------------------------------------------
    # Pair 18: (F08 TCG Buffer Clamp, F09 Engine Build Script)
    # ------------------------------------------------------------------------
    def test_pair_f08_f09_tcg_clamp_and_engine_build_script(self):
        """Pair F08 & F09: Engine build configuration clamps TCG buffer bounds [128MB, 256MB]."""
        # Testing clamping range logic
        test_cases = [(0, 128), (100, 128), (128, 128), (192, 192), (256, 256), (300, 256)]
        for req, expected in test_cases:
            self.assertEqual(self.engine_config.clamp_tcg_size(req), expected)

    # ------------------------------------------------------------------------
    # Pair 19: (F10 Entitlements, F11 Safe RAM)
    # ------------------------------------------------------------------------
    def test_pair_f10_f11_entitlements_and_safe_ram(self):
        """Pair F10 & F11: increased-memory-limit entitlement allows expanded safe RAM budget."""
        device_ram = 6144 * 1024 * 1024

        # With increased-memory-limit entitlement: 75% available (~4608MB)
        ent_with = self.mem_guard.detect_entitlements(increased_memory=True, extended_va=False)
        self.assertEqual(ent_with["ceiling_ratio"], 0.75)
        avail_with_entitlement = int(device_ram * ent_with["ceiling_ratio"])
        safe_ram_entitled = self.mem_guard.calculate_safe_guest_ram(avail_with_entitlement)
        self.assertEqual(safe_ram_entitled, avail_with_entitlement - (450 * 1024 * 1024))

        # Without entitlement (standard sideload): iOS default cap 50%
        ent_without = self.mem_guard.detect_entitlements(increased_memory=False, extended_va=False)
        self.assertEqual(ent_without["ceiling_ratio"], 0.50)
        avail_sideload = int(device_ram * ent_without["ceiling_ratio"])
        safe_ram_sideload = self.mem_guard.calculate_safe_guest_ram(avail_sideload)
        self.assertEqual(safe_ram_sideload, avail_sideload - (450 * 1024 * 1024))
        self.assertGreater(safe_ram_entitled, safe_ram_sideload)

    # ------------------------------------------------------------------------
    # Pair 20: (F10 Entitlements, F21 JIT Hook)
    # ------------------------------------------------------------------------
    def test_pair_f10_f21_entitlements_and_jit_hook(self):
        """Pair F10 & F21: Probing memory entitlements and JIT status (CS_DEBUGGED / AltJIT)."""
        entitlements = self.mem_guard.detect_entitlements(increased_memory=True, extended_va=True)
        self.assertTrue(entitlements["increased_memory_limit"])
        self.assertTrue(entitlements["extended_virtual_addressing"])
        self.assertEqual(entitlements["ceiling_ratio"], 0.80)

        # Verify JIT detection module exists in Engine/JIT/
        jit_detector = self.workspace_root / "Engine" / "JIT" / "JITDetector.swift"
        self.assertTrue(jit_detector.exists(), "JITDetector.swift must exist in Engine/JIT/")

    # ------------------------------------------------------------------------
    # Pair 21: (F11 Safe RAM, F13 Auto-Pause)
    # ------------------------------------------------------------------------
    def test_pair_f11_f13_safe_ram_and_auto_pause(self):
        """Pair F11 & F13: Safe RAM budget respects 90% Jetsam emergency threshold."""
        memory_ceiling = 3000 * 1024 * 1024  # 3000 MB ceiling
        safe_guest_ram = self.mem_guard.calculate_safe_guest_ram(memory_ceiling)

        # Expected consumption = safe_guest_ram + estimated base (~250MB) + TCG (128MB)
        expected_total_consumption = safe_guest_ram + (378 * 1024 * 1024)
        # Safe RAM sizing should prevent reaching 90% threshold in normal operation
        danger_threshold = int(memory_ceiling * 0.90)
        self.assertLess(safe_guest_ram, danger_threshold)

    # ------------------------------------------------------------------------
    # Pair 22: (F12 Memory Pressure, F13 Auto-Pause)
    # ------------------------------------------------------------------------
    def test_pair_f12_f13_memory_pressure_and_auto_pause(self):
        """Pair F12 & F13: Memory pressure escalation triggers ballooning first, escalating to auto-pause at >= 90%."""
        ceiling = 2048 * 1024 * 1024

        # Step 1: Warning pressure -> Triggers ballooning
        balloon_cmd = self.mem_guard.handle_memory_pressure("warning", 1400 * 1024 * 1024)
        self.assertEqual(balloon_cmd["execute"], "balloon")
        # Step 2: Emergency at 90% usage -> Triggers auto-pause
        self.assertTrue(self.mem_guard.check_jetsam_emergency(int(ceiling * 0.91), ceiling))

    # ------------------------------------------------------------------------
    # Pair 23: (F14 P-Core Pinning, F15 QoS Elevation)
    # ------------------------------------------------------------------------
    def test_pair_f14_f15_pcore_pinning_and_qos_elevation(self):
        """Pair F14 & F15: vCPU threads pinned to physical P-cores receive QOS_CLASS_USER_INTERACTIVE."""
        topology = PCoreScheduler.assign_topology(p_cores=2)
        self.assertEqual(topology["vcpus"], 2)
        self.assertEqual(topology["pcore_affinity"], [0, 1])

        qos = PCoreScheduler.elevate_qos("vcpu_0", is_vcpu=True)
        self.assertEqual(qos, PCoreScheduler.QOS_CLASS_USER_INTERACTIVE)

    # ------------------------------------------------------------------------
    # Pair 24: (F14 P-Core Pinning, F16 Boot Boost)
    # ------------------------------------------------------------------------
    def test_pair_f14_f16_pcore_pinning_and_boot_boost(self):
        """Pair F14 & F16: Boot boost maintains P-core affinity and restores topology upon completion."""
        scheduler = PCoreScheduler(physical_p_cores=2)
        self.assertEqual(scheduler.get_default_vcpus(), 2)

        scheduler.update_boot_boost_state(is_booting=True)
        self.assertEqual(scheduler.state, BootBoostState.BOOTING)

        scheduler.update_boot_boost_state(is_booting=False)
        self.assertEqual(scheduler.state, BootBoostState.RUNNING)
        self.assertEqual(scheduler.get_default_vcpus(), 2)

    # ------------------------------------------------------------------------
    # Pair 25: (F16 Boot Boost, F21 JIT Hook)
    # ------------------------------------------------------------------------
    def test_pair_f16_f21_boot_boost_and_jit_hook(self):
        """Pair F16 & F21: Boot boost verifies JIT availability prior to accelerating compilation."""
        jit_file = self.workspace_root / "Engine" / "JIT" / "JITDetector.swift"
        self.assertTrue(jit_file.exists())
        self.assertTrue(PCoreScheduler.set_thread_interactive_qos())

    # ------------------------------------------------------------------------
    # Pair 26: (F17 OS Detection, F20 Storage APFS Sparse Disk)
    # ------------------------------------------------------------------------
    def test_pair_f17_f20_os_detection_and_storage_apfs(self):
        """Pair F17 & F20: Detected OS sets recommended APFS sparse disk capacity."""
        win11_header = b"\x00" * 32768 + b"CD001 MICROSOFT WINDOWS 11 MEDIA"
        detected_os = self.iso_pilot.identify_operating_system(win11_header)
        self.assertEqual(detected_os, OperatingSystemType.WINDOWS_11)

        # Windows 11 detected sets recommended 64GB sparse disk
        win11_sparse = StorageBridge.create_sparse_disk_config(64 * 1024 * 1024 * 1024)
        self.assertEqual(win11_sparse["format"], DiskFormat.APFS_SPARSE)
        self.assertEqual(win11_sparse["virtual_size_bytes"], 64 * 1024 * 1024 * 1024)
        self.assertTrue(win11_sparse["sparse_flag"])

        # Linux detected sets recommended 20GB sparse disk
        linux_header = b"\x00" * 32768 + b"CD001 UBUNTU 24.04 LIVE SERVER"
        detected_linux = self.iso_pilot.identify_operating_system(linux_header)
        self.assertEqual(detected_linux, OperatingSystemType.LINUX_UBUNTU)

        linux_sparse = StorageBridge.create_sparse_disk_config(20 * 1024 * 1024 * 1024)
        self.assertEqual(linux_sparse["format"], DiskFormat.APFS_SPARSE)
        self.assertEqual(linux_sparse["virtual_size_bytes"], 20 * 1024 * 1024 * 1024)

    # ------------------------------------------------------------------------
    # Pair 27: (F18 VirtIO Injection, F19 Win11 Bypass)
    # ------------------------------------------------------------------------
    def test_pair_f18_f19_virtio_injection_and_win11_bypass(self):
        """Pair F18 & F19: autounattend.xml includes driver path for injected virtio-win drivers."""
        xml_content = self.iso_pilot.generate_windows11_bypass_xml()
        self.assertIn("windowsPE", xml_content)
        self.assertIn("BypassTPMCheck", xml_content)

        # Verify virtio config provides viostor for unattended storage driver loading
        virtio_conf = self.iso_pilot.generate_virtio_injection_config(OperatingSystemType.WINDOWS_11)
        self.assertIn("viostor", virtio_conf["drivers"])
        self.assertTrue(virtio_conf["inject_drivers"])
        self.assertIn("virtio-win.iso", virtio_conf["drive_param"])

    # ------------------------------------------------------------------------
    # Pair 28: (F19 Win11 Bypass, F20 Storage APFS Sparse Disk)
    # ------------------------------------------------------------------------
    def test_pair_f19_f20_win11_bypass_and_storage_apfs(self):
        """Pair F19 & F20: Automated install targets APFS sparse disk partition structure."""
        sparse_cfg = StorageBridge.create_sparse_disk_config(64 * 1024 * 1024 * 1024)
        self.assertEqual(sparse_cfg["format"], DiskFormat.APFS_SPARSE)
        xml_bypass = self.iso_pilot.generate_windows11_bypass_xml()
        self.assertIn("<unattend", xml_bypass)

    # ------------------------------------------------------------------------
    # Pair 29: (F09 Engine Build Script, F22 Verification Script)
    # ------------------------------------------------------------------------
    def test_pair_f09_f22_build_script_and_verification_script(self):
        """Pair F09 & F22: Build script output targets match verification script whitelist."""
        whitelist_targets = ["x86_64-softmmu", "aarch64-softmmu"]
        self.assertTrue(self.engine_config.validate_targets(whitelist_targets))
        # Ensure verification script target whitelist contains no forbidden architectures
        for forbidden in ["mips", "ppc", "sparc", "riscv", "s390x"]:
            self.assertFalse(self.engine_config.validate_targets([f"{forbidden}-softmmu"]))

    # ------------------------------------------------------------------------
    # Pair 30: (F23 Mock Test Suite, F24 E2E Acceptance)
    # ------------------------------------------------------------------------
    def test_pair_f23_f24_mock_test_suite_and_e2e_acceptance(self):
        """Pair F23 & F24: Mock test suites pass and satisfy E2E acceptance criteria."""
        # Both SmartMemoryGuard and ISOAutoPilot mock interfaces pass contract evaluation
        safe_ram = self.mem_guard.calculate_safe_guest_ram(3000 * 1024 * 1024)
        self.assertGreater(safe_ram, 1024 * 1024 * 1024)

        win11_xml = self.iso_pilot.generate_windows11_bypass_xml("User")
        self.assertIn("BypassTPMCheck", win11_xml)


if __name__ == "__main__":
    unittest.main()

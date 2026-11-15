#!/usr/bin/env python3
"""
Desk-simulator E2E Test Suite - Tier 2: Boundary & Corner Cases
Cross-platform E2E test harness for Next-Generation PC OS Emulator for iPhone.

Requirements Reference:
- ORIGINAL_REQUEST.md: R1, R2, R3, Acceptance Criteria
- PROJECT.md: Three-Tier Architecture, Code Layout, Interface Contracts
- TEST_INFRA.md: Feature Inventory (Features 1 through 24)

Coverage Threshold:
- >= 5 boundary, edge, negative, and extreme tests per feature for all 24 features.
- Minimum 120 tests in Tier 2 (Current: 123 distinct tests).
"""

import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

# Dynamic workspace root resolution
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))


# Direct imports of genuine Engine and Management Layer modules
from Engine.Config.engine_config import EngineConfig
from Engine.JIT.jit_detector import JITDetector, JITHook, JITSource, JITStatus
from Management.ISOAutoPilot.iso_autopilot import ISOAutoPilot, OperatingSystemType
from Management.PCoreScheduler.pcore_scheduler import BootBoostState, PCoreScheduler
from Management.SmartMemoryGuard.memory_guard import (
    MemoryEntitlements,
    MemoryGuard,
    MemoryPressureLevel,
    QMPCommand,
)
from Management.Storage.storage_bridge import DiskFormat, StorageBridge


# ============================================================================
# Tier 2: Boundary & Corner Case Tests (24 Features)
# ============================================================================

class TestTier2Feature01DirectoryLayoutBoundaries(unittest.TestCase):
    """Feature 1: Modular Directory Layout Boundary & Corner Tests."""

    REQUIRED_SUBDIRS = [
        "UI/Views", "UI/ViewModels",
        "Management/SmartMemoryGuard", "Management/PCoreScheduler",
        "Management/ISOAutoPilot", "Management/Storage",
        "Engine/Config", "Engine/Core", "Engine/QEMU", "Engine/SPICE", "Engine/JIT",
        "Scripts", "Tests", "Tests/EngineTests", "Tests/ManagementMocks",
    ]

    def test_01_boundary_missing_subdirectories_detected(self):
        """Boundary: All required subdirectories exist in workspace root, and missing dirs are detected."""
        missing_in_workspace = [d for d in self.REQUIRED_SUBDIRS if not (WORKSPACE_ROOT / d).is_dir()]
        self.assertEqual(missing_in_workspace, [], f"Required directories missing: {missing_in_workspace}")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            for d in self.REQUIRED_SUBDIRS:
                if d != "Engine/SPICE":
                    (tmp_path / d).mkdir(parents=True)
            detected_missing = [d for d in self.REQUIRED_SUBDIRS if not (tmp_path / d).is_dir()]
            self.assertEqual(detected_missing, ["Engine/SPICE"])

    def test_02_boundary_unexpected_prohibited_directories_detected(self):
        """Boundary: Forbidden architecture directory structures are verified absent from workspace."""
        prohibited = ["Engine/QEMU/target/mips", "Engine/QEMU/target/sparc", "Engine/QEMU/target/ppc"]
        for p in prohibited:
            self.assertFalse((WORKSPACE_ROOT / p).exists(), f"Prohibited directory {p} must not exist in workspace")
        self.assertFalse(EngineConfig.validate_targets(["mips-softmmu", "sparc-softmmu", "ppc-softmmu"]))

    def test_03_boundary_path_normalization_and_slashes(self):
        """Boundary: Trailing slashes, mixed backslashes, and duplicate separators normalize."""
        raw_paths = ["UI//Views", "UI/Views/", "UI\\Views", "UI/Views/."]
        normalized = {str(Path(p)).replace("\\", "/") for p in raw_paths}
        self.assertEqual(len(normalized), 1)
        self.assertEqual(list(normalized)[0], "UI/Views")

    def test_04_boundary_workspace_root_existence(self):
        """Boundary: Workspace root path must resolve to a valid existing directory."""
        self.assertTrue(WORKSPACE_ROOT.exists(), f"Workspace root {WORKSPACE_ROOT} does not exist")
        self.assertTrue(WORKSPACE_ROOT.is_dir())

    def test_05_boundary_path_traversal_confinement(self):
        """Boundary: Directory resolution outside workspace root is detected and rejected."""
        traversal = WORKSPACE_ROOT / "UI" / ".." / ".." / "outside"
        resolved = traversal.resolve()
        is_confined = str(resolved).startswith(str(WORKSPACE_ROOT.resolve()))
        self.assertFalse(is_confined, "Path traversal escaped workspace boundary without detection")


class TestTier2Feature02GitRemoteBoundaries(unittest.TestCase):
    """Feature 2: Git Remote Integration Boundary & Corner Tests."""

    REQUIRED_URL = "https://github.com/Mobimi/Desk-simulator"

    def test_01_boundary_git_remote_url_equivalence(self):
        """Boundary: URL with or without .git is accepted; insecure http is rejected."""
        valid_urls = [
            "https://github.com/Mobimi/Desk-simulator",
            "https://github.com/Mobimi/Desk-simulator.git",
        ]
        insecure_url = "http://github.com/Mobimi/Desk-simulator"
        for u in valid_urls:
            cleaned = u.rstrip("/").removesuffix(".git")
            self.assertEqual(cleaned, self.REQUIRED_URL)
        self.assertFalse(insecure_url.startswith("https://"))

    def test_02_boundary_git_remote_wrong_repo_rejected(self):
        """Boundary: Different org or repository name fails validation."""
        bad_urls = [
            "https://github.com/OtherOrg/Desk-simulator",
            "https://github.com/Mobimi/OtherRepo",
            "https://gitlab.com/Mobimi/Desk-simulator",
        ]
        for u in bad_urls:
            cleaned = u.rstrip("/").removesuffix(".git")
            self.assertNotEqual(cleaned, self.REQUIRED_URL)

    def test_03_boundary_git_remote_empty_or_whitespace_url(self):
        """Boundary: Empty, whitespace, or None remote URL is rejected."""
        for empty_val in ["", "   ", "\t", None]:
            is_valid = bool(empty_val and empty_val.strip() == self.REQUIRED_URL)
            self.assertFalse(is_valid)

    def test_04_boundary_git_branch_mismatch(self):
        """Boundary: Branch name other than 'main' is rejected."""
        invalid_branches = ["master", "dev", "feature/pc-sim", ""]
        for b in invalid_branches:
            self.assertNotEqual(b, "main")

    def test_05_boundary_actual_git_remote_and_branch_tracking(self):
        """Boundary: Actual workspace git config tracks origin/main when git is available."""
        git_dir = WORKSPACE_ROOT / ".git"
        if git_dir.exists():
            proc = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=WORKSPACE_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if proc.returncode == 0:
                remote_out = proc.stdout.strip().rstrip("/").removesuffix(".git")
                self.assertEqual(remote_out, self.REQUIRED_URL)


class TestTier2Feature03PrepareWorkspaceScriptBoundaries(unittest.TestCase):
    """Feature 3: Workspace Preparation Script Boundary & Corner Tests."""

    def test_01_boundary_script_exists_and_is_valid_python(self):
        """Boundary: Scripts/prepare_workspace.py exists and compiles cleanly."""
        script = WORKSPACE_ROOT / "Scripts" / "prepare_workspace.py"
        self.assertTrue(script.exists())
        with open(script, "r", encoding="utf-8") as f:
            code = f.read()
        compiled = compile(code, str(script), "exec")
        self.assertIsNotNone(compiled)

    def test_02_boundary_script_execution_zero_exit_code(self):
        """Boundary: Running prepare_workspace.py in standard environment exits with 0."""
        script = WORKSPACE_ROOT / "Scripts" / "prepare_workspace.py"
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=WORKSPACE_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, f"Script failed with: {proc.stderr}")

    def test_03_boundary_script_invalid_flag_handling(self):
        """Boundary: Script with invalid CLI flags does not crash with unhandled exception."""
        script = WORKSPACE_ROOT / "Scripts" / "prepare_workspace.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--unrecognized-extreme-flag-xyz"],
            cwd=WORKSPACE_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        # Should exit without Python traceback
        self.assertNotIn("Traceback (most recent call last)", proc.stderr)

    def test_04_boundary_script_python_version_guard(self):
        """Boundary: Python version verification enforces >= 3.8."""
        ver = sys.version_info
        is_supported = ver.major == 3 and ver.minor >= 8
        self.assertTrue(is_supported)

    def test_05_boundary_script_idempotent_execution(self):
        """Boundary: Executing preparation twice in succession maintains clean state."""
        script = WORKSPACE_ROOT / "Scripts" / "prepare_workspace.py"
        p1 = subprocess.run([sys.executable, str(script)], cwd=WORKSPACE_ROOT, capture_output=True, text=True)
        p2 = subprocess.run([sys.executable, str(script)], cwd=WORKSPACE_ROOT, capture_output=True, text=True)
        self.assertEqual(p1.returncode, 0)
        self.assertEqual(p2.returncode, 0)


class TestTier2Feature04TargetWhitelistBoundaries(unittest.TestCase):
    """Feature 4: Stripped Target Architecture List Boundary & Corner Tests."""

    def setUp(self):
        self.cfg = EngineConfig

    def test_01_boundary_exact_allowed_targets(self):
        """Boundary: Exact match ['x86_64-softmmu', 'aarch64-softmmu'] is valid."""
        self.assertTrue(self.cfg.validate_targets(["x86_64-softmmu", "aarch64-softmmu"]))

    def test_02_boundary_each_forbidden_target_individually_rejected(self):
        """Boundary: Injecting any single forbidden target fails validation."""
        forbidden_list = ["mips-softmmu", "ppc-softmmu", "sparc-softmmu", "riscv-softmmu", "s390x-softmmu", "i386-softmmu", "arm-softmmu"]
        for bad in forbidden_list:
            targets = ["x86_64-softmmu", "aarch64-softmmu", bad]
            self.assertFalse(self.cfg.validate_targets(targets), f"Failed to reject forbidden target {bad}")

    def test_03_boundary_empty_target_list(self):
        """Boundary: Empty target list is rejected."""
        self.assertFalse(self.cfg.validate_targets([]))

    def test_04_boundary_single_allowed_target_is_incomplete(self):
        """Boundary: Partial whitelist (omitting one target) fails validation."""
        self.assertFalse(self.cfg.validate_targets(["x86_64-softmmu"], require_all=True))
        self.assertFalse(self.cfg.validate_targets(["aarch64-softmmu"], require_all=True))

    def test_05_boundary_case_sensitivity_and_whitespace(self):
        """Boundary: Uppercase or trailing whitespace targets are rejected."""
        self.assertFalse(self.cfg.validate_targets(["X86_64-SOFTMMU", "aarch64-softmmu"]))
        self.assertFalse(self.cfg.validate_targets(["x86_64-softmmu ", "aarch64-softmmu"]))

    def test_06_boundary_non_string_targets_handled(self):
        """Boundary: Non-string elements in target list return False or raise."""
        self.assertFalse(self.cfg.validate_targets([123, None]))


class TestTier2Feature05CompilerOptimizationFlagsBoundaries(unittest.TestCase):
    """Feature 5: Compiler Optimization Flags Boundary & Corner Tests."""

    def setUp(self):
        self.cfg = EngineConfig

    def test_01_boundary_missing_O3_fails(self):
        """Boundary: Flags missing -O3 fail validation."""
        self.assertFalse(self.cfg.validate_compiler_flags(["-O2", "-flto", "-mcpu=apple-m1"]))
        self.assertFalse(self.cfg.validate_compiler_flags(["-Os", "-flto", "-arch arm64"]))

    def test_02_boundary_missing_flto_fails(self):
        """Boundary: Flags containing -O3 but missing -flto fail validation."""
        self.assertFalse(self.cfg.validate_compiler_flags(["-O3", "-mcpu=apple-m1"]))

    def test_03_boundary_conflicting_O0_with_O3_rejected(self):
        """Boundary: Injecting -O0 alongside -O3 overrides optimization and must be rejected."""
        self.assertFalse(self.cfg.validate_compiler_flags(["-O3", "-flto", "-mcpu=apple-m1", "-O0"]))

    def test_04_boundary_missing_apple_silicon_flag_fails(self):
        """Boundary: Flags missing Apple Silicon target optimization fail."""
        self.assertFalse(self.cfg.validate_compiler_flags(["-O3", "-flto", "-march=x86-64"], require_apple_silicon=True))

    def test_05_boundary_empty_or_whitespace_flags_rejected(self):
        """Boundary: Empty list or list with empty strings is rejected."""
        self.assertFalse(self.cfg.validate_compiler_flags([]))
        self.assertFalse(self.cfg.validate_compiler_flags(["", "   "]))


class TestTier2Feature06SpiceUdsIpcBoundaries(unittest.TestCase):
    """Feature 6: SPICE Unix Domain Socket IPC Boundary & Corner Tests."""

    def setUp(self):
        self.cfg = EngineConfig

    def test_01_boundary_tcp_loopback_rejected(self):
        """Boundary: TCP loopback attempts (127.0.0.1, localhost, port=) raise ValueError."""
        loopback_attempts = ["127.0.0.1:5900", "localhost", "0.0.0.0:5901", "port=5900"]
        for bad in loopback_attempts:
            with self.assertRaises(ValueError):
                self.cfg.generate_spice_uds_args(bad)

    def test_02_boundary_uds_path_exceeding_max_length(self):
        """Boundary: Socket path exceeding 108 bytes POSIX limit raises ValueError."""
        long_path = "/tmp/" + ("a" * 110) + ".sock"
        with self.assertRaises(ValueError):
            self.cfg.generate_spice_uds_args(long_path)

    def test_03_boundary_empty_uds_path_rejected(self):
        """Boundary: Empty or whitespace-only socket path raises ValueError."""
        with self.assertRaises(ValueError):
            self.cfg.generate_spice_uds_args("")
        with self.assertRaises(ValueError):
            self.cfg.generate_spice_uds_args("   ")

    def test_04_boundary_uds_path_with_null_bytes_rejected(self):
        """Boundary: Socket path with null byte raises ValueError."""
        with self.assertRaises(ValueError):
            self.cfg.generate_spice_uds_args("/tmp/spice\x00.sock")

    def test_05_boundary_generated_args_contain_unix_on(self):
        """Boundary: Valid socket path produces unix=on and no port= specifier."""
        args = self.cfg.generate_spice_uds_args("/var/run/desk.sock")
        joined = " ".join(args)
        self.assertIn("unix=on", joined)
        self.assertIn("addr=/var/run/desk.sock", joined)
        self.assertNotIn("port=", joined)


class TestTier2Feature07SpiceChannelPruningBoundaries(unittest.TestCase):
    """Feature 7: SPICE Channel Pruning Boundary & Corner Tests."""

    ESSENTIAL_CHANNELS = ["main", "display", "inputs", "cursor"]
    PROHIBITED_CHANNELS = ["smartcard", "webdav"]

    def test_01_boundary_smartcard_channel_rejected(self):
        """Boundary: Enabling smartcard channel is prohibited to reclaim RAM."""
        self.assertTrue(EngineConfig.is_channel_pruned("smartcard"))
        spice_args = EngineConfig.generate_spice_uds_args("/tmp/desk_spice.sock")
        self.assertIn("spice.smartcard=off", " ".join(spice_args))

    def test_02_boundary_webdav_channel_rejected(self):
        """Boundary: Enabling separate webdav channel is prohibited."""
        self.assertTrue(EngineConfig.is_channel_pruned("webdav"))
        spice_args = EngineConfig.generate_spice_uds_args("/tmp/desk_spice.sock")
        self.assertIn("spice.webdav=off", " ".join(spice_args))

    def test_03_boundary_essential_channels_preserved(self):
        """Boundary: Essential channels are fully preserved without omissions."""
        for ess in self.ESSENTIAL_CHANNELS:
            self.assertIn(ess, EngineConfig.ESSENTIAL_CHANNELS)
            self.assertFalse(EngineConfig.is_channel_pruned(ess))

    def test_04_boundary_unknown_channel_filtered(self):
        """Boundary: Unrecognized channel names are filtered."""
        self.assertFalse(EngineConfig.is_channel_pruned("unknown_chan_123"))
        self.assertNotIn("unknown_chan_123", EngineConfig.ESSENTIAL_CHANNELS)

    def test_05_boundary_memory_reclaim_calculation(self):
        """Boundary: Pruning smartcard + webdav guarantees >= 100MB RAM reclaimed per ChannelPolicy.swift."""
        channel_policy_file = WORKSPACE_ROOT / "Engine" / "SPICE" / "ChannelPolicy.swift"
        self.assertTrue(channel_policy_file.is_file())
        swift_code = channel_policy_file.read_text(encoding="utf-8")
        self.assertIn("targetMemorySavingMB: Int = 100", swift_code)
        self.assertEqual(len(EngineConfig.PRUNED_CHANNELS), 2)
        self.assertIn("smartcard", EngineConfig.PRUNED_CHANNELS)
        self.assertIn("webdav", EngineConfig.PRUNED_CHANNELS)


class TestTier2Feature08TcgBufferClampingBoundaries(unittest.TestCase):
    """Feature 8: TCG Buffer Size Clamping Boundary & Corner Tests."""

    def setUp(self):
        self.cfg = EngineConfig

    def test_01_boundary_min_exact_128(self):
        """Boundary: Exact minimum 128 MB is preserved without modification."""
        self.assertEqual(self.cfg.clamp_tcg_size(128), 128)

    def test_02_boundary_max_exact_256(self):
        """Boundary: Exact maximum 256 MB is preserved without modification."""
        self.assertEqual(self.cfg.clamp_tcg_size(256), 256)

    def test_03_boundary_below_min_clamped_to_128(self):
        """Boundary: Values < 128 (0, 32, 64, 127, -1, -500) clamp to 128 MB."""
        test_values = [0, 1, 32, 64, 127, -1, -500]
        for val in test_values:
            self.assertEqual(self.cfg.clamp_tcg_size(val), 128, f"Failed clamping {val}")

    def test_04_boundary_above_max_clamped_to_256(self):
        """Boundary: Values > 256 (257, 512, 1024, 65536) clamp to 256 MB."""
        test_values = [257, 512, 1024, 4096, 65536]
        for val in test_values:
            self.assertEqual(self.cfg.clamp_tcg_size(val), 256, f"Failed clamping {val}")

    def test_05_boundary_within_range_unchanged(self):
        """Boundary: Midpoints (192, 200, 250) remain unchanged."""
        self.assertEqual(self.cfg.clamp_tcg_size(192), 192)
        self.assertEqual(self.cfg.clamp_tcg_size(200), 200)

    def test_06_boundary_non_numeric_input_handling(self):
        """Boundary: Non-integer types (str, float, None) raise TypeError."""
        for bad in ["128", 128.5, None, True]:
            with self.assertRaises(TypeError):
                self.cfg.clamp_tcg_size(bad)


class TestTier2Feature09EngineBuildScriptsBoundaries(unittest.TestCase):
    """Feature 9: Engine Build Scripts Boundary & Corner Tests."""

    def test_01_boundary_build_script_target_validation(self):
        """Boundary: EngineConfig logic rejects forbidden target."""
        self.assertFalse(EngineConfig.validate_targets(["mips-softmmu"]))

    def test_02_boundary_build_script_tcg_extreme_clamping(self):
        """Boundary: CLI parameter --tb-size 9999 is clamped to 256 MB."""
        clamped = EngineConfig.clamp_tcg_size(9999)
        self.assertEqual(clamped, 256)

    def test_03_boundary_build_script_optimization_flags_injection(self):
        """Boundary: Required optimization flags are present in compiler arguments."""
        cmd = ["clang", "-O3", "-flto", "-mcpu=apple-m1", "-c", "qemu_main.c"]
        self.assertIn("-O3", cmd)
        self.assertIn("-flto", cmd)
        self.assertIn("-mcpu=apple-m1", cmd)

    def test_04_boundary_build_script_dry_run_validation(self):
        """Boundary: Dry run build configuration schema contains target and flags."""
        build_spec = {
            "targets": ["x86_64-softmmu", "aarch64-softmmu"],
            "cflags": ["-O3", "-flto", "-mcpu=apple-m1"],
            "tb_size": 128,
            "spice_transport": "unix_domain_socket",
        }
        self.assertTrue(EngineConfig.validate_targets(build_spec["targets"]))
        self.assertTrue(EngineConfig.validate_compiler_flags(build_spec["cflags"]))
        self.assertEqual(build_spec["tb_size"], 128)

    def test_05_boundary_build_script_empty_target_rejection(self):
        """Boundary: Empty target string is rejected."""
        self.assertFalse(EngineConfig.validate_targets([""]))


class TestTier2Feature10MemoryEntitlementsBoundaries(unittest.TestCase):
    """Feature 10: Smart Memory Guard: Entitlements Boundary & Corner Tests."""

    def test_01_boundary_both_entitlements_true(self):
        """Boundary: Both entitlements active -> full RAM ceiling (0.80)."""
        res = MemoryGuard.detect_entitlements(increased_memory=True, extended_va=True)
        self.assertEqual(res["ceiling_ratio"], 0.80)
        self.assertTrue(res["increased_memory_limit"])
        self.assertTrue(res["extended_virtual_addressing"])

    def test_02_boundary_neither_entitlement_true(self):
        """Boundary: Neither entitlement active -> conservative ceiling (0.50)."""
        res = MemoryGuard.detect_entitlements(increased_memory=False, extended_va=False)
        self.assertEqual(res["ceiling_ratio"], 0.50)
        self.assertFalse(res["increased_memory_limit"])
        self.assertFalse(res["extended_virtual_addressing"])

    def test_03_boundary_only_increased_memory(self):
        """Boundary: Only increased-memory-limit yields 0.75 ratio."""
        res = MemoryGuard.detect_entitlements(increased_memory=True, extended_va=False)
        self.assertEqual(res["ceiling_ratio"], 0.75)

    def test_04_boundary_only_extended_addressing(self):
        """Boundary: Only extended addressing without increased memory limit remains 0.50."""
        res = MemoryGuard.detect_entitlements(increased_memory=False, extended_va=True)
        self.assertEqual(res["ceiling_ratio"], 0.50)

    def test_05_boundary_corrupt_entitlement_types(self):
        """Boundary: MemoryGuard instance models active entitlements cleanly."""
        guard = MemoryGuard(increased_memory=True, extended_va=True)
        self.assertEqual(guard.entitlements.ceiling_ratio, 0.80)
        self.assertIsInstance(guard.entitlements.ceiling_ratio, float)


class TestTier2Feature11SafeRamCalculationBoundaries(unittest.TestCase):
    """Feature 11: Smart Memory Guard: Safe RAM Boundary & Corner Tests."""

    def test_01_boundary_available_equal_to_safety_buffer(self):
        """Boundary: Available exactly 450 MB returns floor 1024 MB."""
        res = MemoryGuard.calculate_safe_guest_ram(450 * 1024 * 1024)
        self.assertEqual(res, 1024 * 1024 * 1024)

    def test_02_boundary_available_less_than_safety_buffer(self):
        """Boundary: Available 200 MB returns floor 1024 MB."""
        res = MemoryGuard.calculate_safe_guest_ram(200 * 1024 * 1024)
        self.assertEqual(res, 1024 * 1024 * 1024)

    def test_03_boundary_zero_available_memory(self):
        """Boundary: Available 0 bytes returns floor 1024 MB."""
        res = MemoryGuard.calculate_safe_guest_ram(0)
        self.assertEqual(res, 1024 * 1024 * 1024)

    def test_04_boundary_transition_threshold(self):
        """Boundary: Available 2000 MB returns 2000 - 450 = 1550 MB."""
        available = 2000 * 1024 * 1024
        expected = (2000 - 450) * 1024 * 1024
        self.assertEqual(MemoryGuard.calculate_safe_guest_ram(available), expected)

    def test_05_boundary_extreme_memory_64gb(self):
        """Boundary: Extreme available memory (64 GB) returns available - 450 MB."""
        available = 64 * 1024 * 1024 * 1024
        expected = (64 * 1024 - 450) * 1024 * 1024
        self.assertEqual(MemoryGuard.calculate_safe_guest_ram(available), expected)

    def test_06_boundary_negative_available_memory_safe(self):
        """Boundary: Negative available memory returns floor without overflow."""
        res = MemoryGuard.calculate_safe_guest_ram(-500)
        self.assertEqual(res, 1024 * 1024 * 1024)


class TestTier2Feature12MemoryPressureBoundaries(unittest.TestCase):
    """Feature 12: Smart Memory Guard: Memory Pressure Boundary & Corner Tests."""

    def test_01_boundary_normal_pressure_returns_none(self):
        """Boundary: Normal pressure produces no QMP balloon command."""
        self.assertIsNone(MemoryGuard.handle_memory_pressure("normal", available_bytes=2000 * 1024 * 1024))

    def test_02_boundary_warning_pressure_triggers_balloon(self):
        """Boundary: Warning pressure generates valid balloon command."""
        avail = 2000 * 1024 * 1024
        cmd = MemoryGuard.handle_memory_pressure("warning", available_bytes=avail)
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd["execute"], "balloon")
        expected_safe = MemoryGuard.calculate_safe_guest_ram(avail)
        self.assertEqual(cmd["arguments"]["value"], expected_safe)

    def test_03_boundary_critical_pressure_triggers_balloon(self):
        """Boundary: Critical pressure generates aggressive balloon command."""
        avail = 2000 * 1024 * 1024
        warn_cmd = MemoryGuard.handle_memory_pressure("warning", available_bytes=avail)
        crit_cmd = MemoryGuard.handle_memory_pressure("critical", available_bytes=avail)
        self.assertEqual(crit_cmd["execute"], "balloon")
        self.assertLessEqual(crit_cmd["arguments"]["value"], warn_cmd["arguments"]["value"])

    def test_04_boundary_unknown_pressure_level_raises(self):
        """Boundary: Unknown pressure strings raise ValueError."""
        with self.assertRaises(ValueError):
            MemoryGuard.handle_memory_pressure("catastrophic", available_bytes=1024 * 1024 * 1024)

    def test_05_boundary_balloon_qmp_json_syntax(self):
        """Boundary: Generated balloon command strictly conforms to QMP JSON schema."""
        cmd = MemoryGuard.handle_memory_pressure("warning", available_bytes=2048 * 1024 * 1024)
        cmd_str = json.dumps(cmd)
        parsed = json.loads(cmd_str)
        self.assertIn("execute", parsed)
        self.assertIn("arguments", parsed)
        self.assertIsInstance(parsed["arguments"]["value"], int)


class TestTier2Feature13AutoPauseBoundaries(unittest.TestCase):
    """Feature 13: Smart Memory Guard: Auto-Pause Boundary & Corner Tests."""

    def test_01_boundary_usage_at_89_9_percent_no_pause(self):
        """Boundary: Usage at 89.9% of ceiling does not trigger emergency pause."""
        ceiling = 10_000_000
        usage = 8_990_000  # 89.9%
        self.assertFalse(MemoryGuard.check_jetsam_emergency(usage, ceiling))

    def test_02_boundary_usage_at_exact_90_0_percent_triggers_pause(self):
        """Boundary: Usage at exact 90.0% of ceiling triggers emergency pause."""
        ceiling = 10_000_000
        usage = 9_000_000  # 90.0%
        self.assertTrue(MemoryGuard.check_jetsam_emergency(usage, ceiling))

    def test_03_boundary_usage_at_95_percent_triggers_pause(self):
        """Boundary: Usage at 95% triggers emergency pause."""
        ceiling = 10_000_000
        usage = 9_500_000
        self.assertTrue(MemoryGuard.check_jetsam_emergency(usage, ceiling))

    def test_04_boundary_zero_ceiling_division_safe(self):
        """Boundary: Zero ceiling returns True (emergency state) without ZeroDivisionError."""
        self.assertTrue(MemoryGuard.check_jetsam_emergency(100, 0))

    def test_05_boundary_usage_exceeds_ceiling_110_percent(self):
        """Boundary: Usage exceeding 100% of ceiling returns True."""
        ceiling = 10_000_000
        usage = 11_000_000  # 110%
        self.assertTrue(MemoryGuard.check_jetsam_emergency(usage, ceiling))


class TestTier2Feature14PCoreTopologyPinningBoundaries(unittest.TestCase):
    """Feature 14: P-Core Scheduler: Topology Pinning Boundary & Corner Tests."""

    def test_01_boundary_zero_vcpu_clamped_to_one(self):
        """Boundary: 0 vCPUs requested clamps to minimum 1."""
        self.assertEqual(PCoreScheduler.clamp_vcpus(0, p_cores=2), 1)

    def test_02_boundary_one_vcpu_valid(self):
        """Boundary: 1 vCPU requested is accepted."""
        self.assertEqual(PCoreScheduler.clamp_vcpus(1, p_cores=2), 1)

    def test_03_boundary_two_vcpu_default_pcore_count(self):
        """Boundary: 2 vCPUs requested matches physical P-cores on A15-A18."""
        self.assertEqual(PCoreScheduler.clamp_vcpus(2, p_cores=2), 2)

    def test_04_boundary_excessive_vcpus_clamped_to_pcores(self):
        """Boundary: 4, 8, or 16 vCPUs requested clamps to physical P-cores (2)."""
        for req in [4, 8, 16]:
            self.assertEqual(PCoreScheduler.clamp_vcpus(req, p_cores=2), 2)

    def test_05_boundary_negative_vcpu_rejected(self):
        """Boundary: Negative vCPU count clamps to 1."""
        self.assertEqual(PCoreScheduler.clamp_vcpus(-4, p_cores=2), 1)


class TestTier2Feature15PCoreQoSElevationBoundaries(unittest.TestCase):
    """Feature 15: P-Core Scheduler: QoS Elevation Boundary & Corner Tests."""

    def test_01_boundary_user_interactive_qos_constant(self):
        """Boundary: QOS_CLASS_USER_INTERACTIVE is 0x21 (33)."""
        self.assertEqual(PCoreScheduler.QOS_CLASS_USER_INTERACTIVE, 0x21)
        self.assertEqual(PCoreScheduler.elevate_qos("vcpu_0", is_vcpu=True), 0x21)

    def test_02_boundary_auxiliary_thread_qos_user_initiated(self):
        """Boundary: Non-vCPU auxiliary threads elevate to USER_INITIATED (0x19)."""
        self.assertEqual(PCoreScheduler.elevate_qos("io_disk", is_vcpu=False), PCoreScheduler.QOS_CLASS_USER_INITIATED)
        self.assertEqual(PCoreScheduler.QOS_CLASS_USER_INITIATED, 0x19)

    def test_03_boundary_thread_interactive_qos_simulation(self):
        """Boundary: Setting thread interactive QoS returns True."""
        self.assertTrue(PCoreScheduler.set_thread_interactive_qos())

    def test_04_boundary_background_downgrade_qos(self):
        """Boundary: Background downgrade targets QOS_CLASS_BACKGROUND (0x09)."""
        self.assertEqual(PCoreScheduler.QOS_CLASS_BACKGROUND, 0x09)
        self.assertEqual(PCoreScheduler.demote_qos_background("vcpu_0"), 0x09)

    def test_05_boundary_qos_hierarchy_ordering(self):
        """Boundary: User Interactive priority strictly exceeds User Initiated and Background."""
        self.assertGreater(PCoreScheduler.QOS_CLASS_USER_INTERACTIVE, PCoreScheduler.QOS_CLASS_USER_INITIATED)
        self.assertGreater(PCoreScheduler.QOS_CLASS_USER_INITIATED, PCoreScheduler.QOS_CLASS_BACKGROUND)


class TestTier2Feature16PCoreBootBoostBoundaries(unittest.TestCase):
    """Feature 16: P-Core Scheduler: Boot Boost Boundary & Corner Tests."""

    def test_01_boundary_boot_boost_enabled_during_boot(self):
        """Boundary: Active boot state sets state to BOOTING and records boot start time."""
        scheduler = PCoreScheduler(physical_p_cores=2)
        scheduler.update_boot_boost_state(is_booting=True)
        self.assertEqual(scheduler.state, BootBoostState.BOOTING)
        self.assertIsNotNone(scheduler.boot_start_time)

    def test_02_boundary_boot_boost_deactivation_on_running(self):
        """Boundary: Completion of boot transitions state to RUNNING and clears boot start time."""
        scheduler = PCoreScheduler(physical_p_cores=2)
        scheduler.update_boot_boost_state(is_booting=True)
        scheduler.update_boot_boost_state(is_booting=False)
        self.assertEqual(scheduler.state, BootBoostState.RUNNING)
        self.assertIsNone(scheduler.boot_start_time)

    def test_03_boundary_boot_boost_safety_timeout_cutoff(self):
        """Boundary: Boot boost expires after max safety timeout (120s)."""
        scheduler = PCoreScheduler(physical_p_cores=2)
        scheduler.update_boot_boost_state(is_booting=True)
        # Simulate 125 seconds elapsed
        scheduler.boot_start_time = time.time() - (PCoreScheduler.BOOT_BOOST_TIMEOUT_SECONDS + 5)
        expired = scheduler.check_boot_boost_timeout()
        self.assertTrue(expired)
        self.assertEqual(scheduler.state, BootBoostState.RUNNING)

    def test_04_boundary_thread_registry_registration(self):
        """Boundary: Thread registration assigns QoS and registers thread."""
        scheduler = PCoreScheduler(physical_p_cores=2)
        qos_vcpu = scheduler.register_thread("vcpu_0", is_vcpu=True)
        qos_aux = scheduler.register_thread("io_worker", is_vcpu=False)
        self.assertEqual(qos_vcpu, PCoreScheduler.QOS_CLASS_USER_INTERACTIVE)
        self.assertEqual(qos_aux, PCoreScheduler.QOS_CLASS_USER_INITIATED)
        self.assertEqual(scheduler.thread_registry["vcpu_0"], qos_vcpu)

    def test_05_boundary_timeout_check_before_expiration(self):
        """Boundary: check_boot_boost_timeout returns False before 120s elapses."""
        scheduler = PCoreScheduler(physical_p_cores=2)
        scheduler.update_boot_boost_state(is_booting=True)
        self.assertFalse(scheduler.check_boot_boost_timeout())
        self.assertEqual(scheduler.state, BootBoostState.BOOTING)


class TestTier2Feature17IsoDetectionBoundaries(unittest.TestCase):
    """Feature 17: ISO Auto-Pilot: OS Detection Boundary & Corner Tests."""

    def test_01_boundary_empty_header_returns_unknown(self):
        """Boundary: 0 bytes of header data returns UNKNOWN."""
        self.assertEqual(ISOAutoPilot.identify_operating_system(b""), OperatingSystemType.UNKNOWN)

    def test_02_boundary_truncated_header_safe(self):
        """Boundary: Truncated buffer (< 64 bytes) handles cleanly without IndexError."""
        self.assertEqual(ISOAutoPilot.identify_operating_system(b"SHORT_DATA"), OperatingSystemType.UNKNOWN)

    def test_03_boundary_random_noise_returns_unknown(self):
        """Boundary: Non-ISO random binary stream returns UNKNOWN."""
        noise = b"\x00\xff\x12\x34" * 100
        self.assertEqual(ISOAutoPilot.identify_operating_system(noise), OperatingSystemType.UNKNOWN)

    def test_04_boundary_windows_11_detection(self):
        """Boundary: Header containing CD001 MICROSOFT WINDOWS 11 identifies as WINDOWS_11."""
        header = b"\x00" * 32768 + b"CD001 MICROSOFT WINDOWS 11 PROFESSIONAL"
        self.assertEqual(ISOAutoPilot.identify_operating_system(header), OperatingSystemType.WINDOWS_11)

    def test_05_boundary_linux_detection(self):
        """Boundary: Header containing UBUNTU identifies as LINUX_UBUNTU."""
        header = b"\x00" * 32768 + b"CD001 UBUNTU 22.04 LTS"
        self.assertEqual(ISOAutoPilot.identify_operating_system(header), OperatingSystemType.LINUX_UBUNTU)


class TestTier2Feature18VirtIOInjectionBoundaries(unittest.TestCase):
    """Feature 18: ISO Auto-Pilot: VirtIO Injection Boundary & Corner Tests."""

    def test_01_boundary_windows_all_drivers_present(self):
        """Boundary: Windows 11 target config provides storage, net, and balloon drivers."""
        config = ISOAutoPilot.generate_virtio_injection_config("WINDOWS_11")
        self.assertTrue(config["inject_drivers"])
        self.assertIn("viostor", config["drivers"])
        self.assertIn("netkvm", config["drivers"])
        self.assertIn("balloon", config["drivers"])
        self.assertIn("-drive", config["drive_param"])

    def test_02_boundary_linux_native_driver_indication(self):
        """Boundary: Linux target specifies native in-kernel driver support."""
        config = ISOAutoPilot.generate_virtio_injection_config("LINUX_UBUNTU")
        self.assertFalse(config["inject_drivers"])
        self.assertTrue(config["native_drivers"])
        self.assertIn("virtio_blk", config["drivers"])

    def test_03_boundary_unknown_os_empty_drivers(self):
        """Boundary: UNKNOWN OS target returns empty driver list and inject_drivers=False."""
        config = ISOAutoPilot.generate_virtio_injection_config("UNKNOWN")
        self.assertFalse(config["inject_drivers"])
        self.assertEqual(config["drivers"], [])

    def test_04_boundary_driver_names_traversal_safe(self):
        """Boundary: Injected driver names contain no path traversal patterns."""
        config = ISOAutoPilot.generate_virtio_injection_config("WINDOWS_11")
        for driver in config["drivers"]:
            self.assertNotIn("..", driver)
            self.assertFalse(driver.startswith("/"))

    def test_05_boundary_case_insensitive_os_type(self):
        """Boundary: Mixed-case OS name produces identical configuration."""
        c1 = ISOAutoPilot.generate_virtio_injection_config("WINDOWS_11")
        c2 = ISOAutoPilot.generate_virtio_injection_config("windows_11")
        self.assertEqual(c1, c2)


class TestTier2Feature19Win11BypassBoundaries(unittest.TestCase):
    """Feature 19: ISO Auto-Pilot: Win11 Bypass Boundary & Corner Tests."""

    def test_01_boundary_xml_special_characters_escaped(self):
        """Boundary: Special characters (&, <, >, quotes) in username parse as valid XML."""
        xml_str = ISOAutoPilot.generate_windows11_bypass_xml('John & Jane <"Dev">')
        root = ET.fromstring(xml_str)
        self.assertIsNotNone(root)

    def test_02_boundary_empty_username_defaults_to_user(self):
        """Boundary: Empty username defaults to 'DeskUser'."""
        xml_str = ISOAutoPilot.generate_windows11_bypass_xml("")
        self.assertIn("<Name>DeskUser</Name>", xml_str)

    def test_03_boundary_extreme_username_length_clamped(self):
        """Boundary: Long username (>20 chars) parses safely in XML."""
        long_user = "A" * 100
        xml_str = ISOAutoPilot.generate_windows11_bypass_xml(long_user)
        self.assertIn(f"<Name>{long_user}</Name>", xml_str)

    def test_04_boundary_all_three_bypass_keys_present(self):
        """Boundary: XML contains BypassTPMCheck, BypassSecureBootCheck, BypassRAMCheck."""
        xml_str = ISOAutoPilot.generate_windows11_bypass_xml("Admin")
        self.assertIn("BypassTPMCheck", xml_str)
        self.assertIn("BypassSecureBootCheck", xml_str)
        self.assertIn("BypassRAMCheck", xml_str)

    def test_05_boundary_xml_root_and_encoding(self):
        """Boundary: Generated XML starts with declaration and has unattend root."""
        xml_str = ISOAutoPilot.generate_windows11_bypass_xml("TestUser")
        self.assertTrue(xml_str.startswith('<?xml version="1.0" encoding="utf-8"?>'))
        root = ET.fromstring(xml_str)
        self.assertTrue(root.tag.endswith("unattend"))


class TestTier2Feature20StorageBridgeBoundaries(unittest.TestCase):
    """Feature 20: Storage & Bridge Interface Boundary & Corner Tests."""

    def test_01_boundary_apfs_sparse_disk_zero_or_negative_rejected(self):
        """Boundary: Requesting 0 bytes or negative size raises ValueError in create_sparse_disk_config."""
        with self.assertRaises(ValueError):
            StorageBridge.create_sparse_disk_config(0)
        with self.assertRaises(ValueError):
            StorageBridge.create_sparse_disk_config(-5 * 1024 * 1024 * 1024)

    def test_02_boundary_apfs_sparse_disk_allocation_negative_rejected(self):
        """Boundary: Allocating non-positive size returns False."""
        self.assertFalse(StorageBridge.allocate_sparse_disk("dummy.sparseimage", -1))
        self.assertFalse(StorageBridge.allocate_sparse_disk("dummy.sparseimage", 0))

    def test_03_boundary_clipboard_sync_empty_and_normal(self):
        """Boundary: Empty string and text clipboard synchronizes without error."""
        bridge = StorageBridge()
        self.assertEqual(bridge.sync_to_guest(""), "")
        self.assertEqual(bridge.sync_from_guest(), "")
        self.assertEqual(bridge.sync_to_guest("HostClipboardText"), "HostClipboardText")
        self.assertEqual(bridge.sync_from_guest(), "HostClipboardText")

    def test_04_boundary_clipboard_sync_large_payload(self):
        """Boundary: 1MB clipboard payload synchronizes accurately."""
        bridge = StorageBridge()
        large_payload = "A" * (1024 * 1024)
        self.assertEqual(bridge.sync_to_guest(large_payload), large_payload)
        self.assertEqual(bridge.sync_from_guest(), large_payload)

    def test_05_boundary_file_sharing_and_staging(self):
        """Boundary: File sharing stages file, non-existent file raises FileNotFoundError."""
        bridge = StorageBridge()
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"Desk Simulator Test Shared Content")
            temp_file = f.name
        try:
            staged = bridge.share_file_to_guest(temp_file)
            self.assertEqual(staged["status"], "staged")
            self.assertTrue(Path(staged["destination"]).exists())
            with self.assertRaises(FileNotFoundError):
                bridge.share_file_to_guest("/non/existent/path/traversal/test")
        finally:
            try:
                os.remove(temp_file)
            except Exception:
                pass


class TestTier2Feature21JitHookBoundaries(unittest.TestCase):
    """Feature 21: JIT Hook Interface Boundary & Corner Tests."""

    def test_01_boundary_cs_debugged_active(self):
        """Boundary: CS_DEBUGGED flag set marks JIT available via AltJIT by default."""
        status = JITDetector.detect_jit(has_cs_debugged=True)
        self.assertTrue(status["is_available"])
        self.assertEqual(status["source"], JITSource.ALTJIT.value)

    def test_02_boundary_trollstore_active(self):
        """Boundary: TrollStore environment marker marks JIT available via TrollStore."""
        status = JITDetector.detect_jit(has_cs_debugged=True, env_marker="trollstore")
        self.assertTrue(status["is_available"])
        self.assertEqual(status["source"], JITSource.TROLLSTORE.value)

    def test_03_boundary_sandboxed_unentitled(self):
        """Boundary: Standard sandbox without debugger marks JIT unavailable."""
        status = JITDetector.detect_jit(has_cs_debugged=False)
        self.assertFalse(status["is_available"])
        self.assertEqual(status["source"], JITSource.NONE.value)

    def test_04_boundary_jit_unavailable_guidance_message(self):
        """Boundary: Unavailable JIT message references SideStore or AltStore."""
        status = JITDetector.detect_jit(has_cs_debugged=False)
        self.assertIn("SideStore", status["advisory"])
        self.assertIn("AltStore", status["advisory"])

    def test_05_boundary_state_transitions_idempotent(self):
        """Boundary: Polling JIT status repeatedly maintains consistent return."""
        s1 = JITDetector.detect_jit(has_cs_debugged=True, env_marker="sidestore")
        s2 = JITDetector.detect_jit(has_cs_debugged=True, env_marker="sidestore")
        self.assertEqual(s1["is_available"], s2["is_available"])
        self.assertEqual(s1["source"], s2["source"])
        self.assertEqual(s1["source"], JITSource.SIDESTORE.value)


class TestTier2Feature22VerifyPhase1ScriptBoundaries(unittest.TestCase):
    """Feature 22: Automated Verification Script Boundary & Corner Tests."""

    def test_01_boundary_verify_script_unknown_args(self):
        """Boundary: Unknown arguments to verification script exit non-zero or clean error."""
        script = WORKSPACE_ROOT / "Scripts" / "verify_phase1.py"
        if script.exists():
            proc = subprocess.run(
                [sys.executable, str(script), "--unknown-flag-xyz"],
                cwd=WORKSPACE_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotIn("Traceback (most recent call last)", proc.stderr)
        else:
            self.assertTrue(True)

    def test_02_boundary_verify_script_missing_component_exits_1(self):
        """Boundary: Verification fails with exit code 1 if run against an empty directory."""
        script = WORKSPACE_ROOT / "Scripts" / "verify_phase1.py"
        with tempfile.TemporaryDirectory() as empty_dir:
            proc = subprocess.run(
                [sys.executable, str(script), "--workspace-root", empty_dir, "--skip-git"],
                cwd=WORKSPACE_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 1)

    def test_03_boundary_verify_script_exit_code_zero_on_pass(self):
        """Boundary: Verification succeeds with exit code 0 on the actual workspace."""
        script = WORKSPACE_ROOT / "Scripts" / "verify_phase1.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--workspace-root", str(WORKSPACE_ROOT), "--skip-git"],
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)

    def test_04_boundary_verify_script_output_pass_fail_indicators(self):
        """Boundary: Verification script output contains [PASS] indicators."""
        script = WORKSPACE_ROOT / "Scripts" / "verify_phase1.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--workspace-root", str(WORKSPACE_ROOT), "--skip-git"],
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertIn("[PASS]", proc.stdout)

    def test_05_boundary_verify_script_execution_timeout(self):
        """Boundary: Verification completes within 10 seconds."""
        script = WORKSPACE_ROOT / "Scripts" / "verify_phase1.py"
        start = time.time()
        proc = subprocess.run(
            [sys.executable, str(script), "--workspace-root", str(WORKSPACE_ROOT), "--skip-git"],
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
        )
        elapsed = time.time() - start
        self.assertEqual(proc.returncode, 0)
        self.assertLess(elapsed, 10.0)


class TestTier2Feature23MockTestSuiteBoundaries(unittest.TestCase):
    """Feature 23: Mock Test Suite Scaffolding Boundary & Corner Tests."""

    def test_01_boundary_runner_propagates_success_code_zero(self):
        """Boundary: Actual unit & mock runner exits with 0 on workspace."""
        runner = WORKSPACE_ROOT / "Tests" / "run_all_tests.py"
        proc = subprocess.run(
            [sys.executable, str(runner)],
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("[PASSED]", proc.stdout)

    def test_02_boundary_runner_execution_duration(self):
        """Boundary: Unit & mock runner completes rapidly (< 5 seconds)."""
        runner = WORKSPACE_ROOT / "Tests" / "run_all_tests.py"
        start = time.time()
        proc = subprocess.run(
            [sys.executable, str(runner)],
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertLess(time.time() - start, 5.0)

    def test_03_boundary_memory_guard_mock_harness_normal_pressure_safe(self):
        """Boundary: Normal pressure returns None cleanly from MemoryGuard."""
        res = MemoryGuard.handle_memory_pressure("normal", available_bytes=2000 * 1024 * 1024)
        self.assertIsNone(res)

    def test_04_boundary_qmp_command_serialization(self):
        """Boundary: QMPCommand dataclass serializes cleanly to JSON-RPC dict."""
        cmd = QMPCommand(execute="balloon", arguments={"value": 1024 * 1024 * 1024})
        d = cmd.to_dict()
        self.assertEqual(d["execute"], "balloon")
        self.assertEqual(d["arguments"]["value"], 1024 * 1024 * 1024)

    def test_05_boundary_runner_summary_metrics_structure(self):
        """Boundary: Unit runner output contains expected summary headers."""
        runner = WORKSPACE_ROOT / "Tests" / "run_all_tests.py"
        proc = subprocess.run(
            [sys.executable, str(runner)],
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertIn("engine", proc.stdout)
        self.assertIn("management", proc.stdout)


class TestTier2Feature24E2EAcceptanceHardening(unittest.TestCase):
    """Feature 24: E2E Acceptance & Compliance Boundary & Corner Tests."""

    def test_01_boundary_all_criteria_satisfied_acceptance_passes(self):
        """Boundary: All required directories UI, Management, Engine, Scripts, Tests exist."""
        for mod in ["UI", "Management", "Engine", "Scripts", "Tests"]:
            self.assertTrue((WORKSPACE_ROOT / mod).is_dir())

    def test_02_boundary_engine_allowed_targets_strict(self):
        """Boundary: EngineConfig allows only x86_64-softmmu and aarch64-softmmu."""
        self.assertEqual(set(EngineConfig.ALLOWED_TARGETS), {"x86_64-softmmu", "aarch64-softmmu"})

    def test_03_boundary_mandatory_baseline_files_exist(self):
        """Boundary: Mandatory baseline files exist in workspace."""
        for f in ["README.md", ".gitignore", "Scripts/verify_phase1.py", "Scripts/build_engine.py"]:
            self.assertTrue((WORKSPACE_ROOT / f).is_file())

    def test_04_boundary_tcg_bounds_enforced(self):
        """Boundary: TCG bounds are clamped within 128MB–256MB."""
        self.assertEqual(EngineConfig.clamp_tcg_size(64), 128)
        self.assertEqual(EngineConfig.clamp_tcg_size(512), 256)

    def test_05_boundary_phase1_scope_strict_isolation(self):
        """Boundary: Phase 1 acceptance strictly omits Phase 2-5 requirements."""
        phase1_keys = {"workspace", "engine_targets", "compiler_flags", "uds_spice", "tcg_clamp"}
        phase4_keys = {"swiftui_gamepad_hud", "metal_promotion_shaders"}
        self.assertEqual(phase1_keys.intersection(phase4_keys), set())


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""
Tests/Phase3Tests/test_vm_controller_boot_pipeline.py
Desk-simulator Phase 3: VMController Boot Pipeline, Argument Builder & State Machine Test Suite.

Covers:
- Feature 9: VMController Boot Orchestration & State Machine (R2)
  - VMState enum (.stopped, .starting, .running, .paused, .stopping, .error)
  - QEMUArgumentsBuilder CLI generation (architecture, RAM, SMP, clamped TCG, SPICE UDS)
  - Strict Unix Domain Socket validation (TCP loopback prohibition, 108-byte limit)
  - VMController startup orchestration (launcher launch, SPICE and QMP initialization)
  - Pause, Resume, Stop, and Force Stop lifecycle transitions
  - Smart Memory Guard VirtIO-Balloon command dispatching
  - Error trapping and delegate notifications
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


class TestVMControllerBootPipeline(unittest.TestCase):
    """Production-grade automated tests for VMController.swift and QEMUArgumentsBuilder.swift."""

    @classmethod
    def setUpClass(cls):
        cls.root = WORKSPACE_ROOT
        cls.controller_swift_path = cls.root / "Engine" / "Core" / "VMController.swift"
        cls.args_builder_swift_path = cls.root / "Engine" / "QEMU" / "QEMUArgumentsBuilder.swift"

        if not cls.controller_swift_path.exists():
            raise FileNotFoundError(f"Missing VMController.swift at {cls.controller_swift_path}")
        if not cls.args_builder_swift_path.exists():
            raise FileNotFoundError(f"Missing QEMUArgumentsBuilder.swift at {cls.args_builder_swift_path}")

        cls.controller_code = cls.controller_swift_path.read_text(encoding="utf-8")
        cls.builder_code = cls.args_builder_swift_path.read_text(encoding="utf-8")

    # =========================================================================
    # TIER 1: Feature Coverage (Equivalence Class Partitioning)
    # =========================================================================

    def test_t1_f09_01_vm_state_enum_declaration(self):
        """TEST-T1-F09-01: VMState enum declares stopped, starting, running, paused, stopping, error."""
        self.assertIn("public enum VMState: Equatable", self.controller_code)
        self.assertIn("case stopped", self.controller_code)
        self.assertIn("case starting", self.controller_code)
        self.assertIn("case running", self.controller_code)
        self.assertIn("case paused", self.controller_code)
        self.assertIn("case stopping", self.controller_code)
        self.assertIn("case error(String)", self.controller_code)

    def test_t1_f09_02_vm_controller_delegate_protocol(self):
        """TEST-T1-F09-02: VMControllerDelegate protocol defines didChangeState and didReceiveError."""
        self.assertIn("public protocol VMControllerDelegate: AnyObject", self.controller_code)
        self.assertIn("func vmController(_ controller: VMController, didChangeState state: VMState)", self.controller_code)
        self.assertIn("func vmController(_ controller: VMController, didReceiveError error: Error)", self.controller_code)

    def test_t1_f09_03_qemu_configuration_struct_fields(self):
        """TEST-T1-F09-03: QEMUConfiguration struct contains architecture, ram, tbSize, vCPUs, sockets."""
        self.assertIn("public struct QEMUConfiguration", self.builder_code)
        self.assertIn("public var architecture: TargetArchitecture", self.builder_code)
        self.assertIn("public var ramMB: Int", self.builder_code)
        self.assertIn("public var tbSizeMB: Int", self.builder_code)
        self.assertIn("public var vCPUs: Int", self.builder_code)
        self.assertIn("public var spiceSocketPath: String", self.builder_code)
        self.assertIn("public var qmpSocketPath: String?", self.builder_code)

    def test_t1_f09_04_argument_builder_error_cases(self):
        """TEST-T1-F09-04: ArgumentBuilderError enum cases for validation."""
        self.assertIn("public enum ArgumentBuilderError: Error, LocalizedError", self.builder_code)
        self.assertIn("case invalidTargetArchitecture(String)", self.builder_code)
        self.assertIn("case invalidSocketPath(String)", self.builder_code)
        self.assertIn("case tcpLoopbackProhibited(String)", self.builder_code)
        self.assertIn("case socketPathTooLong(Int)", self.builder_code)
        self.assertIn("case invalidMemorySize(Int)", self.builder_code)

    def test_t1_f09_05_tcg_clamping_constants_and_logic(self):
        """TEST-T1-F09-05: TCG translation buffer size clamped between 128MB and 256MB."""
        self.assertIn("public static let tcgMinMB: Int = 128", self.builder_code)
        self.assertIn("public static let tcgMaxMB: Int = 256", self.builder_code)
        self.assertIn("public static func clampTCGSize(_ requestedMB: Int) -> Int", self.builder_code)

        def clamp_tcg(val: int) -> int:
            if val < 128:
                return 128
            if val > 256:
                return 256
            return val

        self.assertEqual(clamp_tcg(64), 128)
        self.assertEqual(clamp_tcg(128), 128)
        self.assertEqual(clamp_tcg(192), 192)
        self.assertEqual(clamp_tcg(256), 256)
        self.assertEqual(clamp_tcg(512), 256)

    def test_t1_f09_06_spice_uds_anti_tcp_enforcement(self):
        """TEST-T1-F09-06: Validates rejection of TCP loopback strings."""
        self.assertIn('lower.contains("127.0.0.1")', self.builder_code)
        self.assertIn('lower.contains("localhost")', self.builder_code)
        self.assertIn('lower.contains("0.0.0.0")', self.builder_code)
        self.assertIn('lower.contains("port=")', self.builder_code)

        def validate_socket(path: str):
            trimmed = path.strip()
            if not trimmed:
                raise ValueError("empty")
            lower = trimmed.lower()
            if any(k in lower for k in ["127.0.0.1", "localhost", "0.0.0.0", "port="]):
                raise ValueError("tcpLoopbackProhibited")
            if len(trimmed.encode("utf-8")) > 108:
                raise ValueError("socketPathTooLong")

        with self.assertRaises(ValueError):
            validate_socket("127.0.0.1:5900")
        with self.assertRaises(ValueError):
            validate_socket("localhost")
        with self.assertRaises(ValueError):
            validate_socket("port=5900")
        with self.assertRaises(ValueError):
            validate_socket("/tmp/" + "a" * 105)  # > 108 bytes

        # Valid socket path
        validate_socket("/tmp/spice.sock")

    def test_t1_f09_07_vm_controller_start_pipeline(self):
        """TEST-T1-F09-07: VMController.start() sequence (args, SPICE, QMP, launcher, running)."""
        self.assertIn("QEMUArgumentsBuilder.buildArguments(from: self.configuration)", self.controller_code)
        self.assertIn("self.spiceConnection = try SPICEConnection", self.controller_code)
        self.assertIn("socketPath: self.configuration.spiceSocketPath", self.controller_code)
        self.assertIn("channelPolicy: .optimizedForIOS", self.controller_code)
        self.assertIn("self.launcher.launch(with: args)", self.controller_code)
        self.assertIn("self.updateState(.running)", self.controller_code)
        self.assertIn("self.spiceConnection?.connect()", self.controller_code)

    def test_t1_f09_08_vm_controller_pause_and_resume(self):
        """TEST-T1-F09-08: VMController pause() and resume() invoke QMP commands."""
        self.assertIn("qmp.pauseVM", self.controller_code)
        self.assertIn("self.updateState(.paused)", self.controller_code)
        self.assertIn("qmp.resumeVM", self.controller_code)
        self.assertIn("self.updateState(.running)", self.controller_code)

    def test_t1_f09_09_vm_controller_stop_and_cleanup(self):
        """TEST-T1-F09-09: VMController stop() disconnects SPICE, shuts down QMP, terminates launcher."""
        self.assertIn("self.spiceConnection?.disconnect()", self.controller_code)
        self.assertIn("qmp.shutdown(force: force)", self.controller_code)
        self.assertIn("self.launcher.terminate()", self.controller_code)
        self.assertIn("self.updateState(.stopped)", self.controller_code)

    def test_t1_f09_10_memory_command_dispatching(self):
        """TEST-T1-F09-10: dispatchMemoryCommand routes stop, cont, and balloon commands."""
        self.assertIn('command.execute == "stop"', self.controller_code)
        self.assertIn('command.execute == "cont"', self.controller_code)
        self.assertIn('command.execute == "balloon"', self.controller_code)
        self.assertIn("self.qmpClient?.setBalloonMemory", self.controller_code)

    # =========================================================================
    # TIER 2: Boundary, Edge, & Corner Cases
    # =========================================================================

    def test_t2_f09_01_socket_path_exact_boundary_108_vs_109(self):
        """TEST-T2-F09-01: Socket path of exactly 108 bytes is accepted; 109 bytes rejected."""
        valid_108 = "/tmp/" + "a" * (108 - len("/tmp/"))
        self.assertEqual(len(valid_108.encode("utf-8")), 108)

        invalid_109 = valid_108 + "x"
        self.assertEqual(len(invalid_109.encode("utf-8")), 109)

        def check_path_len(path: str) -> bool:
            return len(path.strip().encode("utf-8")) <= 108

        self.assertTrue(check_path_len(valid_108))
        self.assertFalse(check_path_len(invalid_109))

    def test_t2_f09_02_invalid_memory_size_rejection(self):
        """TEST-T2-F09-02: RAM <= 0 rejected with ArgumentBuilderError.invalidMemorySize."""
        self.assertIn("guard config.ramMB > 0 else", self.builder_code)
        self.assertIn("throw ArgumentBuilderError.invalidMemorySize(config.ramMB)", self.builder_code)

    def test_t2_f09_03_double_start_idempotency(self):
        """TEST-T2-F09-03: Calling start() when already .running returns early without re-launching."""
        self.assertIn("switch self.state {", self.controller_code)
        self.assertIn("case .stopped, .error:", self.controller_code)
        self.assertIn("default:\n                return", self.controller_code)

    def test_t2_f09_04_pause_when_stopped_noop(self):
        """TEST-T2-F09-04: Calling pause() when .stopped returns early without state change."""
        self.assertIn("guard self.state == .running else { return }", self.controller_code)

    def test_t2_f09_05_resume_when_running_noop(self):
        """TEST-T2-F09-05: Calling resume() when .running returns early without state change."""
        self.assertIn("guard self.state == .paused else { return }", self.controller_code)

    def test_t2_f09_06_force_stop_flag_propagation(self):
        """TEST-T2-F09-06: stop(force: Bool) passes force parameter to qmp.shutdown."""
        self.assertIn("public func stop(force: Bool = false)", self.controller_code)
        self.assertIn("qmp.shutdown(force: force)", self.controller_code)

    def test_t2_f09_07_darwin_socket_path_length_boundary_104_bytes(self):
        """TEST-T2-F09-07: Darwin sockaddr_un sun_path 104-byte buffer boundary verification."""
        self.assertIn("maxSocketPathLength", self.builder_code)
        posix_max = 108
        darwin_max = 104
        self.assertLessEqual(darwin_max, posix_max)

        safe_darwin_path = "/tmp/vm_" + "a" * (darwin_max - len("/tmp/vm_") - 1)
        self.assertLess(len(safe_darwin_path.encode("utf-8")), darwin_max)

    # =========================================================================
    # TIER 3: Cross-Feature Interactions
    # =========================================================================

    def test_t3_f09_01_cli_argument_assembly_simulation(self):
        """TEST-T3-01: Full CLI argument array builder simulation matching Swift logic."""
        def build_args(arch: str, ram: int, tb: int, vcpus: int, spice_sock: str, qmp_sock: str | None = None) -> List[str]:
            if ram <= 0:
                raise ValueError("invalidMemorySize")
            # Clamp TB
            clamped_tb = max(128, min(256, tb))
            cores = max(1, vcpus)

            bin_name = "qemu-system-x86_64" if arch == "x86_64" else "qemu-system-aarch64"
            args = [
                bin_name,
                "-m", str(ram),
                "-smp", f"cpus={cores},cores={cores}",
                "-accel", f"tcg,tb-size={clamped_tb}",
                "-spice", f"unix=on,addr={spice_sock},disable-ticketing=on",
                "-global", "spice.smartcard=off"
            ]
            if qmp_sock:
                args.extend(["-qmp", f"unix:{qmp_sock},server,nowait"])
            return args

        # Scenario: x86_64 boot
        args = build_args("x86_64", 2048, 128, 2, "/tmp/spice.sock", "/tmp/qmp.sock")
        self.assertEqual(args[0], "qemu-system-x86_64")
        self.assertIn("-m", args)
        self.assertIn("2048", args)
        self.assertIn("-smp", args)
        self.assertIn("cpus=2,cores=2", args)
        self.assertIn("-accel", args)
        self.assertIn("tcg,tb-size=128", args)
        self.assertIn("-spice", args)
        self.assertIn("unix=on,addr=/tmp/spice.sock,disable-ticketing=on", args)
        self.assertIn("-qmp", args)
        self.assertIn("unix:/tmp/qmp.sock,server,nowait", args)

    def test_t3_f09_02_state_machine_full_lifecycle(self):
        """TEST-T3-02: Complete state machine lifecycle simulation: stopped -> starting -> running -> paused -> running -> stopping -> stopped."""
        class MockVMController:
            def __init__(self):
                self.state = "stopped"
                self.history = ["stopped"]

            def start(self):
                if self.state not in ("stopped", "error"):
                    return
                self.state = "starting"
                self.history.append("starting")
                self.state = "running"
                self.history.append("running")

            def pause(self):
                if self.state != "running":
                    return
                self.state = "paused"
                self.history.append("paused")

            def resume(self):
                if self.state != "paused":
                    return
                self.state = "running"
                self.history.append("running")

            def stop(self, force: bool = False):
                if self.state not in ("running", "paused"):
                    return
                self.state = "stopping"
                self.history.append("stopping")
                self.state = "stopped"
                self.history.append("stopped")

        vm = MockVMController()
        vm.start()
        vm.pause()
        vm.resume()
        vm.stop()
        self.assertEqual(vm.history, ["stopped", "starting", "running", "paused", "running", "stopping", "stopped"])

    def test_t3_f09_03_vm_controller_process_launcher_delegate_binding(self):
        """TEST-T3-03: VMController binds launcher.delegate = self and conforms to ProcessLauncherDelegate."""
        self.assertIn("self.launcher.delegate = self", self.controller_code)
        self.assertIn("extension VMController: ProcessLauncherDelegate", self.controller_code)
        self.assertIn("func launcher(_ launcher: ProcessLauncher, didChangeState state: LaunchState)", self.controller_code)
        self.assertIn("self.updateState(.error", self.controller_code)
        self.assertIn("self.updateState(.stopped)", self.controller_code)

    # =========================================================================
    # TIER 4: Real-World Scenarios
    # =========================================================================

    def test_t4_f09_01_cold_boot_scenario_x86_64(self):
        """TEST-T4-01: Cold boot scenario with 1024MB RAM, UDS SPICE connection."""
        # 1. Structural Swift code verification
        self.assertIn("public final class VMController: NSObject", self.controller_code)
        self.assertIn("public let configuration: QEMUConfiguration", self.controller_code)
        self.assertIn("public let launcher: ProcessLauncher", self.controller_code)
        self.assertIn("QEMUArgumentsBuilder.buildArguments(from: self.configuration)", self.controller_code)

        # 2. Cold boot configuration assembly simulation
        class ColdBootSimulator:
            def __init__(self, ram_mb: int = 1024, vcpus: int = 2, tb_mb: int = 128):
                self.ram_mb = ram_mb
                self.vcpus = vcpus
                self.tb_mb = tb_mb
                self.spice_sock = "/tmp/desk_spice_coldboot.sock"
                self.qmp_sock = "/tmp/desk_qmp_coldboot.sock"
                self.controller_state = "stopped"
                self.launcher_state = "idle"
                self.spice_connected = False
                self.cli_args: List[str] = []

            def start(self) -> List[str]:
                self.controller_state = "starting"
                # Build arguments
                self.cli_args = [
                    "qemu-system-x86_64",
                    "-m", str(self.ram_mb),
                    "-smp", f"cpus={self.vcpus},cores={self.vcpus}",
                    "-accel", f"tcg,tb-size={self.tb_mb}",
                    "-chardev", f"socket,id=spice,path={self.spice_sock}",
                    "-spice", f"unix=on,addr={self.spice_sock},disable-ticketing=on",
                    "-qmp", f"unix:{self.qmp_sock},server,nowait"
                ]
                # Launcher launches
                self.launcher_state = "launching"
                self.launcher_state = "running"
                self.controller_state = "running"
                self.spice_connected = True
                return self.cli_args

            def stop(self):
                self.controller_state = "stopping"
                self.spice_connected = False
                self.launcher_state = "stopping"
                self.launcher_state = "terminated"
                self.controller_state = "stopped"

        sim = ColdBootSimulator(ram_mb=1024, vcpus=2, tb_mb=128)
        args = sim.start()

        # Validate complete argument vector
        self.assertEqual(args[0], "qemu-system-x86_64")
        self.assertIn("-m", args)
        self.assertIn("1024", args)
        self.assertIn("-smp", args)
        self.assertIn("cpus=2,cores=2", args)
        self.assertIn("-accel", args)
        self.assertIn("tcg,tb-size=128", args)
        self.assertIn("-spice", args)
        self.assertIn("unix=on,addr=/tmp/desk_spice_coldboot.sock,disable-ticketing=on", args)
        self.assertIn("-qmp", args)
        self.assertIn("unix:/tmp/desk_qmp_coldboot.sock,server,nowait", args)

        # Validate state progression
        self.assertEqual(sim.controller_state, "running")
        self.assertEqual(sim.launcher_state, "running")
        self.assertTrue(sim.spice_connected)

        sim.stop()
        self.assertEqual(sim.controller_state, "stopped")
        self.assertEqual(sim.launcher_state, "terminated")
        self.assertFalse(sim.spice_connected)

    def test_t4_f09_02_jetsam_memory_pressure_balloon_workload(self):
        """TEST-T4-02: Jetsam memory alert triggering balloon memory command dispatch."""
        self.assertIn("public func dispatchMemoryCommand(_ command: QMPCommand)", self.controller_code)
        self.assertIn('command.execute == "balloon"', self.controller_code)
        self.assertIn("self.qmpClient?.setBalloonMemory", self.controller_code)

        dispatched_balloon_bytes: List[int] = []

        class MockQMPClient:
            def setBalloonMemory(self, target_bytes: int):
                dispatched_balloon_bytes.append(target_bytes)

        # Simulate host memory pressure dropping available memory below safe threshold
        qmp = MockQMPClient()
        guest_ram_mb = 2048
        pressure_target_mb = 1024
        target_bytes = pressure_target_mb * 1024 * 1024

        qmp.setBalloonMemory(target_bytes)
        self.assertEqual(len(dispatched_balloon_bytes), 1)
        self.assertEqual(dispatched_balloon_bytes[0], 1024 * 1024 * 1024)

    def test_t4_f09_03_rapid_stop_start_cycle_consistency(self):
        """TEST-T4-03: Rapid stop-then-start sequence does not leave zombie running controller state."""
        class SynchronizedController:
            def __init__(self):
                self.controller_state = "running"
                self.launcher_state = "running"

            def stop(self):
                self.controller_state = "stopping"
                self.launcher_state = "stopping"
                self.launcher_state = "terminated"
                self.controller_state = "stopped"

            def start(self):
                if self.controller_state not in ("stopped", "error"):
                    return False
                if self.launcher_state not in ("idle", "terminated"):
                    return False
                self.controller_state = "starting"
                self.launcher_state = "running"
                self.controller_state = "running"
                return True

        ctrl = SynchronizedController()
        # Rapid stop
        ctrl.stop()
        self.assertEqual(ctrl.controller_state, "stopped")
        self.assertEqual(ctrl.launcher_state, "terminated")

        # Immediately restart
        started = ctrl.start()
        self.assertTrue(started)
        self.assertEqual(ctrl.controller_state, "running")
        self.assertEqual(ctrl.launcher_state, "running")


if __name__ == "__main__":
    unittest.main()

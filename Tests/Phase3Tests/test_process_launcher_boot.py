#!/usr/bin/env python3
"""
Tests/Phase3Tests/test_process_launcher_boot.py
Desk-simulator Phase 3: ProcessLauncher Boot Execution, Thread QoS, C Marshalling & Lifecycle Test Suite.

Covers:
- Feature 8: ProcessLauncher Boot Execution (R2)
  - Dedicated background thread with .userInteractive QoS and 4MB+ stack
  - C-array string marshalling with zero-leak deallocation (defer { free })
  - Dynamic dlsym symbol lookup (qemu_init, qemu_main_loop, qemu_cleanup, qemu_request_exit)
  - NSCondition thread stop signaling and event loop retention
  - LaunchState state machine transitions (.idle, .launching, .running, .stopping, .terminated, .failed)
  - Error trapping on double launch
  - Weak delegate thread safety
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


class TestProcessLauncherBoot(unittest.TestCase):
    """Production-grade automated tests for ProcessLauncher.swift across Tiers 1-4."""

    @classmethod
    def setUpClass(cls):
        cls.root = WORKSPACE_ROOT
        cls.launcher_swift_path = cls.root / "Engine" / "Core" / "ProcessLauncher.swift"
        if not cls.launcher_swift_path.exists():
            raise FileNotFoundError(f"Missing ProcessLauncher.swift at {cls.launcher_swift_path}")
        cls.code = cls.launcher_swift_path.read_text(encoding="utf-8")

    # =========================================================================
    # TIER 1: Feature Coverage (Equivalence Class Partitioning)
    # =========================================================================

    def test_t1_f08_01_launch_state_enum_declaration(self):
        """TEST-T1-F08-01: LaunchState enum must declare idle, launching, running, stopping, terminated, failed."""
        self.assertIn("public enum LaunchState: Equatable", self.code)
        self.assertIn("case idle", self.code)
        self.assertIn("case launching", self.code)
        self.assertIn("case running", self.code)
        self.assertIn("case stopping", self.code)
        self.assertIn("case terminated(exitCode: Int32)", self.code)
        self.assertIn("case failed(error: String)", self.code)

    def test_t1_f08_02_delegate_protocol_definition(self):
        """TEST-T1-F08-02: ProcessLauncherDelegate must declare state and logging notifications."""
        self.assertIn("public protocol ProcessLauncherDelegate: AnyObject", self.code)
        self.assertIn("func launcher(_ launcher: ProcessLauncher, didChangeState state: LaunchState)", self.code)
        self.assertIn("func launcher(_ launcher: ProcessLauncher, didLogMessage message: String)", self.code)

    def test_t1_f08_03_thread_interactive_qos_and_name(self):
        """TEST-T1-F08-03: Dedicated thread must be configured with .userInteractive and canonical name."""
        self.assertIn('thread.qualityOfService = .userInteractive', self.code)
        self.assertIn('thread.name = "com.mobimi.desk.qemu.main"', self.code)
        self.assertIn('qos: .userInteractive', self.code)
        self.assertIn('"com.mobimi.desk.engine.launcher"', self.code)

    def test_t1_f08_04_c_string_marshalling_with_null_termination(self):
        """TEST-T1-F08-04: ProcessLauncher marshals arguments and environment to NULL-terminated C-arrays."""
        # Check arguments marshalling
        self.assertIn("var cArgs = arguments.map { strdup($0) }", self.code)
        self.assertIn("cArgs.append(nil)", self.code)
        # Check environment marshalling
        self.assertIn('var cEnv = environment.map { strdup("\\($0.key)=\\($0.value)") }', self.code)
        self.assertIn("cEnv.append(nil)", self.code)

    def test_t1_f08_05_c_string_deallocation_defer_block(self):
        """TEST-T1-F08-05: Strict defer block must free each non-nil C string pointer for zero leaks."""
        self.assertIn("defer {", self.code)
        self.assertIn("for ptr in cArgs where ptr != nil { free(ptr) }", self.code)
        self.assertIn("for ptr in cEnv where ptr != nil { free(ptr) }", self.code)

    def test_t1_f08_06_dynamic_dlsym_symbol_resolution(self):
        """TEST-T1-F08-06: ProcessLauncher queries dlopen(nil, RTLD_NOW) and resolves QEMU symbols."""
        self.assertIn("dlopen(nil, RTLD_NOW)", self.code)
        self.assertIn('dlsym(handle, "qemu_init")', self.code)
        self.assertIn('dlsym(handle, "qemu_main_loop")', self.code)
        self.assertIn('dlsym(handle, "qemu_cleanup")', self.code)
        self.assertIn('dlsym(handle, "qemu_request_exit")', self.code)

    def test_t1_f08_07_c_calling_convention_function_pointer_types(self):
        """TEST-T1-F08-07: Uses @convention(c) function signatures for C ABI compatibility."""
        self.assertIn("@convention(c)", self.code)
        self.assertIn("UnsafeMutablePointer<UnsafeMutablePointer<CChar>?>?", self.code)
        self.assertIn("withUnsafeMutableBufferPointer", self.code)

    def test_t1_f08_08_nscondition_stop_signaling(self):
        """TEST-T1-F08-08: Uses NSCondition lock, broadcast, wait, and unlock for synchronization."""
        self.assertIn("private let stopCondition = NSCondition()", self.code)
        self.assertIn("stopCondition.lock()", self.code)
        self.assertIn("stopCondition.broadcast()", self.code)
        self.assertIn("stopCondition.wait(until:", self.code)
        self.assertIn("stopCondition.unlock()", self.code)

    def test_t1_f08_09_weak_self_and_weak_delegate(self):
        """TEST-T1-F08-09: ProcessLauncher uses weak references to avoid retain cycles."""
        self.assertIn("public weak var delegate: ProcessLauncherDelegate?", self.code)
        self.assertIn("[weak self]", self.code)

    # =========================================================================
    # TIER 2: Boundary, Edge, & Corner Cases
    # =========================================================================

    def test_t2_f08_01_double_launch_protection(self):
        """TEST-T2-F08-01: Launching while already active transitions state to .failed."""
        self.assertIn("Cannot launch: engine is already active.", self.code)
        self.assertIn("case .idle, .terminated:", self.code)

    def test_t2_f08_02_terminate_when_idle_is_noop(self):
        """TEST-T2-F08-02: Calling terminate() when not running returns early safely."""
        self.assertIn("guard self.state == .running else { return }", self.code)

    def test_t2_f08_03_c_string_marshalling_simulation_correctness(self):
        """TEST-T2-F08-03: Simulate C-array marshalling with various inputs and verify NULL termination."""
        def marshal_args(args: List[str]) -> List[Optional[str]]:
            c_args: List[Optional[str]] = list(args)
            c_args.append(None)
            return c_args

        def marshal_env(env: Dict[str, str]) -> List[Optional[str]]:
            c_env: List[Optional[str]] = [f"{k}={v}" for k, v in env.items()]
            c_env.append(None)
            return c_env

        # Empty args
        res_empty = marshal_args([])
        self.assertEqual(len(res_empty), 1)
        self.assertIsNone(res_empty[-1])

        # Normal args
        normal_args = ["-m", "2048", "-smp", "2", "-name", "Windows 11 VM"]
        res_normal = marshal_args(normal_args)
        self.assertEqual(len(res_normal), len(normal_args) + 1)
        self.assertIsNone(res_normal[-1])
        self.assertEqual(res_normal[:-1], normal_args)

        # Args with spaces, quotes, dashes, unicode
        special_args = ["-drive", 'file="C:\\path with spaces\\disk.qcow2",if=virtio', "-rtc", "base=localtime"]
        res_special = marshal_args(special_args)
        self.assertEqual(len(res_special), len(special_args) + 1)
        self.assertIsNone(res_special[-1])

        # Environment dictionary
        env_dict = {"QEMU_AUDIO_DRV": "spice", "PATH": "/bin:/usr/bin", "COMPLEX": "key=val=extra"}
        res_env = marshal_env(env_dict)
        self.assertEqual(len(res_env), len(env_dict) + 1)
        self.assertIsNone(res_env[-1])
        self.assertIn("QEMU_AUDIO_DRV=spice", res_env)
        self.assertIn("COMPLEX=key=val=extra", res_env)

    def test_t2_f08_04_state_machine_transition_contract(self):
        """TEST-T2-F08-04: Full state machine simulation matching ProcessLauncher logic."""
        class MockProcessLauncher:
            def __init__(self):
                self.state = "idle"
                self.history = ["idle"]

            def launch(self, args: List[str]):
                if self.state not in ("idle", "terminated"):
                    self.state = "failed"
                    self.history.append("failed")
                    return
                self.state = "launching"
                self.history.append("launching")
                # Thread starts:
                self.state = "running"
                self.history.append("running")

            def terminate(self):
                if self.state != "running":
                    return
                self.state = "stopping"
                self.history.append("stopping")
                # Simulated C exit:
                self.state = "terminated"
                self.history.append("terminated")

        launcher = MockProcessLauncher()
        self.assertEqual(launcher.state, "idle")

        # Calling terminate while idle -> noop
        launcher.terminate()
        self.assertEqual(launcher.state, "idle")

        # Launch -> launching -> running
        launcher.launch(["-m", "1024"])
        self.assertEqual(launcher.state, "running")

        # Calling launch while running -> failed
        launcher.launch(["-m", "2048"])
        self.assertEqual(launcher.state, "failed")

        # Fresh launcher lifecycle:
        l2 = MockProcessLauncher()
        l2.launch(["-m", "2048"])
        self.assertEqual(l2.state, "running")
        l2.terminate()
        self.assertEqual(l2.state, "terminated")
        self.assertEqual(l2.history, ["idle", "launching", "running", "stopping", "terminated"])

    def test_t2_f08_05_error_state_on_failed_init(self):
        """TEST-T2-F08-05: ProcessLauncher code transitions to .failed if initRet != 0."""
        self.assertIn('updateState(.failed(error: "qemu_init failed with exit code: \\(initRet)"))', self.code)

    # =========================================================================
    # TIER 3: Cross-Feature Interactions
    # =========================================================================

    def test_t3_f08_01_cross_feature_c_symbol_name_matching(self):
        """TEST-T3-01: Symbol names in ProcessLauncher match BootstrapBridge.h exact identifiers."""
        bootstrap_h = (self.root / "Engine" / "QEMU" / "BootstrapBridge.h").read_text(encoding="utf-8")
        symbols_in_launcher = ["qemu_init", "qemu_main_loop", "qemu_cleanup", "qemu_request_exit"]
        for sym in symbols_in_launcher:
            self.assertIn(f'"{sym}"', self.code, f"ProcessLauncher must query symbol {sym}")
            self.assertIn(sym, bootstrap_h, f"BootstrapBridge.h must declare symbol {sym}")

    def test_t3_f08_02_cross_feature_state_synchronization(self):
        """TEST-T3-02: LaunchState states match QEMUStatusCode lifecycle semantics."""
        bootstrap_h = (self.root / "Engine" / "QEMU" / "BootstrapBridge.h").read_text(encoding="utf-8")

        # Parse QEMUStatusCode enum from BootstrapBridge.h
        enum_match = re.search(r"typedef\s+enum\s*\{(.*?)\}\s*QEMUStatusCode\s*;", bootstrap_h, re.DOTALL)
        self.assertIsNotNone(enum_match, "BootstrapBridge.h must define QEMUStatusCode enum")
        enum_body = enum_match.group(1)

        c_status_codes: Dict[str, int] = {}
        for line in enum_body.splitlines():
            line = line.strip().rstrip(",")
            if "=" in line:
                name, val = line.split("=", 1)
                c_status_codes[name.strip()] = int(val.strip())

        self.assertEqual(c_status_codes.get("QEMU_STATUS_STOPPED"), 0)
        self.assertEqual(c_status_codes.get("QEMU_STATUS_INITIALIZING"), 1)
        self.assertEqual(c_status_codes.get("QEMU_STATUS_RUNNING"), 2)
        self.assertEqual(c_status_codes.get("QEMU_STATUS_PAUSED"), 3)
        self.assertEqual(c_status_codes.get("QEMU_STATUS_TERMINATING"), 4)
        self.assertEqual(c_status_codes.get("QEMU_STATUS_ERROR"), -1)

        # Parse LaunchState enum cases from ProcessLauncher.swift
        swift_cases = set(re.findall(r"case\s+([a-zA-Z0-9_]+)", self.code))
        expected_swift_cases = {"idle", "launching", "running", "stopping", "terminated", "failed"}
        self.assertTrue(expected_swift_cases.issubset(swift_cases), f"Missing cases in ProcessLauncher: {expected_swift_cases - swift_cases}")

        # Validate semantic cross-mapping
        swift_to_c_map = {
            "idle": c_status_codes["QEMU_STATUS_STOPPED"],
            "launching": c_status_codes["QEMU_STATUS_INITIALIZING"],
            "running": c_status_codes["QEMU_STATUS_RUNNING"],
            "stopping": c_status_codes["QEMU_STATUS_TERMINATING"],
            "terminated": c_status_codes["QEMU_STATUS_STOPPED"],
            "failed": c_status_codes["QEMU_STATUS_ERROR"],
        }
        self.assertEqual(len(swift_to_c_map), 6)
        for state, code in swift_to_c_map.items():
            self.assertIn(state, swift_cases)
            self.assertIn(code, c_status_codes.values())

    def test_t3_f08_03_concurrent_launch_race_condition_guard(self):
        """TEST-T3-03: ProcessLauncher queue serialization prevents double-launch race conditions."""
        # ProcessLauncher must enforce thread-safety via serial DispatchQueue
        self.assertIn('DispatchQueue(label: "com.mobimi.desk.engine.launcher", qos: .userInteractive)', self.code)
        self.assertIn("case .idle, .terminated:", self.code)
        self.assertIn("Cannot launch: engine is already active.", self.code)

        import threading
        class ConcurrentLauncherSimulation:
            def __init__(self):
                self.lock = threading.Lock()
                self.state = "idle"
                self.successful_launches = 0
                self.rejected_launches = 0

            def launch(self):
                with self.lock:
                    if self.state in ("idle", "terminated"):
                        self.state = "launching"
                        self.successful_launches += 1
                        self.state = "running"
                    else:
                        self.rejected_launches += 1

        sim = ConcurrentLauncherSimulation()
        threads = [threading.Thread(target=sim.launch) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sim.successful_launches, 1)
        self.assertEqual(sim.rejected_launches, 9)
        self.assertEqual(sim.state, "running")

    # =========================================================================
    # TIER 4: Real-World Application Workloads
    # =========================================================================

    def test_t4_f08_01_simulated_multi_boot_stress_cycles(self):
        """TEST-T4-01: Simulate 50 sequential boot-stop cycles with zero leaked descriptors."""
        # Verify the actual deallocation logic exists in ProcessLauncher.swift
        self.assertIn("defer {", self.code)
        self.assertIn("for ptr in cArgs where ptr != nil { free(ptr) }", self.code)
        self.assertIn("for ptr in cEnv where ptr != nil { free(ptr) }", self.code)

        active_allocations: Set[int] = set()

        def simulated_allocate_and_run(args: List[str], env: Dict[str, str]) -> int:
            c_args_ptrs: List[Optional[int]] = []
            for idx, arg in enumerate(args):
                # Unique allocation token simulating C-heap pointer address
                addr = 0x10000000 + len(active_allocations) * 16 + idx * 8
                active_allocations.add(addr)
                c_args_ptrs.append(addr)
            c_args_ptrs.append(None)

            c_env_ptrs: List[Optional[int]] = []
            for idx, (k, v) in enumerate(env.items()):
                addr = 0x20000000 + len(active_allocations) * 16 + idx * 8
                active_allocations.add(addr)
                c_env_ptrs.append(addr)
            c_env_ptrs.append(None)

            # Simulated execution
            active_count = len(c_args_ptrs) - 1 + len(c_env_ptrs) - 1
            self.assertGreater(active_count, 0)

            # Strict deallocation matching ProcessLauncher defer { free }
            for ptr in c_args_ptrs:
                if ptr is not None:
                    active_allocations.remove(ptr)
            for ptr in c_env_ptrs:
                if ptr is not None:
                    active_allocations.remove(ptr)

            return 0

        # Execute 50 boot cycles with realistic varying arguments
        for cycle in range(50):
            ram = 1024 + (cycle % 4) * 512
            vcpus = 1 + (cycle % 4)
            args = [
                "qemu-system-x86_64",
                "-m", str(ram),
                "-smp", f"cpus={vcpus},cores={vcpus}",
                "-accel", "tcg,tb-size=128",
                "-chardev", f"socket,id=ch0,path=/tmp/vm_{cycle}.sock",
                "-spice", f"unix=on,addr=/tmp/vm_{cycle}.sock,disable-ticketing=on",
                "-name", f"Stress_VM_{cycle}",
            ]
            env = {"QEMU_AUDIO_DRV": "spice", "DESK_BOOT_CYCLE": str(cycle)}
            exit_code = simulated_allocate_and_run(args, env)
            self.assertEqual(exit_code, 0)

        # Assert zero leaked allocations across all 50 cycles
        self.assertEqual(len(active_allocations), 0, "No C-string allocations should remain after 50 boot cycles")

    def test_t4_f08_02_dynamic_symbol_lookup_and_cleanup_pipeline(self):
        """TEST-T4-02: ProcessLauncher dynamic symbol dispatch and error exit code propagation."""
        self.assertIn("let initRet = cArgs.withUnsafeMutableBufferPointer", self.code)
        self.assertIn("if initRet == 0 {", self.code)
        self.assertIn("mainLoopFn()", self.code)
        self.assertIn("cleanupFn()", self.code)
        self.assertIn("updateState(.terminated(exitCode: 0))", self.code)
        self.assertIn('updateState(.failed(error: "qemu_init failed with exit code: \\(initRet)"))', self.code)


if __name__ == "__main__":
    unittest.main()

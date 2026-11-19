#!/usr/bin/env python3
"""
Tests/Phase3Tests/test_phase3_harness_cli.py
Desk-simulator Phase 3: Verification Harness CLI & Test Runner Component Tests.

Covers:
- Feature 17: Phase 3 Verification Harness (Scripts/verify_phase3.py)
  - CLI argument parsing (--workspace-root, --skip-git, --skip-regression, --dry-run, -v/--verbose, --json)
  - Clean error handling on unrecognized flags (StrictArgumentParser exit code 1)
  - Isolated execution of Check 1 through Check 10
  - JSON output schema verification
- Feature 18: Phase 3 Component Test Runner (Tests/Phase3Tests/run_phase3_tests.py)
  - CLI options (-v/--verbose, --failfast, --pattern, --suite)
  - Test discovery across Phase 3 suites
  - ASCII 80-column summary table rendering
  - Exit code and pass/fail semantics
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional

# Workspace root discovery
CANDIDATE_ROOT = Path(__file__).resolve().parent.parent.parent
if (CANDIDATE_ROOT / "Engine").is_dir():
    WORKSPACE_ROOT = CANDIDATE_ROOT
elif (Path.cwd() / "Engine").is_dir():
    WORKSPACE_ROOT = Path.cwd().resolve()
else:
    WORKSPACE_ROOT = Path(r"d:\project nhảm\giả lập").resolve()

if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

# Import target harness modules
import Scripts.verify_phase3 as v3
import Tests.Phase3Tests.run_phase3_tests as r3


class TestVerifyPhase3CliParsing(unittest.TestCase):
    """Unit tests for verify_phase3.py command-line argument parsing and flags."""

    def test_cli_defaults(self):
        """Verifies default argument values when no CLI flags are supplied."""
        args = v3.parse_args([])
        self.assertEqual(Path(args.workspace_root).resolve(), WORKSPACE_ROOT.resolve())
        self.assertFalse(args.skip_git)
        self.assertFalse(args.skip_regression)
        self.assertFalse(args.dry_run)
        self.assertFalse(args.verbose)
        self.assertFalse(args.json)

    def test_cli_workspace_root_custom_path(self):
        """Verifies --workspace-root overrides target root path."""
        custom = Path("/tmp/custom_desk_root").resolve()
        args = v3.parse_args(["--workspace-root", str(custom)])
        self.assertEqual(Path(args.workspace_root).resolve(), custom)

    def test_cli_skip_git_flag(self):
        """Verifies --skip-git sets skip_git to True."""
        args = v3.parse_args(["--skip-git"])
        self.assertTrue(args.skip_git)

    def test_cli_skip_regression_flag(self):
        """Verifies --skip-regression sets skip_regression to True."""
        args = v3.parse_args(["--skip-regression"])
        self.assertTrue(args.skip_regression)

    def test_cli_dry_run_flag(self):
        """Verifies --dry-run sets dry_run to True."""
        args = v3.parse_args(["--dry-run"])
        self.assertTrue(args.dry_run)

    def test_cli_verbose_short_and_long(self):
        """Verifies -v and --verbose both enable verbose logging."""
        args_short = v3.parse_args(["-v"])
        self.assertTrue(args_short.verbose)

        args_long = v3.parse_args(["--verbose"])
        self.assertTrue(args_long.verbose)

    def test_cli_json_flag(self):
        """Verifies --json flag enables structured JSON output mode."""
        args = v3.parse_args(["--json"])
        self.assertTrue(args.json)

    def test_cli_combined_flags(self):
        """Verifies combining multiple flags correctly sets all attributes."""
        args = v3.parse_args(["--skip-git", "--skip-regression", "--dry-run", "--json", "-v"])
        self.assertTrue(args.skip_git)
        self.assertTrue(args.skip_regression)
        self.assertTrue(args.dry_run)
        self.assertTrue(args.json)
        self.assertTrue(args.verbose)

    def test_cli_unrecognized_argument_raises_system_exit(self):
        """Verifies StrictArgumentParser exits with code 1 upon unrecognized flags."""
        with self.assertRaises(SystemExit) as cm:
            v3.parse_args(["--unrecognized-flag-xyz"])
        self.assertEqual(cm.exception.code, 1)

    def test_cli_help_flag_displays_usage(self):
        """Verifies -h and --help display usage without crashing."""
        res = subprocess.run(
            [sys.executable, str(WORKSPACE_ROOT / "Scripts" / "verify_phase3.py"), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("usage:", res.stdout.lower())
        self.assertIn("--workspace-root", res.stdout)
        self.assertIn("--json", res.stdout)


class TestVerifyPhase3CheckFunctionsIsolation(unittest.TestCase):
    """Unit tests for verify_phase3.py individual check functions in isolation."""

    @classmethod
    def setUpClass(cls):
        cls.root = WORKSPACE_ROOT

    def test_check1_engine_linkage_isolated(self):
        """Check 1: Verifies engine linkage, frameworks, search paths, and bridging header."""
        ok, msg = v3.check_engine_linkage_and_search_paths(self.root)
        self.assertTrue(ok, f"Check 1 failed: {msg}")

    def test_check2_c_abi_signatures_isolated(self):
        """Check 2: Verifies 13 C-ABI functions, pthread stack, and spawn hooks."""
        ok, msg = v3.check_native_c_abi_bridge_signatures(self.root)
        self.assertTrue(ok, f"Check 2 failed: {msg}")

    def test_check3_darwin_runtime_probes_isolated(self):
        """Check 3: Verifies Darwin memory probes, csops JIT, and Mach fallbacks."""
        ok, msg = v3.check_darwin_runtime_probes_and_jit(self.root)
        self.assertTrue(ok, f"Check 3 failed: {msg}")

    def test_check4_process_launcher_lifecycle_isolated(self):
        """Check 4: Verifies ProcessLauncher QoS thread, C-marshalling, and lifecycle."""
        ok, msg = v3.check_process_launcher_thread_and_lifecycle(self.root)
        self.assertTrue(ok, f"Check 4 failed: {msg}")

    def test_check5_vm_controller_boot_pipeline_isolated(self):
        """Check 5: Verifies VMController boot pipeline, state machine, and UDS rules."""
        ok, msg = v3.check_vm_controller_boot_pipeline(self.root)
        self.assertTrue(ok, f"Check 5 failed: {msg}")

    def test_check6_spice_display_ingestion_isolated(self):
        """Check 6: Verifies SPICEConnection UDS stream transport and ingestDisplayFrame."""
        ok, msg = v3.check_spice_uds_and_display_ingestion(self.root)
        self.assertTrue(ok, f"Check 6 failed: {msg}")

    def test_check7_metal_rendering_session_isolated(self):
        """Check 7: Verifies Metal framebuffer rendering, 120Hz ProMotion, and session UI."""
        ok, msg = v3.check_metal_rendering_and_ui_session(self.root)
        self.assertTrue(ok, f"Check 7 failed: {msg}")

    def test_check8_packaging_and_ci_isolated(self):
        """Check 8: Verifies dual TrollStore and Sideload schemes and GitHub Actions CI."""
        ok, msg = v3.check_packaging_configurations_and_ci(self.root)
        self.assertTrue(ok, f"Check 8 failed: {msg}")

    def test_check9_component_tests_dry_run_isolated(self):
        """Check 9: Verifies dry-run execution of component test suite check."""
        ok, msg = v3.check_phase3_component_tests(self.root, dry_run=True)
        self.assertTrue(ok)
        self.assertIn("Dry-run", msg)

    def test_check10_zero_regression_skip_and_dry_run_isolated(self):
        """Check 10: Verifies skip_regression and dry_run flags in regression suite check."""
        ok_skip, msg_skip = v3.check_zero_regression_suite(self.root, skip_regression=True)
        self.assertTrue(ok_skip)
        self.assertIn("skipped", msg_skip.lower())

        ok_dry, msg_dry = v3.check_zero_regression_suite(self.root, dry_run=True)
        self.assertTrue(ok_dry)
        self.assertIn("dry-run", msg_dry.lower())

    def test_run_all_phase3_checks_dry_run(self):
        """Verifies run_all_phase3_checks executes all 10 checks and returns structured results."""
        success, results = v3.run_all_phase3_checks(
            self.root,
            skip_git=True,
            skip_regression=True,
            dry_run=True,
        )
        self.assertTrue(success)
        self.assertEqual(len(results), 10)
        for r in results:
            self.assertIn("check", r)
            self.assertIn("success", r)
            self.assertIn("message", r)
            self.assertTrue(r["success"], f"Check failed in dry run: {r['check']}")


class TestRunPhase3TestsCliAndReporting(unittest.TestCase):
    """Unit tests for run_phase3_tests.py CLI options, discovery, and table rendering."""

    def test_runner_cli_defaults(self):
        """Verifies default flags of Phase 3 component test runner."""
        args = r3.parse_args([])
        self.assertEqual(args.verbose, 1)
        self.assertFalse(args.failfast)
        self.assertEqual(args.pattern, "test_*.py")
        self.assertIsNone(args.suite)

    def test_runner_cli_verbose_flag(self):
        """Verifies -v and --verbose increment verbosity count."""
        args1 = r3.parse_args(["-v"])
        self.assertEqual(args1.verbose, 2)
        args2 = r3.parse_args(["-v", "-v"])
        self.assertEqual(args2.verbose, 3)

    def test_runner_cli_failfast_flag(self):
        """Verifies --failfast sets failfast to True."""
        args = r3.parse_args(["--failfast"])
        self.assertTrue(args.failfast)

    def test_runner_cli_pattern_filter(self):
        """Verifies --pattern specifies test filename pattern."""
        args = r3.parse_args(["--pattern", "test_qemu*.py"])
        self.assertEqual(args.pattern, "test_qemu*.py")

    def test_runner_cli_suite_filter(self):
        """Verifies --suite sets suite key filter."""
        args = r3.parse_args(["--suite", "qemu_engine_bridge"])
        self.assertEqual(args.suite, "qemu_engine_bridge")

    def test_runner_suite_registry_completeness(self):
        """Verifies SUITE_REGISTRY has entries for all primary suites."""
        expected_keys = [
            "qemu_engine_bridge",
            "process_launcher_boot",
            "vm_controller_boot_pipeline",
            "spice_display_ingestion",
            "dual_ipa_packaging_config",
            "phase3_swift_symbol_resolution",
        ]
        for k in expected_keys:
            self.assertIn(k, r3.SUITE_REGISTRY)
            self.assertTrue(r3.SUITE_REGISTRY[k]["file"].endswith(".py"))

    def test_runner_ascii_table_rendering_output(self):
        """Verifies print_ascii_table formats 80-column summary table with status tags."""
        dummy_results = [
            r3.SuiteResult("test_suite_alpha", "Suite Alpha", "test_alpha.py"),
            r3.SuiteResult("test_suite_beta", "Suite Beta", "test_beta.py"),
        ]
        dummy_results[0].total = 10
        dummy_results[0].passed = 10
        dummy_results[0].duration = 0.05
        dummy_results[0].status = "PASSED"

        dummy_results[1].total = 5
        dummy_results[1].passed = 5
        dummy_results[1].duration = 0.02
        dummy_results[1].status = "PASSED"

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            success = r3.print_ascii_table(dummy_results, 0.07)

        output = buffer.getvalue()
        self.assertTrue(success)
        self.assertIn("DESK-SIMULATOR PHASE 3 COMPONENT TEST SUMMARY", output)
        self.assertIn("Suite Name", output)
        self.assertIn("Tests", output)
        self.assertIn("Pass", output)
        self.assertIn("Fail", output)
        self.assertIn("Duration", output)
        self.assertIn("Status", output)
        self.assertIn("TOTAL", output)
        self.assertIn("[PASSED]", output)
        self.assertIn("15", output)  # 10 + 5

    def test_runner_ascii_table_failed_status_reporting(self):
        """Verifies print_ascii_table outputs [FAILED] when any suite has failed tests."""
        dummy_results = [
            r3.SuiteResult("test_suite_fail", "Suite Fail", "test_fail.py"),
        ]
        dummy_results[0].total = 5
        dummy_results[0].passed = 4
        dummy_results[0].failed = 1
        dummy_results[0].duration = 0.03
        dummy_results[0].status = "FAILED"

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            success = r3.print_ascii_table(dummy_results, 0.03)

        output = buffer.getvalue()
        self.assertFalse(success)
        self.assertIn("[FAILED]", output)
        self.assertIn("[FAIL]", output)

    def test_runner_discovery_finds_all_modules(self):
        """Verifies Phase 3 directory contains all expected test files."""
        phase3_dir = WORKSPACE_ROOT / "Tests" / "Phase3Tests"
        found = sorted([f.name for f in phase3_dir.glob("test_*.py") if f.is_file()])
        self.assertGreaterEqual(len(found), 7, f"Expected at least 7 test files, found: {found}")
        self.assertIn("test_qemu_engine_bridge.py", found)
        self.assertIn("test_process_launcher_boot.py", found)
        self.assertIn("test_vm_controller_boot_pipeline.py", found)
        self.assertIn("test_spice_display_ingestion.py", found)
        self.assertIn("test_dual_ipa_packaging_config.py", found)
        self.assertIn("test_phase3_swift_symbol_resolution.py", found)
        self.assertIn("test_phase3_harness_cli.py", found)


if __name__ == "__main__":
    unittest.main()

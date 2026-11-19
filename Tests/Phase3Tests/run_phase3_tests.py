#!/usr/bin/env python3
"""
Desk-simulator Phase 3 Component Test Runner.
Discovers and executes all Phase 3 test suites:
- test_qemu_engine_bridge.py (BootstrapBridge C-ABI & Pthread Hooks)
- test_process_launcher_boot.py (ProcessLauncher Boot & Lifecycle)
- test_vm_controller_boot_pipeline.py (VMController Boot Pipeline & State)
- test_spice_display_ingestion.py (SPICE UDS Transport & Metal Display)
- test_dual_ipa_packaging_config.py (Dual IPA Packaging & CI Workflow)
- test_phase3_swift_symbol_resolution.py (Phase 3 Swift Symbol Resolution)

Supports CLI options:
  -v, --verbose: Set output verbosity
  --failfast: Stop on first failure or error
  --pattern: Filter test filenames (default: test_*.py)
  --suite: Filter by test suite name/key

Renders a clean 80-column ASCII status table reporting test suite name, test count,
passes, failures, and execution duration.
Returns exit code 0 on all tests passing, 1 on any failure or error.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

# Workspace root resolution
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE3_DIR = Path(__file__).resolve().parent

if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

# Phase 3 Suite definitions
SUITE_REGISTRY: Dict[str, Dict[str, str]] = {
    "qemu_engine_bridge": {
        "file": "test_qemu_engine_bridge.py",
        "name": "BootstrapBridge C-ABI & Pthreads",
        "description": "Native QEMU bridge, pthread & C-ABI exports",
    },
    "process_launcher_boot": {
        "file": "test_process_launcher_boot.py",
        "name": "ProcessLauncher Boot Pipeline",
        "description": "Dedicated thread QoS, C-marshalling & dlsym",
    },
    "vm_controller_boot_pipeline": {
        "file": "test_vm_controller_boot_pipeline.py",
        "name": "VMController Orchestration",
        "description": "Boot orchestration, arguments & state machine",
    },
    "spice_display_ingestion": {
        "file": "test_spice_display_ingestion.py",
        "name": "SPICE Display & Metal Ingestion",
        "description": "UDS transport, display frame & Metal blit",
    },
    "dual_ipa_packaging_config": {
        "file": "test_dual_ipa_packaging_config.py",
        "name": "Dual IPA Packaging & CI/CD",
        "description": "TrollStore/Sideload schemes, entitlements & CI",
    },
    "phase3_swift_symbol_resolution": {
        "file": "test_phase3_swift_symbol_resolution.py",
        "name": "Swift Symbol Resolution",
        "description": "Static AST member call site resolution",
    },
    "phase3_harness_cli": {
        "file": "test_phase3_harness_cli.py",
        "name": "Phase 3 Harness & Runner CLI",
        "description": "verify_phase3.py & run_phase3_tests.py CLI flags and isolation checks",
    },
}


class SuiteResult:
    """Stores execution metrics for a test suite."""

    def __init__(self, key: str, name: str, file_name: str):
        self.key = key
        self.name = name
        self.file_name = file_name
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors = 0
        self.skipped = 0
        self.duration = 0.0
        self.status = "NOT_RUN"
        self.error_messages: List[str] = []


def discover_and_run_module(
    module_file: str,
    suite_key: str,
    suite_name: str,
    verbosity: int = 1,
    failfast: bool = False,
) -> SuiteResult:
    """Discovers and executes tests in a single test module file."""
    res = SuiteResult(suite_key, suite_name, module_file)
    module_path = PHASE3_DIR / module_file

    if not module_path.is_file():
        res.status = "MISSING"
        res.error_messages.append(f"Module file not found: {module_path}")
        return res

    loader = unittest.TestLoader()
    module_stem = Path(module_file).stem
    module_import = f"Tests.Phase3Tests.{module_stem}"

    try:
        suite = loader.loadTestsFromName(module_import)
    except Exception as exc:
        res.status = "ERROR"
        res.error_messages.append(f"Failed to load module {module_import}: {exc}")
        return res

    res.total = suite.countTestCases()
    if res.total == 0:
        res.status = "EMPTY"
        return res

    runner = unittest.TextTestRunner(
        verbosity=verbosity,
        failfast=failfast,
        stream=sys.stdout,
    )

    if verbosity > 1:
        print(f"\n{'=' * 80}")
        print(f" Executing Suite: {suite_name} ({module_file})")
        print(f"{'=' * 80}")

    start_time = time.time()
    test_result = runner.run(suite)
    res.duration = time.time() - start_time

    res.total = test_result.testsRun
    res.failed = len(test_result.failures)
    res.errors = len(test_result.errors)
    res.skipped = len(test_result.skipped)
    res.passed = res.total - (res.failed + res.errors + res.skipped)

    if res.failed == 0 and res.errors == 0 and res.total > 0:
        res.status = "PASSED"
    else:
        res.status = "FAILED"
        for failure in test_result.failures:
            res.error_messages.append(f"FAILURE in {failure[0]}: {failure[1][:200]}...")
        for error in test_result.errors:
            res.error_messages.append(f"ERROR in {error[0]}: {error[1][:200]}...")

    return res


def print_ascii_table(results: List[SuiteResult], total_duration: float) -> bool:
    """
    Renders a clean 80-column ASCII status table reporting test suite name,
    test count, passes, failures, and execution duration.
    """
    table_width = 80
    print(f"\n\n{'=' * table_width}")
    print(f"{'DESK-SIMULATOR PHASE 3 COMPONENT TEST SUMMARY':^{table_width}}")
    print(f"{'=' * table_width}")
    # Column allocation: 33 + 8 + 8 + 8 + 10 + 13 = 80
    header = f"{'Suite Name':<33}{'Tests':<8}{'Pass':<8}{'Fail':<8}{'Duration':<10}{'Status':<13}"
    print(header)
    print("-" * table_width)

    all_passed = True
    grand_total = 0
    grand_passed = 0
    grand_failed = 0

    for r in results:
        grand_total += r.total
        grand_passed += r.passed
        total_fails = r.failed + r.errors
        grand_failed += total_fails

        if r.status == "PASSED":
            status_tag = "[OK]"
        elif r.status == "FAILED":
            status_tag = "[FAIL]"
            all_passed = False
        elif r.status == "EMPTY":
            status_tag = "[EMPTY]"
            all_passed = False
        else:
            status_tag = "[ERROR]"
            all_passed = False

        duration_str = f"{r.duration:.2f}s"
        name_display = r.key[:31]
        row = f"{name_display:<33}{r.total:<8}{r.passed:<8}{total_fails:<8}{duration_str:<10}{status_tag:<13}"
        print(row)

    print("-" * table_width)
    overall_status = "[PASSED]" if (all_passed and grand_total > 0) else "[FAILED]"
    tot_dur_str = f"{total_duration:.2f}s"
    summary_row = f"{'TOTAL':<33}{grand_total:<8}{grand_passed:<8}{grand_failed:<8}{tot_dur_str:<10}{overall_status:<13}"
    print(summary_row)
    print(f"{'=' * table_width}\n")

    return all_passed and grand_total > 0


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone runner discovering and executing Phase 3 component test suites.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=1,
        help="Increase output verbosity (e.g. -v for detailed test output)",
    )
    parser.add_argument(
        "--failfast",
        action="store_true",
        default=False,
        help="Stop test execution on first failure or error",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="test_*.py",
        help="Glob pattern to filter test module filenames (default: test_*.py)",
    )
    parser.add_argument(
        "--suite",
        type=str,
        default=None,
        help="Optional filter to execute a specific test suite key or filename",
    )
    return parser.parse_args(argv)


def run_phase3_suite(
    pattern: str = "test_*.py",
    suite_filter: Optional[str] = None,
    verbosity: int = 1,
    failfast: bool = False,
) -> bool:
    """Orchestrates test discovery and execution for Phase 3 suites."""
    # Find all test files matching pattern
    all_files = sorted([f.name for f in PHASE3_DIR.glob(pattern) if f.is_file() and f.name.startswith("test_")])

    if not all_files:
        print(f"Error: No test files found matching pattern '{pattern}' in {PHASE3_DIR}", file=sys.stderr)
        return False

    # Filter suites
    selected_suites: List[Tuple[str, str, str]] = []
    for file_name in all_files:
        module_key = Path(file_name).stem
        if module_key.startswith("test_"):
            suite_key = module_key[5:]
        else:
            suite_key = module_key

        entry = SUITE_REGISTRY.get(module_key) or SUITE_REGISTRY.get(suite_key)
        suite_name = entry["name"] if entry else module_key

        if suite_filter:
            sf = suite_filter.lower()
            if (
                sf not in module_key.lower()
                and sf not in suite_key.lower()
                and sf not in file_name.lower()
                and sf not in suite_name.lower()
            ):
                continue

        selected_suites.append((module_key, suite_name, file_name))

    if not selected_suites:
        print(f"Error: No test suites matched filter '{suite_filter}'", file=sys.stderr)
        return False

    results: List[SuiteResult] = []
    overall_start = time.time()

    for mod_key, s_name, f_name in selected_suites:
        res = discover_and_run_module(
            module_file=f_name,
            suite_key=mod_key,
            suite_name=s_name,
            verbosity=verbosity,
            failfast=failfast,
        )
        results.append(res)
        if failfast and res.status != "PASSED":
            break

    total_duration = time.time() - overall_start
    success = print_ascii_table(results, total_duration)

    return success


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    success = run_phase3_suite(
        pattern=args.pattern,
        suite_filter=args.suite,
        verbosity=args.verbose,
        failfast=args.failfast,
    )
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

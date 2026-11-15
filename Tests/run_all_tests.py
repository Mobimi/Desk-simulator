#!/usr/bin/env python3
"""
Desk-simulator Master Unit & Mock Test Runner (Milestone M4)
Discovers and executes all unit and mock test suites:
- Tests/EngineTests (test_engine_config.py)
- Tests/ManagementMocks (test_memory_guard_mock.py, test_iso_autopilot_mock.py, test_pcore_scheduler_mock.py)

CRITICAL: Strictly excludes Tests/E2ETests/ to prevent recursive subprocess execution.
Returns exit code 0 on all tests passing, 1 on any failure.
"""

from __future__ import annotations

import argparse
import sys
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

# Workspace root resolution
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

SUITE_CONFIG = {
    "engine": {
        "name": "Engine Core Configuration & Pruning Tests",
        "path": WORKSPACE_ROOT / "Tests" / "EngineTests",
        "pattern": "test_*.py",
    },
    "management": {
        "name": "Management Layer Mock Test Suite",
        "path": WORKSPACE_ROOT / "Tests" / "ManagementMocks",
        "pattern": "test_*.py",
    },
}


class SuiteExecutionResult:
    """Stores execution metrics and outcome for an individual test suite."""

    def __init__(self, key: str, name: str):
        self.key = key
        self.name = name
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors = 0
        self.skipped = 0
        self.duration = 0.0
        self.status = "NOT_RUN"
        self.message = ""


def discover_and_run_suite(
    suite_key: str,
    verbosity: int = 1,
    failfast: bool = False,
    pattern: str = "test_*.py",
) -> SuiteExecutionResult:
    """
    Discovers and executes tests in a targeted suite directory.
    Explicitly targets only the specific suite path and never discovers Tests/E2ETests/.
    """
    cfg = SUITE_CONFIG[suite_key]
    res = SuiteExecutionResult(suite_key, cfg["name"])
    suite_dir = cfg["path"]

    if not suite_dir.exists():
        res.status = "MISSING"
        res.message = f"Suite directory does not exist: {suite_dir}"
        return res

    loader = unittest.TestLoader()
    try:
        suite = loader.discover(
            start_dir=str(suite_dir),
            pattern=pattern,
            top_level_dir=str(WORKSPACE_ROOT),
        )
    except Exception as exc:
        res.status = "FAILED"
        res.message = f"Failed to discover tests: {exc}"
        return res

    runner = unittest.TextTestRunner(
        verbosity=verbosity,
        failfast=failfast,
        stream=sys.stdout,
    )

    print(f"\n{'=' * 75}")
    print(f" Executing: {cfg['name']} ({suite_key})")
    print(f"{'=' * 75}")

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
    elif res.total == 0:
        res.status = "EMPTY"
    else:
        res.status = "FAILED"

    return res


def compute_summary_dict(results: List[SuiteExecutionResult], total_duration: float) -> Dict[str, Any]:
    """Computes summary metrics dictionary matching required schema."""
    total = sum(r.total for r in results)
    passed = sum(r.passed for r in results)
    failed = sum(r.failed + r.errors for r in results)
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "duration": total_duration,
        "results": results,
    }


def print_summary_table(summary: Dict[str, Any]) -> None:
    """Renders formatted ASCII summary table of test results."""
    table_width = 80
    print(f"\n\n{'=' * table_width}")
    print(f"{'DESK-SIMULATOR UNIT & MOCK TEST SUMMARY':^{table_width}}")
    print(f"{'=' * table_width}")
    header = f"{'Suite':<12}{'Description':<38}{'Total':<8}{'Pass':<8}{'Fail':<8}{'Status':<6}"
    print(header)
    print("-" * table_width)

    all_passed = True
    for r in summary["results"]:
        status_tag = "[OK]" if r.status == "PASSED" else "[FAIL]"
        if r.status != "PASSED":
            all_passed = False
        row = f"{r.key:<12}{r.name:<38}{r.total:<8}{r.passed:<8}{r.failed + r.errors:<8}{status_tag:<6}"
        print(row)

    print("-" * table_width)
    overall_status = "[PASSED]" if (all_passed and summary["total"] > 0) else "[FAILED]"
    summary_row = f"{'TOTAL':<12}{'All Unit & Mock Suites':<38}{summary['total']:<8}{summary['passed']:<8}{summary['failed']:<8}{overall_status:<6}"
    print(summary_row)
    print(f"{'=' * table_width}")
    print(f" Execution Duration: {summary['duration']:.2f} seconds")
    print(f" Final Verdict: {'PASSED (Zero Failures)' if overall_status == '[PASSED]' else 'FAILED'}")
    print(f"{'=' * table_width}\n")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Master Unit & Mock Test Runner for Desk-simulator PC OS Emulator."
    )
    parser.add_argument(
        "--suite",
        type=str,
        default="all",
        choices=["all", "engine", "management"],
        help="Specify test suite to execute: engine, management, or all (default: all)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=1,
        help="Increase output verbosity.",
    )
    parser.add_argument(
        "--failfast",
        action="store_true",
        default=False,
        help="Stop test execution on first failure or error.",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="test_*.py",
        help="File pattern for test discovery (default: test_*.py)",
    )
    return parser.parse_args(argv)


def run_tests(
    suite: str = "all",
    verbosity: int = 1,
    failfast: bool = False,
    pattern: str = "test_*.py",
) -> Tuple[int, Dict[str, Any]]:
    """Programmatic entry point returning (exit_code, summary_dict)."""
    selected_keys = ["engine", "management"] if suite == "all" else [suite]

    print("Starting Desk-simulator Unit & Mock Test Runner...")
    print(f"Workspace Root: {WORKSPACE_ROOT}")
    print(f"Target Suites: {selected_keys}")

    start_time = time.time()
    results: List[SuiteExecutionResult] = []

    for key in selected_keys:
        res = discover_and_run_suite(
            key,
            verbosity=verbosity,
            failfast=failfast,
            pattern=pattern,
        )
        results.append(res)
        if failfast and res.status == "FAILED":
            break

    total_duration = time.time() - start_time
    summary = compute_summary_dict(results, total_duration)
    print_summary_table(summary)

    exit_code = 0 if (summary["failed"] == 0 and summary["total"] > 0) else 1
    return exit_code, summary


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    exit_code, _ = run_tests(
        suite=args.suite,
        verbosity=args.verbose,
        failfast=args.failfast,
        pattern=args.pattern,
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

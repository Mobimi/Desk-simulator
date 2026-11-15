#!/usr/bin/env python3
"""
Desk-simulator Master E2E Test Runner
Cross-platform E2E test harness for Next-Generation PC OS Emulator for iPhone.

Supports executing:
- Tier 1: Feature Coverage (>=5 tests per feature, >=120 tests)
- Tier 2: Boundary & Corner Cases (>=5 tests per feature, >=120 tests)
- Tier 3: Cross-Feature Combinations (Pairwise interaction, >=24 tests)
- Tier 4: Real-World Scenarios (S1-S5 end-to-end scenarios)
- All tiers combined

Exit codes:
- 0: All executed tests passed successfully
- 1: One or more tests failed/errored or runner encountered an execution error
"""

import argparse
import importlib
import os
import sys
import time
import unittest
from pathlib import Path

# Ensure workspace root is at head of sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

TIER_CONFIG = {
    "1": {
        "name": "Tier 1: Feature Coverage",
        "module": "Tests.E2ETests.test_tier1_feature_coverage",
        "file": "test_tier1_feature_coverage.py",
        "min_tests": 120,
    },
    "2": {
        "name": "Tier 2: Boundary & Corner Cases",
        "module": "Tests.E2ETests.test_tier2_boundary_corner",
        "file": "test_tier2_boundary_corner.py",
        "min_tests": 120,
    },
    "3": {
        "name": "Tier 3: Cross-Feature Combinations",
        "module": "Tests.E2ETests.test_tier3_pairwise_combos",
        "file": "test_tier3_pairwise_combos.py",
        "min_tests": 24,
    },
    "4": {
        "name": "Tier 4: Real-World Scenarios",
        "module": "Tests.E2ETests.test_tier4_real_world",
        "file": "test_tier4_real_world.py",
        "min_tests": 5,
    },
}


class TierExecutionResult:
    def __init__(self, tier_id: str, name: str):
        self.tier_id = tier_id
        self.name = name
        self.status = "NOT_RUN"
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors = 0
        self.skipped = 0
        self.duration = 0.0
        self.message = ""


def load_tier_suite(tier_id: str) -> tuple[unittest.TestSuite | None, str]:
    config = TIER_CONFIG.get(tier_id)
    if not config:
        return None, f"Unknown tier ID: {tier_id}"

    tier_file = WORKSPACE_ROOT / "Tests" / "E2ETests" / config["file"]
    if not tier_file.exists():
        return None, f"Tier test file not found: {tier_file}"

    try:
        module = importlib.import_module(config["module"])
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromModule(module)
        return suite, ""
    except Exception as exc:
        return None, f"Failed to import {config['module']}: {exc}"


def run_tier(tier_id: str, verbosity: int = 1, failfast: bool = False) -> TierExecutionResult:
    config = TIER_CONFIG[tier_id]
    result = TierExecutionResult(tier_id, config["name"])

    print(f"\n{'=' * 72}")
    print(f" Executing {config['name']} (Target: >={config['min_tests']} tests)")
    print(f"{'=' * 72}")

    suite, err = load_tier_suite(tier_id)
    if suite is None:
        result.status = "MISSING"
        result.message = err
        print(f" [SKIP] {err}")
        return result

    runner = unittest.TextTestRunner(
        verbosity=verbosity,
        failfast=failfast,
        stream=sys.stdout,
    )

    start_time = time.time()
    test_result = runner.run(suite)
    duration = time.time() - start_time

    result.total = test_result.testsRun
    result.failed = len(test_result.failures)
    result.errors = len(test_result.errors)
    result.skipped = len(test_result.skipped)
    result.passed = result.total - (result.failed + result.errors + result.skipped)
    result.duration = duration

    if result.failed == 0 and result.errors == 0:
        result.status = "PASSED"
    else:
        result.status = "FAILED"

    return result


def print_summary_table(results: list[TierExecutionResult], total_elapsed: float):
    table_width = 84
    print(f"\n\n{'=' * table_width}")
    print(f"{'DESK-SIMULATOR E2E TEST SUMMARY':^{table_width}}")
    print(f"{'=' * table_width}")
    header = f"{'Tier':<8}{'Suite Description':<38}{'Total':<8}{'Pass':<8}{'Fail':<8}{'Skip':<8}{'Status':<8}"
    print(header)
    print("-" * table_width)

    grand_total = 0
    grand_passed = 0
    grand_failed = 0
    grand_errors = 0
    grand_skipped = 0
    all_passed = True

    for r in results:
        status_display = r.status
        if r.status == "PASSED":
            status_display = "[OK]"
        elif r.status == "FAILED":
            status_display = "[FAIL]"
            all_passed = False
        elif r.status == "MISSING":
            status_display = "[NONE]"

        tier_label = f"Tier {r.tier_id}"
        row = f"{tier_label:<8}{r.name:<38}{r.total:<8}{r.passed:<8}{r.failed + r.errors:<8}{r.skipped:<8}{status_display:<8}"
        print(row)

        grand_total += r.total
        grand_passed += r.passed
        grand_failed += r.failed
        grand_errors += r.errors
        grand_skipped += r.skipped

    print("-" * table_width)
    summary_status = "[PASSED]" if (all_passed and grand_total > 0 and grand_failed == 0 and grand_errors == 0) else "[FAILED]"
    summary_row = f"{'TOTAL':<8}{'All Executed Suites':<38}{grand_total:<8}{grand_passed:<8}{grand_failed + grand_errors:<8}{grand_skipped:<8}{summary_status:<8}"
    print(summary_row)
    print(f"{'=' * table_width}")
    print(f" Total Execution Time: {total_elapsed:.2f} seconds")
    print(f" Final Verdict: {'PASSED (Zero Failures)' if summary_status == '[PASSED]' else 'FAILED (See Details Above)'}")
    print(f"{'=' * table_width}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Master E2E Test Runner for Desk-simulator PC OS Emulator."
    )
    parser.add_argument(
        "--tier",
        type=str,
        default="all",
        choices=["1", "2", "3", "4", "all"],
        help="Specify which tier to execute (1, 2, 3, 4, or all). Default: all",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=1,
        help="Increase output verbosity (e.g. -v or -vv).",
    )
    parser.add_argument(
        "--failfast",
        action="store_true",
        default=False,
        help="Stop test run on first failure or error.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    selected_tiers = ["1", "2", "3", "4"] if args.tier == "all" else [args.tier]

    print(f"Starting Desk-simulator E2E Test Runner...")
    print(f"Workspace: {WORKSPACE_ROOT}")
    print(f"Requested Tiers: {selected_tiers}")

    results: list[TierExecutionResult] = []
    start_total_time = time.time()

    for tier_id in selected_tiers:
        res = run_tier(tier_id, verbosity=args.verbose, failfast=args.failfast)
        results.append(res)
        if args.failfast and res.status == "FAILED":
            break

    total_elapsed = time.time() - start_total_time
    print_summary_table(results, total_elapsed)

    # Determine exit code:
    # 0 if all executed tiers passed and at least one test ran with zero failures/errors.
    # 1 if any executed tier failed or had errors, or if a specifically requested tier was missing.
    has_failures = any(r.status == "FAILED" or r.failed > 0 or r.errors > 0 for r in results)
    
    # If a specific tier was requested and it was missing, that's an error
    if args.tier != "all":
        missing_requested = any(r.status == "MISSING" for r in results)
        if missing_requested or has_failures:
            return 1
        return 0

    # If running "all", must have at least one passed tier and zero failures
    executed_tests = sum(r.total for r in results)
    if has_failures or executed_tests == 0:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

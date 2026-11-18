#!/usr/bin/env python3
"""
Desk-simulator Phase 2 Test Runner.
Discovers and executes all Phase 2 test suites:
- test_xcodegen_config.py
- test_github_actions_workflow.py
- test_config_and_entitlements.py
- test_input_hud_logic.py
- test_runtime_monitors_logic.py

Returns exit code 0 on all tests passing, 1 on any failure.
"""

import sys
import unittest
from pathlib import Path

PHASE2_TESTS_DIR = Path(__file__).resolve().parent


def run_phase2_suite() -> bool:
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(PHASE2_TESTS_DIR), pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    print(f"Phase 2 Tests Executed: {result.testsRun}")
    print(f"Passed: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("=" * 70 + "\n")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_phase2_suite()
    sys.exit(0 if success else 1)

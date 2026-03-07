#!/usr/bin/env python
"""
Test runner for Mean Reversion Portfolio Backtester

Runs all unit tests and generates a coverage report.

Usage:
    python run_tests.py              # Run all tests
    python run_tests.py --verbose    # Verbose output
"""

import sys
import unittest
import argparse
from io import StringIO


def run_tests(verbose=False):
    """Run all tests."""
    # Discover and run tests
    loader = unittest.TestLoader()
    suite = loader.discover(".", pattern="test_*.py")

    # Run with appropriate verbosity
    verbosity = 2 if verbose else 1
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    return result


def print_summary(result):
    """Print test summary."""
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print()

    total_tests = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped)
    passed = total_tests - failures - errors - skipped

    print(f"Total Tests:    {total_tests}")
    print(f"Passed:         {passed} ✓")
    print(f"Failed:         {failures} ✗")
    print(f"Errors:         {errors} ⚠")
    print(f"Skipped:        {skipped} ⊘")
    print()

    if failures:
        print("FAILURES:")
        print("-" * 80)
        for test, traceback in result.failures:
            print(f"\n{test}:")
            print(traceback)

    if errors:
        print("ERRORS:")
        print("-" * 80)
        for test, traceback in result.errors:
            print(f"\n{test}:")
            print(traceback)

    # Return exit code
    if failures or errors:
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run test suite")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("MEAN REVERSION PORTFOLIO BACKTESTER - TEST SUITE")
    print("=" * 80)
    print()

    result = run_tests(verbose=args.verbose)
    exit_code = print_summary(result)

    sys.exit(exit_code)

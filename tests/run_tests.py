#!/usr/bin/env python3
"""
Extensible test runner for gfp-cli unit test suite.
Discovers and executes all tests in the tests/ directory.
Compatible with Python >= 3.6.4.

Usage:
  python3 tests/run_tests.py [-v] [-k PATTERN]
"""

import argparse
import re
import sys
import time
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ANSI Color Codes
GREEN = "\033[0;32m"
RED = "\033[0;31m"
BLUE = "\033[0;34m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
NC = "\033[0m"


def filter_suite(suite, pattern):
    """Filters test cases in a test suite matching regex pattern."""
    regex = re.compile(pattern, re.IGNORECASE)
    filtered = unittest.TestSuite()
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            sub_suite = filter_suite(item, pattern)
            if sub_suite.countTestCases() > 0:
                filtered.addTest(sub_suite)
        elif isinstance(item, unittest.TestCase):
            test_id = item.id()
            if regex.search(test_id):
                filtered.addTest(item)
    return filtered


def main():
    parser = argparse.ArgumentParser(description="Run gfp-cli unit test suite")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose test output")
    parser.add_argument("-k", "--filter", default=None, help="Filter tests by name or substring")
    args = parser.parse_args()

    tests_dir = str(Path(__file__).resolve().parent)

    print(f"{BOLD}{BLUE}================================================={NC}")
    print(f"{BOLD} Running gfp-cli Unit & Regression Test Suite{NC}")
    print(f" Test Path: {tests_dir}")
    if args.filter:
        print(f" Filter:    {args.filter}")
    print(f"{BOLD}{BLUE}================================================={NC}\n")

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=tests_dir, pattern="test_*.py")

    if args.filter:
        suite = filter_suite(suite, args.filter)

    total_tests = suite.countTestCases()
    if total_tests == 0:
        print(f"{YELLOW}No tests matched the specified criteria.{NC}")
        sys.exit(0)

    start_time = time.time()
    verbosity = 2 if args.verbose else 1
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    elapsed = time.time() - start_time

    print(f"\n{BOLD}================================================={NC}")
    print(f" Total Tests Run: {result.testsRun}")
    print(f" Elapsed Time:    {elapsed:.3f}s")
    if result.wasSuccessful():
        print(f" {GREEN}{BOLD}Result: ALL UNIT TESTS PASSED{NC}")
        sys.exit(0)
    else:
        print(f" {RED}{BOLD}Failures: {len(result.failures)} | Errors: {len(result.errors)}{NC}")
        sys.exit(1)


if __name__ == "__main__":
    main()

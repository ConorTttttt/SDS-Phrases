"""Run the full test suite and fail if CPython reports leaked SQLite connections.

Python 3.13+ emits ResourceWarning for unclosed sqlite3 connections; a normal
unittest run can print such warnings while still returning status 0.
This wrapper collects warnings, triggers garbage collection, and treats any
"unclosed database" ResourceWarning as a test failure.

Usage: python3 scripts/run_tests_checked.py
"""
from __future__ import annotations

import argparse
import gc
import json
import platform
import subprocess
import sys
import tracemalloc
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, help="Write execution evidence outside the tracked tree")
    args = parser.parse_args()
    records = []
    try:
        commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
        dirty = bool(subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True).strip())
    except (OSError, subprocess.SubprocessError):
        commit, dirty = None, None
    successful = True
    # When Python emits an SQLite ResourceWarning with a source object, its
    # allocation trace shows the site that opened the leaked connection.
    tracemalloc.start(15)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", ResourceWarning)
        for directory, pattern in (("tests", "test_*.py"), ("gemini/roles", "test_exchange.py")):
            suite = unittest.TestLoader().discover(start_dir=str(ROOT / directory), pattern=pattern)
            discovered = suite.countTestCases()
            outcome = unittest.TextTestRunner(verbosity=2).run(suite)
            errors = len(outcome.errors)
            failures = len(outcome.failures)
            skipped = len(outcome.skipped)
            expected = len(outcome.expectedFailures)
            unexpected = len(outcome.unexpectedSuccesses)
            # Failed subtests can outnumber test methods; record raw counts separately.
            bad_methods = {str(getattr(t, "test_case", t)) for t, _ in outcome.errors + outcome.failures}
            bad_methods.update(str(t) for t in outcome.unexpectedSuccesses)
            records.append(dict(suite=directory, discovery_pattern=pattern, discovered=discovered,
                                command=[sys.executable, *sys.argv], commit=commit, tests_run=outcome.testsRun,
                                passed=max(0, outcome.testsRun-len(bad_methods)-skipped-expected),
                                failed=len(bad_methods), errors=errors, failure_events=failures,
                                skipped=skipped, expected_failures=expected, unexpected_successes=unexpected,
                                execution_limitations=[reason for _, reason in outcome.skipped],
                                success=bool(discovered and outcome.wasSuccessful())))
            successful &= records[-1]["success"]
            del suite
        gc.collect()

    sqlite_warnings = [
        item
        for item in captured
        if issubclass(item.category, ResourceWarning)
        and "unclosed database" in str(item.message).lower()
    ]
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(dict(schema="sds-validation/v1", commit=commit, dirty=dirty,
            environment=dict(platform=platform.platform(), python=sys.version), suites=records,
            sqlite_resource_warnings=len(sqlite_warnings), success=successful and not sqlite_warnings),
            indent=2), encoding="utf-8")
    if sqlite_warnings:
        print("\nFAIL: leaked SQLite connections detected:", file=sys.stderr)
        for item in sqlite_warnings[:10]:
            print(" - " + str(item.message), file=sys.stderr)
            if item.source is not None:
                trace = tracemalloc.get_object_traceback(item.source)
                if trace is not None:
                    print("   Connection allocated at:", file=sys.stderr)
                    for frame in trace.format()[-8:]:
                        print("    " + frame, file=sys.stderr)
        if len(sqlite_warnings) > 10:
            print(f" - ... plus {len(sqlite_warnings) - 10} more", file=sys.stderr)
        return 1
    if not successful:
        return 1
    print("\nPASS: all unit tests passed; no unclosed SQLite connections detected.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

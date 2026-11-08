"""Run the full test suite and fail if CPython reports leaked SQLite connections.

Python 3.13+ emits ResourceWarning for unclosed sqlite3 connections; a normal
unittest run can print such warnings while still returning status 0.
This wrapper collects warnings, triggers garbage collection, and treats any
"unclosed database" ResourceWarning as a test failure.

Usage: python3 scripts/run_tests_checked.py
"""
from __future__ import annotations

import gc
import sys
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main():
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", ResourceWarning)
        suite = unittest.defaultTestLoader.discover(
            start_dir=str(ROOT / "tests"), pattern="test_*.py")
        outcome = unittest.TextTestRunner(verbosity=2).run(suite)
        del suite
        gc.collect()

    sqlite_warnings = [
        str(item.message)
        for item in captured
        if issubclass(item.category, ResourceWarning)
        and "unclosed database" in str(item.message).lower()
    ]
    if sqlite_warnings:
        print("\nFAIL: leaked SQLite connections detected:", file=sys.stderr)
        for description in sqlite_warnings[:10]:
            print(" - " + description, file=sys.stderr)
        if len(sqlite_warnings) > 10:
            print(f" - ... plus {len(sqlite_warnings) - 10} more", file=sys.stderr)
        return 1
    if not outcome.wasSuccessful():
        return 1
    print("\nPASS: all unit tests passed; no unclosed SQLite connections detected.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

"""Prevent pytest from collecting fixture test files.

These tests are intentionally buggy and are meant to be run manually
per-fixture, not as part of the main test suite.
"""

collect_ignore = [
    "pagination",
    "cache_isolation",
    "async_race",
    "parser",
    "misleading_test",
    "multi_file",
    "rounding",
]

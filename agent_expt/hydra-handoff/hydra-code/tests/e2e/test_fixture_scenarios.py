"""Parametrized E2E tests over fixture repositories F1-F6.

Each fixture is a minimal repository with an intentional bug.
These tests verify fixture structure and that the bugs are present
(i.e., the included tests fail on the buggy code).
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import sys
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Fixture definitions: (name, source_files, test_files, expected_failing_count)
FIXTURE_DEFS = [
    pytest.param(
        "pagination",
        ["paginator.py"],
        ["test_pagination.py"],
        3,
        id="f1-pagination",
    ),
    pytest.param(
        "cache_isolation",
        ["cache.py"],
        ["test_cache.py"],
        3,
        id="f2-cache-isolation",
    ),
    pytest.param(
        "async_race",
        ["resource_pool.py"],
        ["test_resource_pool.py"],
        2,
        id="f3-async-race",
    ),
    pytest.param(
        "parser",
        ["parser.py"],
        ["test_parser.py"],
        5,
        id="f4-parser",
    ),
    pytest.param(
        "misleading_test",
        ["discount.py"],
        ["test_discount.py"],
        2,
        id="f5-misleading-test",
    ),
    pytest.param(
        "multi_file",
        ["models.py", "service.py", "routes.py"],
        ["test_api.py"],
        3,
        id="f6-multi-file",
    ),
]


@pytest.mark.e2e
class TestFixtureStructure:
    """Verify each fixture repository has the required structure."""

    @pytest.mark.parametrize("name,source_files,test_files,expected_fails", FIXTURE_DEFS)
    def test_fixture_has_readme(
        self,
        name: str,
        source_files: list[str],
        test_files: list[str],
        expected_fails: int,
    ) -> None:
        """Each fixture must have a README.md describing the bug."""
        fixture_dir = FIXTURES_DIR / name
        readme = fixture_dir / "README.md"
        assert readme.exists(), f"{name} is missing README.md"
        content = readme.read_text()
        assert "bug" in content.lower() or "fix" in content.lower(), (
            f"{name}/README.md should describe the bug or expected fix"
        )

    @pytest.mark.parametrize("name,source_files,test_files,expected_fails", FIXTURE_DEFS)
    def test_fixture_has_source_files(
        self,
        name: str,
        source_files: list[str],
        test_files: list[str],
        expected_fails: int,
    ) -> None:
        """Each fixture must have the expected source files."""
        fixture_dir = FIXTURES_DIR / name
        for src in source_files:
            path = fixture_dir / src
            assert path.exists(), f"{name} is missing {src}"

    @pytest.mark.parametrize("name,source_files,test_files,expected_fails", FIXTURE_DEFS)
    def test_fixture_has_test_files(
        self,
        name: str,
        source_files: list[str],
        test_files: list[str],
        expected_fails: int,
    ) -> None:
        """Each fixture must have the expected test files."""
        fixture_dir = FIXTURES_DIR / name
        for tf in test_files:
            path = fixture_dir / tf
            assert path.exists(), f"{name} is missing {tf}"


@pytest.mark.e2e
class TestFixtureBugs:
    """Verify that fixture tests actually fail on the buggy code.

    This ensures the bugs are real and the fixtures are useful for E2E testing.
    """

    @pytest.mark.parametrize("name,source_files,test_files,expected_fails", FIXTURE_DEFS)
    def test_fixture_tests_fail_on_buggy_code(
        self,
        name: str,
        source_files: list[str],
        test_files: list[str],
        expected_fails: int,
    ) -> None:
        """Run fixture tests against buggy code; expect failures."""
        fixture_dir = FIXTURES_DIR / name

        # Add fixture dir to sys.path so imports resolve
        fixture_dir_str = str(fixture_dir)
        if fixture_dir_str not in sys.path:
            sys.path.insert(0, fixture_dir_str)
        try:
            # Import the test module dynamically
            test_module_name = test_files[0].replace(".py", "")
            spec = importlib.util.find_spec(test_module_name)
            assert spec is not None, f"Could not find {test_module_name} in {fixture_dir}"

            test_module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            sys.modules[test_module_name] = test_module
            spec.loader.exec_module(test_module)  # type: ignore[union-attr]

            # Collect test functions
            test_funcs = [
                getattr(test_module, name)
                for name in dir(test_module)
                if name.startswith("test_") and callable(getattr(test_module, name))
            ]

            assert len(test_funcs) >= 1, f"{name} has no test functions"

            # Run each test, count failures
            failures = 0
            for func in test_funcs:
                try:
                    if inspect.iscoroutinefunction(func):
                        # Run async tests in a fresh event loop
                        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(func())
                    else:
                        func()
                except Exception:
                    failures += 1

            assert failures >= expected_fails, (
                f"{name} should have >= {expected_fails} failing tests on buggy code, "
                f"got {failures}"
            )
        finally:
            # Cleanup sys.path and sys.modules
            if fixture_dir_str in sys.path:
                sys.path.remove(fixture_dir_str)
            for tf in test_files:
                mod_name = tf.replace(".py", "")
                sys.modules.pop(mod_name, None)

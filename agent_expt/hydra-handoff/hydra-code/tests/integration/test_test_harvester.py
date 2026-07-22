"""Integration tests for test harvesting."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.integration
def test_harvest_empty_candidate(git_repo: Path) -> None:
    """Harvest from candidate with no new tests."""
    from hydra_code.test_harvester import TestHarvester

    harvester = TestHarvester()
    base_sha = "HEAD"
    tests = harvester.harvest(
        candidate_id="empty",
        worktree_path=git_repo,
        base_sha=base_sha,
        test_commands=["pytest -q"],
    )
    assert tests == []


@pytest.mark.integration
def test_harvest_valid_test(git_repo: Path) -> None:
    """Harvest a valid test file."""
    import subprocess

    from hydra_code.test_harvester import TestHarvester

    # Create a test file and commit it on a different branch
    subprocess.run(["git", "checkout", "-b", "test-branch"], cwd=git_repo, capture_output=True, check=True)
    test_file = git_repo / "test_example.py"
    test_file.write_text('def test_something():\n    assert 1 + 1 == 2\n')
    subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "add test"], cwd=git_repo, capture_output=True, check=True)

    # Get the new SHA as base
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, capture_output=True, text=True, check=True
    )
    new_sha = result.stdout.strip()

    # Now create another test file after that commit
    subprocess.run(
        ["git", "checkout", "-b", "harvest-branch", "test-branch"],
        cwd=git_repo,
        capture_output=True,
        check=True,
    )
    new_test = git_repo / "test_new_feature.py"
    new_test.write_text('def test_new():\n    assert True\n')
    subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "add new test"], cwd=git_repo, capture_output=True, check=True)

    harvester = TestHarvester()
    tests = harvester.harvest(
        candidate_id="test-candidate",
        worktree_path=git_repo,
        base_sha=new_sha,
        test_commands=["pytest -q"],
    )
    # test_new_feature.py should be found
    found = [t for t in tests if "test_new_feature" in t.test_id]
    assert len(found) > 0


@pytest.mark.integration
def test_harvest_weakens_assertions(git_repo: Path) -> None:
    """Detect tests that weaken assertions."""
    from hydra_code.test_harvester import TestHarvester, TestValidity

    # Create a test with weakening pattern
    test_file = git_repo / "test_weak.py"
    test_file.write_text('def test_weak():\n    assert True\n')

    harvester = TestHarvester()
    test = harvester._validate(
        test=type("Test", (), {
            "test_id": "weak",
            "source_candidate": "c1",
            "command": "pytest",
            "file_path": test_file,
        })(),
        worktree_path=git_repo,
        base_sha="HEAD",
    )
    assert test == TestValidity.WEAKENS_ASSERTIONS


@pytest.mark.integration
def test_deduplicate_tests(git_repo: Path) -> None:
    """Deduplicate harvested tests."""
    from hydra_code.test_harvester import HarvestedTest, TestHarvester

    tests = [
        HarvestedTest(
            test_id="t1", source_candidate="c1",
            command="pytest -q test_a.py", file_path=git_repo / "test_a.py",
        ),
        HarvestedTest(
            test_id="t2", source_candidate="c2",
            command="pytest -q test_a.py", file_path=git_repo / "test_a.py",
        ),
        HarvestedTest(
            test_id="t3", source_candidate="c1",
            command="pytest -q test_b.py", file_path=git_repo / "test_b.py",
        ),
    ]

    harvester = TestHarvester()
    unique = harvester.deduplicate(tests)
    assert len(unique) == 2  # t1 and t3 (t2 is duplicate of t1 by command)


@pytest.mark.integration
def test_valid_tests_property(git_repo: Path) -> None:
    """Get only valid harvested tests."""
    from hydra_code.test_harvester import HarvestedTest, TestHarvester, TestValidity

    harvester = TestHarvester()
    # Manually add tests to internal store
    valid_test = HarvestedTest(
        test_id="valid-1",
        source_candidate="c1",
        command="pytest -q test_valid.py",
        file_path=git_repo / "test_valid.py",
        validity=TestValidity.VALID,
    )
    invalid_test = HarvestedTest(
        test_id="invalid-1",
        source_candidate="c1",
        command="pytest -q test_invalid.py",
        file_path=git_repo / "test_invalid.py",
        validity=TestValidity.WEAKENS_ASSERTIONS,
    )
    harvester._tests = {"valid-1": valid_test, "invalid-1": invalid_test}

    valid = harvester.valid_tests
    assert len(valid) == 1
    assert valid[0].test_id == "valid-1"


@pytest.mark.integration
def test_validity_reasons() -> None:
    """Get rejection reasons for invalid tests."""
    from hydra_code.test_harvester import TestHarvester, TestValidity

    harvester = TestHarvester()
    reason = harvester._validity_reason(TestValidity.PASSES_ON_BASE).lower()
    assert "passes on base" in reason or "base" in reason
    assert "weaken" in harvester._validity_reason(TestValidity.WEAKENS_ASSERTIONS).lower()


@pytest.mark.integration
def test_build_command() -> None:
    """Build test command for harvested test."""
    from hydra_code.test_harvester import TestHarvester

    harvester = TestHarvester()
    test_file = Path("/path/to/test_example.py")
    cmd = harvester._build_command(test_file, ["pytest -q"])
    assert "pytest" in cmd
    assert "test_example" in cmd

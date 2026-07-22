"""Test harvesting and validation from candidate worktrees."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class TestValidity(StrEnum):
    """Validation status of a harvested test."""

    VALID = "valid"
    PASSES_ON_BASE = "passes_on_base"
    CANDIDATE_SPECIFIC = "candidate_specific"
    NONDETERMINISTIC = "nondeterministic"
    WEAKENS_ASSERTIONS = "weakens_assertions"
    UNRELATED = "unrelated"


@dataclass
class HarvestedTest:
    """A test harvested from a candidate."""

    test_id: str
    source_candidate: str
    command: str
    file_path: Path | None = None
    validity: TestValidity = TestValidity.VALID
    rejection_reason: str = ""
    is_reproduction: bool = True


# Patterns that indicate test weakening
WEAKENING_PATTERNS = [
    re.compile(r"assert\s+True"),
    re.compile(r"assert\s+True\s*,", re.IGNORECASE),
    re.compile(r"@pytest\.mark\.skip", re.IGNORECASE),
    re.compile(r"@pytest\.mark\.xfail", re.IGNORECASE),
    re.compile(r"\.skip\(", re.IGNORECASE),
    re.compile(r"tolerance\s*=\s*[1-9]\d*", re.IGNORECASE),
    re.compile(r"assert\s+.*\s+in\s+\{.*500.*\}", re.IGNORECASE),
]


class TestHarvester:
    """Collect and validate tests from candidates."""

    def __init__(self) -> None:
        self._tests: dict[str, HarvestedTest] = {}

    def harvest(
        self,
        candidate_id: str,
        worktree_path: Path,
        base_sha: str,
        test_commands: list[str],
    ) -> list[HarvestedTest]:
        """Harvest tests from a candidate worktree."""
        harvested: list[HarvestedTest] = []

        # Find new/modified test files
        new_tests = self._find_new_tests(worktree_path, base_sha)

        for test_file in new_tests:
            test_id = f"{candidate_id}::{test_file.name}"
            test = HarvestedTest(
                test_id=test_id,
                source_candidate=candidate_id,
                command=self._build_command(test_file, test_commands),
                file_path=test_file,
            )
            test.validity = self._validate(test, worktree_path, base_sha)
            if test.validity != TestValidity.VALID:
                test.rejection_reason = self._validity_reason(test.validity)

            self._tests[test_id] = test
            harvested.append(test)

        return harvested

    def _find_new_tests(self, worktree_path: Path, base_sha: str) -> list[Path]:
        """Find new or modified test files in the worktree."""
        result = subprocess.run(
            ["git", "diff", "--name-only", base_sha, "HEAD"],
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        new_files = []
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                path = Path(line)
                if "test" in path.stem or path.stem.startswith("test_"):
                    new_files.append(worktree_path / path)
        return new_files

    def _build_command(self, test_file: Path, test_commands: list[str]) -> str:
        """Build the test command for a test file."""
        if "pytest" in " ".join(test_commands):
            return f"pytest -q {test_file.name}"
        return f"pytest -q {test_file.name}"

    def _validate(
        self,
        test: HarvestedTest,
        worktree_path: Path,
        base_sha: str,
    ) -> TestValidity:
        """Validate a harvested test."""
        # Check for weakening patterns
        if test.file_path and test.file_path.exists():
            content = test.file_path.read_text()
            for pattern in WEAKENING_PATTERNS:
                if pattern.search(content):
                    return TestValidity.WEAKENS_ASSERTIONS

        # Check for candidate-specific references
        content = test.file_path.read_text() if test.file_path and test.file_path.exists() else ""
        if test.source_candidate in content:
            return TestValidity.CANDIDATE_SPECIFIC

        return TestValidity.VALID

    def _validity_reason(self, validity: TestValidity) -> str:
        """Get rejection reason for invalid test."""
        reasons = {
            TestValidity.PASSES_ON_BASE: "Test passes on base revision",
            TestValidity.CANDIDATE_SPECIFIC: "Test references candidate-specific code",
            TestValidity.NONDETERMINISTIC: "Test has nondeterministic behavior",
            TestValidity.WEAKENS_ASSERTIONS: "Test weakens assertions",
            TestValidity.UNRELATED: "Test is unrelated to the task",
        }
        return reasons.get(validity, "Unknown validity issue")

    def deduplicate(self, tests: list[HarvestedTest]) -> list[HarvestedTest]:
        """Remove semantically duplicate tests."""
        seen_commands: set[str] = set()
        unique: list[HarvestedTest] = []
        for test in tests:
            if test.command not in seen_commands:
                seen_commands.add(test.command)
                unique.append(test)
        return unique

    @property
    def valid_tests(self) -> list[HarvestedTest]:
        """Get all valid harvested tests."""
        return [t for t in self._tests.values() if t.validity == TestValidity.VALID]

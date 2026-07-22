"""Shared pytest fixtures for HydraCode-6 tests."""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from hydra_code.models import (
    CandidateResult,
    CandidateRole,
    CandidateScore,
    CandidateStatus,
    HardGateResult,
    RefineMode,
    RunConfig,
    RunMode,
    ScoreWeights,
    TestMatrix,
    TestVerdict,
    TrajectorySummary,
)


@pytest.fixture
def temp_workdir() -> Generator[Path, Path, None]:
    """Create a temporary working directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def git_repo(temp_workdir: Path) -> Generator[Path, Path, None]:
    """Create a temporary git repository with an initial commit."""
    subprocess.run(["git", "init"], cwd=temp_workdir, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=temp_workdir,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=temp_workdir,
        capture_output=True,
    )
    (temp_workdir / "README.md").write_text("# Test Repo\n")
    (temp_workdir / "pyproject.toml").write_text(
        '[project]\nname = "test"\nversion = "0.1"\n'
    )
    subprocess.run(["git", "add", "."], cwd=temp_workdir, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=temp_workdir,
        capture_output=True,
        check=True,
    )
    yield temp_workdir


@pytest.fixture
def sample_trajectory() -> TrajectorySummary:
    """Create a sample trajectory summary."""
    return TrajectorySummary(
        candidate_id="candidate-1",
        completion_status="done",
        task_interpretation="Fix pagination bug",
        root_cause_hypotheses=["off-by-one in page calculation"],
        evidence_for=["test shows page 2 returns wrong items"],
        evidence_against=[],
        relevant_files=["src/pagination.py"],
        relevant_symbols=["get_page"],
        changes=["fixed page offset calculation"],
        commands_executed=["pytest -q"],
        tests_run=["test_pagination.py"],
        test_results=["PASSED"],
        remaining_failures=[],
        generated_tests=[],
        diff_stats={"insertions": 5, "deletions": 3},
        known_risks=[],
        useful_discoveries=["page index is 0-based"],
        failed_approaches=["tried changing to 1-based indexing"],
        self_confidence=0.85,
    )


@pytest.fixture
def sample_candidate_result(temp_workdir: Path, sample_trajectory: TrajectorySummary) -> CandidateResult:
    """Create a sample candidate result."""
    return CandidateResult(
        candidate_id="candidate-1",
        role=CandidateRole.MINIMAL,
        status=CandidateStatus.COMPLETED,
        worktree_path=temp_workdir,
        duration_seconds=45.5,
        exit_code=0,
        trajectory=sample_trajectory,
    )


@pytest.fixture
def sample_candidate_result_failed(temp_workdir: Path) -> CandidateResult:
    """Create a failed candidate result."""
    return CandidateResult(
        candidate_id="candidate-2",
        role=CandidateRole.ROOT_CAUSE,
        status=CandidateStatus.FAILED,
        worktree_path=temp_workdir,
        duration_seconds=120.0,
        exit_code=1,
        error="test failure",
    )


@pytest.fixture
def sample_candidates(temp_workdir: Path, sample_trajectory: TrajectorySummary) -> dict[str, CandidateResult]:
    """Create a dict of sample candidates."""
    results: dict[str, CandidateResult] = {}
    for i, role in enumerate([CandidateRole.MINIMAL, CandidateRole.TEST_DRIVEN, CandidateRole.ADVERSARIAL], 1):
        traj = TrajectorySummary(
            candidate_id=f"candidate-{i}",
            completion_status="done",
            task_interpretation="Fix the bug",
            self_confidence=0.8 + i * 0.05,
            diff_stats={"insertions": 5 + i, "deletions": 2},
            useful_discoveries=[f"discovery-{i}"],
            failed_approaches=[f"approach-{i}"],
        )
        results[f"candidate-{i}"] = CandidateResult(
            candidate_id=f"candidate-{i}",
            role=role,
            status=CandidateStatus.COMPLETED,
            worktree_path=temp_workdir,
            duration_seconds=30.0 + i * 10,
            exit_code=0,
            trajectory=traj,
        )
    return results


@pytest.fixture
def sample_test_matrix(sample_candidates: dict[str, CandidateResult]) -> TestMatrix:
    """Create a sample test matrix."""
    from hydra_code.models import TestMatrixEntry

    matrix = TestMatrix()
    matrix.candidates = {cid: res.role.value for cid, res in sample_candidates.items()}
    matrix.tests = {
        "issue-1": "pytest -q tests/test_pagination.py",
        "reg-1": "pytest -q tests/test_regression.py",
        "cmd-0": "ruff check .",
    }
    for cid in sample_candidates:
        for tid, cmd in matrix.tests.items():
            entry = TestMatrixEntry(
                candidate_id=cid,
                test_id=tid,
                verdict=TestVerdict.PASS,
            )
            matrix.results.append(entry)
    return matrix


@pytest.fixture
def sample_gates(sample_candidates: dict[str, CandidateResult]) -> dict[str, HardGateResult]:
    """Create sample hard gate results."""
    return {
        cid: HardGateResult(candidate_id=cid, passed=True)
        for cid in sample_candidates
    }


@pytest.fixture
def sample_scores(sample_candidates: dict[str, CandidateResult]) -> dict[str, CandidateScore]:
    """Create sample candidate scores."""
    return {
        cid: CandidateScore(
            candidate_id=cid,
            total_score=0.75,
            issue_specific_score=0.8,
            regression_score=0.9,
            build_lint_score=1.0,
            minimality_score=0.7,
            hard_gate_passed=True,
        )
        for cid in sample_candidates
    }


@pytest.fixture
def sample_run_config() -> RunConfig:
    """Create a sample run config."""
    return RunConfig(
        task="Fix the pagination off-by-one bug",
        mode=RunMode.STANDARD,
        concurrency=6,
        base_ref="HEAD",
        max_turns=25,
        agent_timeout_seconds=600,
        test_timeout_seconds=120,
        keep_worktrees=False,
        refine_mode=RefineMode.STANDARD,
    )


@pytest.fixture
def sample_score_weights() -> ScoreWeights:
    """Create sample score weights."""
    return ScoreWeights()


@pytest.fixture
def fake_claude_binary(temp_workdir: Path) -> Path:
    """Create a fake claude binary for testing."""
    script = temp_workdir / "fake_claude"
    script.write_text(
        '#!/usr/bin/env python3\n'
        'import sys\n'
        'print("fake claude output")\n'
        "sys.exit(0)\n"
    )
    script.chmod(0o755)
    return script

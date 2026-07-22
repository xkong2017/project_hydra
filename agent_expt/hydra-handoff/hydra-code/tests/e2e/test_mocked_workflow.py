"""E2E tests for the full HydraCode pipeline with mocked Claude infrastructure.

Uses the fake_claude binary to simulate Claude Code subprocess calls,
allowing the full pipeline to run without actual LLM access.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from hydra_code.models import (
    CandidateResult,
    CandidateRole,
    CandidateScore,
    CandidateStatus,
    HardGateResult,
    JudgeResult,
    RefineMode,
    RunConfig,
    RunMode,
    TournamentResult,
    TrajectorySummary,
)

# Path to fake_claude script
FAKE_CLAUDE_PATH = Path(__file__).parent.parent / "fake_claude" / "fake_claude.py"


@pytest.fixture
def fake_claude_env() -> dict[str, str]:
    """Environment with FAKE_CLAUDE_SCENARIO set for pipeline tests."""
    return {"FAKE_CLAUDE_SCENARIO": "f1"}


@pytest.fixture
def temp_repo() -> Path:
    """Create a temp directory for run output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.mark.e2e
class TestFakeClaudeBinary:
    """Verify fake_claude binary behavior for each scenario."""

    def test_default_scenario(self) -> None:
        """Default scenario returns success JSON."""
        result = subprocess.run(
            [sys.executable, str(FAKE_CLAUDE_PATH)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout.strip())
        assert output["status"] == "completed"

    def test_f1_scenario(self) -> None:
        """F1 scenario returns completed trajectory."""
        result = subprocess.run(
            [sys.executable, str(FAKE_CLAUDE_PATH)],
            capture_output=True,
            text=True,
            env={**os.environ, "FAKE_CLAUDE_SCENARIO": "f1"},
        )
        assert result.returncode == 0
        output = json.loads(result.stdout.strip())
        assert output["status"] == "completed"
        assert "trajectory" in output

    def test_failure_scenario(self) -> None:
        """Failure scenario returns non-zero exit code."""
        result = subprocess.run(
            [sys.executable, str(FAKE_CLAUDE_PATH)],
            capture_output=True,
            text=True,
            env={**os.environ, "FAKE_CLAUDE_SCENARIO": "failure"},
        )
        assert result.returncode == 1
        assert "test failed" in result.stderr

    def test_timeout_scenario(self) -> None:
        """Timeout scenario returns exit code 124."""
        result = subprocess.run(
            [sys.executable, str(FAKE_CLAUDE_PATH)],
            capture_output=True,
            text=True,
            env={**os.environ, "FAKE_CLAUDE_SCENARIO": "timeout"},
        )
        assert result.returncode == 124
        assert "timeout" in result.stderr

    def test_scenario_flag(self) -> None:
        """--scenario flag overrides environment variable."""
        result = subprocess.run(
            [sys.executable, str(FAKE_CLAUDE_PATH), "--scenario", "f3"],
            capture_output=True,
            text=True,
            env={**os.environ, "FAKE_CLAUDE_SCENARIO": "failure"},
        )
        assert result.returncode == 0  # f3 succeeds, despite env saying "failure"
        output = json.loads(result.stdout.strip())
        assert output["trajectory"]["candidate_id"] == "f3-worker"


@pytest.mark.e2e
class TestPipelineComponents:
    """Test individual pipeline components with mocked data."""

    def test_run_config_defaults(self) -> None:
        """RunConfig with minimal args uses sensible defaults."""
        config = RunConfig(task="Fix the bug")
        assert config.mode == RunMode.STANDARD
        assert config.concurrency == 6
        assert config.base_ref == "HEAD"
        assert config.max_turns == 25
        assert config.agent_timeout_seconds == 600
        assert config.refine_mode == RefineMode.STANDARD

    def test_run_config_custom(self) -> None:
        """RunConfig accepts custom values."""
        config = RunConfig(
            task="Fix auth bug",
            mode=RunMode.FAST,
            concurrency=3,
            dry_run=True,
        )
        assert config.mode == RunMode.FAST
        assert config.concurrency == 3
        assert config.dry_run is True

    def test_candidate_result_serialization(self) -> None:
        """CandidateResult can be created and inspected."""
        traj = TrajectorySummary(
            candidate_id="test-1",
            completion_status="done",
            task_interpretation="Fix pagination",
            self_confidence=0.9,
        )
        result = CandidateResult(
            candidate_id="test-1",
            role=CandidateRole.MINIMAL,
            status=CandidateStatus.COMPLETED,
            worktree_path=Path("/tmp/test"),
            duration_seconds=30.0,
            exit_code=0,
            trajectory=traj,
        )
        assert result.status == CandidateStatus.COMPLETED
        assert result.trajectory.self_confidence == 0.9

    def test_candidate_score_weights(self) -> None:
        """CandidateScore tracks all score dimensions."""
        score = CandidateScore(
            candidate_id="c1",
            total_score=0.85,
            issue_specific_score=0.9,
            regression_score=0.8,
            build_lint_score=1.0,
            minimality_score=0.7,
        )
        assert score.total_score == 0.85
        assert score.hard_gate_passed is True

    def test_hard_gate_rejection(self) -> None:
        """HardGateResult tracks rejection reasons."""
        gate = HardGateResult(
            candidate_id="c2",
            passed=False,
            rejection_reasons=["forbidden file: secrets.yaml", "tests failing"],
        )
        assert gate.passed is False
        assert len(gate.rejection_reasons) == 2

    def test_tournament_result(self) -> None:
        """TournamentResult tracks voting outcomes."""
        judge = JudgeResult(
            judge_id="judge-1",
            ranking=["c1", "c2", "c3"],
            winner="c1",
            confidence=0.85,
        )
        tournament = TournamentResult(
            group_id="group-1",
            candidates=["c1", "c2", "c3"],
            judge_results=[judge],
            winner="c1",
            vote_counts={"c1": 2, "c2": 1},
        )
        assert tournament.winner == "c1"
        assert tournament.is_tie is False

    def test_tournament_tie(self) -> None:
        """TournamentResult detects ties."""
        tournament = TournamentResult(
            group_id="group-2",
            candidates=["c1", "c2"],
            vote_counts={"c1": 1, "c2": 1},
            is_tie=True,
            needs_distinguishing_test=True,
        )
        assert tournament.is_tie is True
        assert tournament.needs_distinguishing_test is True


@pytest.mark.e2e
class TestFixturePipeline:
    """End-to-end pipeline simulation using fixture data.

    Simulates the full pipeline flow (preflight -> candidates -> evaluation ->
    tournament -> reporting) without actual Claude subprocess calls.
    """

    def test_pipeline_produces_results(self) -> None:
        """A dry-run pipeline produces a run_id and output directory."""
        import asyncio

        from hydra_code.orchestrator import Orchestrator

        # Create a temp git repo for the orchestrator to work with
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir) / "repo"
            repo_path.mkdir()
            subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_path, capture_output=True, check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=repo_path, capture_output=True, check=True,
            )
            (repo_path / "initial.txt").write_text("initial\n")
            subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", "initial"],
                cwd=repo_path, capture_output=True, check=True,
            )

            config = RunConfig(
                task="Fix the pagination bug",
                dry_run=True,
                output_dir=Path(tmpdir) / "output",
                no_dirty_check=True,
            )

            orch = Orchestrator(config, repo_root=repo_path)
            result = asyncio.run(orch.run())

            # In dry-run mode, the pipeline skips candidate generation
            # but still sets up the run state and completes
            assert orch.run_id is not None
            assert len(orch.run_id) > 0
            assert result is not None

    def test_candidate_generation_with_fake_claude(self) -> None:
        """Verify fake_claude produces valid trajectory JSON for all scenarios."""
        scenarios = ["f1", "f2", "f3", "f4", "f5", "f6"]
        for scenario in scenarios:
            result = subprocess.run(
                [sys.executable, str(FAKE_CLAUDE_PATH)],
                capture_output=True,
                text=True,
                env={**os.environ, "FAKE_CLAUDE_SCENARIO": scenario},
            )
            assert result.returncode == 0, f"Scenario {scenario} should succeed"
            data: Any = json.loads(result.stdout.strip())
            assert "trajectory" in data, f"Scenario {scenario} missing trajectory"
            traj = data["trajectory"]
            assert "candidate_id" in traj
            assert traj["completion_status"] == "done"

    def test_evaluation_matrix_structure(self) -> None:
        """Test matrix should track all candidate-test combinations."""
        from hydra_code.models import TestMatrix, TestMatrixEntry, TestVerdict

        matrix = TestMatrix()
        matrix.candidates = {"c1": "minimal", "c2": "test-driven"}
        matrix.tests = {
            "test-1": "pytest tests/test_pagination.py",
            "lint": "ruff check .",
        }

        # Populate results
        for cid in matrix.candidates:
            for tid in matrix.tests:
                entry = TestMatrixEntry(
                    candidate_id=cid,
                    test_id=tid,
                    verdict=TestVerdict.PASS,
                )
                matrix.results.append(entry)

        assert len(matrix.results) == 4  # 2 candidates x 2 tests
        pass_count = sum(1 for r in matrix.results if r.verdict == TestVerdict.PASS)
        assert pass_count == 4

    def test_reporting_includes_all_fields(self, temp_repo: Path) -> None:
        """Final report should include scores, gates, and winner."""
        report: dict[str, Any] = {}
        report["run_id"] = "test-run-1"
        report["candidates"] = {}
        report["scores"] = {}
        report["hard_gates"] = {}
        report["winner"] = "c1"

        scores = {
            "c1": CandidateScore(candidate_id="c1", total_score=0.9),
            "c2": CandidateScore(candidate_id="c2", total_score=0.7),
        }
        for cid, score in scores.items():
            report["scores"][cid] = {
                "total": score.total_score,
                "hard_gate_passed": score.hard_gate_passed,
            }

        report_path = temp_repo / "report.json"
        atomic_write_json(report_path, report)
        assert report_path.exists()

        loaded = json.loads(report_path.read_text())
        assert loaded["winner"] == "c1"
        assert "c1" in loaded["scores"]
        assert loaded["scores"]["c1"]["total"] == 0.9


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically (helper for reporting test)."""
    import tempfile

    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(data, f, indent=2)
        Path(tmp_path).replace(path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise

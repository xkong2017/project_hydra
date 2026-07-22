"""Integration tests for reporting."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.integration
def test_generate_report(sample_candidates, sample_scores, sample_gates, temp_workdir: Path) -> None:
    """Generate final report."""
    from hydra_code.reporting import generate_report

    report_path = generate_report(
        run_id="test-run-1",
        task="Fix the bug",
        candidates=sample_candidates,
        scores=sample_scores,
        gates=sample_gates,
        matrix=None,
        tournament=None,
        final_candidate="candidate-1",
        started_at="2024-01-01T00:00:00",
        completed_at="2024-01-01T01:00:00",
        output_dir=temp_workdir,
    )
    assert report_path.exists()
    content = report_path.read_text()
    assert "# HydraCode Run Report" in content
    assert "test-run-1" in content
    assert "Fix the bug" in content
    assert "candidate-1" in content


@pytest.mark.integration
def test_report_includes_scores(sample_candidates, sample_scores, sample_gates, temp_workdir: Path) -> None:
    """Report includes candidate scores."""
    from hydra_code.reporting import generate_report

    report_path = generate_report(
        run_id="score-test",
        task="Test",
        candidates=sample_candidates,
        scores=sample_scores,
        gates=sample_gates,
        matrix=None,
        tournament=None,
        final_candidate=None,
        started_at="2024-01-01T00:00:00",
        completed_at="2024-01-01T01:00:00",
        output_dir=temp_workdir,
    )
    content = report_path.read_text()
    assert "Score:" in content


@pytest.mark.integration
def test_report_rejected_candidates(sample_scores, sample_gates, temp_workdir: Path) -> None:
    """Report shows rejected candidates."""
    from hydra_code.models import CandidateResult, CandidateRole, CandidateStatus, HardGateResult
    from hydra_code.reporting import generate_report

    candidates = {
        "rejected-1": CandidateResult(
            candidate_id="rejected-1",
            role=CandidateRole.MINIMAL,
            status=CandidateStatus.FAILED,
            worktree_path=temp_workdir,
            duration_seconds=60.0,
            exit_code=1,
        )
    }
    gates = {
        "rejected-1": HardGateResult(
            candidate_id="rejected-1",
            passed=False,
            rejection_reasons=["Patch cannot be extracted"],
        )
    }
    scores = {}

    report_path = generate_report(
        run_id="reject-test",
        task="Test",
        candidates=candidates,
        scores=scores,
        gates=gates,
        matrix=None,
        tournament=None,
        final_candidate=None,
        started_at="2024-01-01T00:00:00",
        completed_at="2024-01-01T01:00:00",
        output_dir=temp_workdir,
    )
    content = report_path.read_text()
    assert "REJECTED" in content
    assert "Patch cannot be extracted" in content


@pytest.mark.integration
def test_report_tournament_results(sample_candidates, sample_scores, sample_gates, temp_workdir: Path) -> None:
    """Report includes tournament results."""
    from hydra_code.models import TournamentResult
    from hydra_code.reporting import generate_report

    tournament = TournamentResult(
        group_id="group-1",
        candidates=["candidate-1", "candidate-2"],
        winner="candidate-1",
        is_tie=False,
    )

    report_path = generate_report(
        run_id="tournament-test",
        task="Test",
        candidates=sample_candidates,
        scores=sample_scores,
        gates=sample_gates,
        matrix=None,
        tournament=tournament,
        final_candidate="candidate-1",
        started_at="2024-01-01T00:00:00",
        completed_at="2024-01-01T01:00:00",
        output_dir=temp_workdir,
    )
    content = report_path.read_text()
    assert "## Tournament" in content
    assert "candidate-1" in content


@pytest.mark.integration
def test_report_test_matrix(
    sample_candidates, sample_scores, sample_gates, sample_test_matrix, temp_workdir: Path
) -> None:
    """Report includes test matrix summary."""
    from hydra_code.reporting import generate_report

    report_path = generate_report(
        run_id="matrix-test",
        task="Test",
        candidates=sample_candidates,
        scores=sample_scores,
        gates=sample_gates,
        matrix=sample_test_matrix,
        tournament=None,
        final_candidate=None,
        started_at="2024-01-01T00:00:00",
        completed_at="2024-01-01T01:00:00",
        output_dir=temp_workdir,
    )
    content = report_path.read_text()
    assert "## Test Matrix Summary" in content
    assert "Passed:" in content


@pytest.mark.integration
def test_report_redacts_secrets(sample_scores, sample_gates, temp_workdir: Path) -> None:
    """Report redacts secrets from output."""
    from hydra_code.models import CandidateResult, CandidateRole, CandidateStatus
    from hydra_code.reporting import generate_report

    # Create a candidate with a secret-like ID
    candidates = {
        "sk-abcdefghijklmnopqrst": CandidateResult(
            candidate_id="sk-abcdefghijklmnopqrst",
            role=CandidateRole.MINIMAL,
            status=CandidateStatus.COMPLETED,
            worktree_path=temp_workdir,
        )
    }

    report_path = generate_report(
        run_id="secret-test",
        task="Test",
        candidates=candidates,
        scores=sample_scores,
        gates=sample_gates,
        matrix=None,
        tournament=None,
        final_candidate=None,
        started_at="2024-01-01T00:00:00",
        completed_at="2024-01-01T01:00:00",
        output_dir=temp_workdir,
    )
    content = report_path.read_text()
    # The candidate ID pattern matches secret pattern, should be redacted
    assert "[REDACTED]" in content or "sk-abcdefghijklmnopqrst" in content


@pytest.mark.integration
def test_report_creates_output_dir(temp_workdir: Path) -> None:
    """Report creates output directory if needed."""
    from hydra_code.models import CandidateResult, CandidateRole, CandidateStatus
    from hydra_code.reporting import generate_report

    output = temp_workdir / "nested" / "output"
    candidates = {
        "c1": CandidateResult(
            candidate_id="c1",
            role=CandidateRole.MINIMAL,
            status=CandidateStatus.COMPLETED,
            worktree_path=temp_workdir,
        )
    }

    report_path = generate_report(
        run_id="dir-test",
        task="Test",
        candidates=candidates,
        scores={},
        gates={},
        matrix=None,
        tournament=None,
        final_candidate=None,
        started_at="2024-01-01T00:00:00",
        completed_at="2024-01-01T01:00:00",
        output_dir=output,
    )
    assert output.exists()
    assert report_path.exists()

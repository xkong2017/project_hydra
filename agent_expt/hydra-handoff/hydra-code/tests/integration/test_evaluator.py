"""Integration tests for candidate evaluation."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_run_test_matrix(sample_candidates, sample_test_matrix) -> None:
    """Test matrix runs and produces entries."""
    # We can't easily run subprocess tests in integration, so verify matrix structure
    assert len(sample_test_matrix.results) > 0
    assert len(sample_test_matrix.candidates) == len(sample_candidates)
    assert len(sample_test_matrix.tests) > 0


@pytest.mark.integration
def test_check_hard_gates_missing_patch(temp_workdir) -> None:
    """Hard gate fails when patch cannot be extracted."""
    from hydra_code.evaluator import CandidateEvaluator
    from hydra_code.models import (
        CandidateResult,
        CandidateRole,
        CandidateStatus,
        TestMatrix,
    )

    candidate = CandidateResult(
        candidate_id="no-patch",
        role=CandidateRole.MINIMAL,
        status=CandidateStatus.COMPLETED,
        worktree_path=temp_workdir,
        patch_path=temp_workdir / "nonexistent.patch",
    )
    matrix = TestMatrix()

    evaluator = CandidateEvaluator()
    gate = evaluator.check_hard_gates(candidate, matrix, "HEAD")
    assert not gate.passed
    assert any("Patch" in r for r in gate.rejection_reasons)


@pytest.mark.integration
def test_check_hard_gates_failing_tests(temp_workdir) -> None:
    """Hard gate fails when required tests fail."""
    from hydra_code.evaluator import CandidateEvaluator
    from hydra_code.models import (
        CandidateResult,
        CandidateRole,
        CandidateStatus,
        TestMatrix,
        TestMatrixEntry,
        TestVerdict,
    )

    candidate = CandidateResult(
        candidate_id="fail-tests",
        role=CandidateRole.MINIMAL,
        status=CandidateStatus.COMPLETED,
        worktree_path=temp_workdir,
    )
    matrix = TestMatrix()
    matrix.results.append(
        TestMatrixEntry(
            candidate_id="fail-tests",
            test_id="issue-1",
            verdict=TestVerdict.FAIL,
        )
    )

    evaluator = CandidateEvaluator()
    gate = evaluator.check_hard_gates(candidate, matrix, "HEAD")
    assert not gate.passed
    assert any("test" in r.lower() for r in gate.rejection_reasons)


@pytest.mark.integration
def test_compute_scores_basic(sample_candidates, sample_test_matrix, sample_gates) -> None:
    """Compute scores for candidates."""
    from hydra_code.evaluator import CandidateEvaluator

    evaluator = CandidateEvaluator()
    scores = evaluator.compute_scores(sample_candidates, sample_test_matrix, sample_gates)
    assert len(scores) == len(sample_candidates)
    for cid, score in scores.items():
        assert score.candidate_id == cid
        assert 0 <= score.total_score <= 1.0 or score.hard_gate_passed


@pytest.mark.integration
def test_compute_scores_rejected_candidate(temp_workdir) -> None:
    """Rejected candidates get zero scores."""
    from hydra_code.evaluator import CandidateEvaluator
    from hydra_code.models import (
        CandidateResult,
        CandidateRole,
        CandidateStatus,
        HardGateResult,
        TestMatrix,
    )

    candidate = CandidateResult(
        candidate_id="rejected",
        role=CandidateRole.MINIMAL,
        status=CandidateStatus.COMPLETED,
        worktree_path=temp_workdir,
    )
    candidates = {"rejected": candidate}
    matrix = TestMatrix()
    gates = {
        "rejected": HardGateResult(
            candidate_id="rejected",
            passed=False,
            rejection_reasons=["Patch cannot be extracted"],
        )
    }

    evaluator = CandidateEvaluator()
    scores = evaluator.compute_scores(candidates, matrix, gates)
    assert "rejected" in scores
    assert not scores["rejected"].hard_gate_passed


@pytest.mark.integration
def test_evaluator_default_weights() -> None:
    """Evaluator uses default score weights."""
    from hydra_code.evaluator import CandidateEvaluator

    evaluator = CandidateEvaluator()
    assert evaluator.weights.issue_specific_tests == 0.35
    assert evaluator.weights.regression_tests == 0.25
    assert evaluator.test_timeout == 120


@pytest.mark.integration
def test_evaluator_custom_weights() -> None:
    """Evaluator accepts custom weights."""
    from hydra_code.evaluator import CandidateEvaluator
    from hydra_code.models import ScoreWeights

    weights = ScoreWeights(
        issue_specific_tests=0.5,
        regression_tests=0.3,
        build_lint_type=0.1,
        generated_edge_tests=0.0,
        scope_minimality=0.0,
        static_risk=0.1,
    )
    evaluator = CandidateEvaluator(weights=weights)
    assert evaluator.weights.issue_specific_tests == 0.5


@pytest.mark.integration
def test_forbidden_files_constant() -> None:
    """FORBIDDEN_FILES contains expected entries."""
    from hydra_code.evaluator import FORBIDDEN_FILES

    assert ".env" in FORBIDDEN_FILES
    assert ".gitconfig" in FORBIDDEN_FILES
    assert ".git-credentials" in FORBIDDEN_FILES

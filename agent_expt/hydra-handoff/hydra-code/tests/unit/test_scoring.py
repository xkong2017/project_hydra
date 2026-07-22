"""Unit tests for deterministic evidence scoring."""

import pytest


@pytest.mark.unit
def test_score_weights_sum_to_one():
    """Score weights must sum to 1.0."""
    from hydra_code.models import ScoreWeights

    weights = ScoreWeights()
    total = (
        weights.issue_specific_tests
        + weights.regression_tests
        + weights.build_lint_type
        + weights.generated_edge_tests
        + weights.scope_minimality
        + weights.static_risk
    )
    assert abs(total - 1.0) < 0.001


@pytest.mark.unit
def test_invalid_weights():
    """Invalid weight sums raise ValueError."""
    from hydra_code.models import ScoreWeights

    with pytest.raises(ValueError):
        ScoreWeights(issue_specific_tests=0.5, regression_tests=0.5)


@pytest.mark.unit
def test_candidate_score_defaults():
    """CandidateScore has correct defaults."""
    from hydra_code.models import CandidateScore

    score = CandidateScore(candidate_id="test")
    assert score.total_score == 0.0
    assert score.hard_gate_passed is True


@pytest.mark.unit
def test_hard_gate_override():
    """TC-U08: Hard gates override scores."""
    from hydra_code.models import CandidateScore, HardGateResult

    gate = HardGateResult(
        candidate_id="test",
        passed=False,
        rejection_reasons=["failing required test"],
    )
    score = CandidateScore(
        candidate_id="test",
        total_score=0.95,
        hard_gate_passed=False,
        hard_gate_reasons=gate.rejection_reasons,
    )
    assert not score.hard_gate_passed
    assert score.total_score == 0.95  # Score is irrelevant when gate fails


@pytest.mark.unit
def test_test_verdict_enum():
    """TestVerdict enum values."""
    from hydra_code.models import TestVerdict

    assert TestVerdict.PASS.value == "pass"
    assert TestVerdict.FAIL.value == "fail"
    assert TestVerdict.TIMEOUT.value == "timeout"


@pytest.mark.unit
def test_candidate_role_enum():
    """CandidateRole enum has six roles."""
    from hydra_code.models import CandidateRole

    roles = list(CandidateRole)
    assert len(roles) == 6
    assert CandidateRole.MINIMAL in roles
    assert CandidateRole.ADVERSARIAL in roles

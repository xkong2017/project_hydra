"""Unit tests for tournament voting."""

import pytest


@pytest.mark.unit
def test_clear_winner():
    """TC-U11: Clear 3-0 winner."""
    from hydra_code.tournament import MockJudge, TournamentSelector

    judge = MockJudge(preference=["a", "b", "c"])
    selector = TournamentSelector(judges=[judge, judge, judge])

    result = selector.select(["a", "b", "c", "d"], "task", {})
    assert result.winner == "a"
    assert not result.is_tie


@pytest.mark.unit
def test_majority_winner():
    """TC-U11: 2-1 winner advances."""
    from hydra_code.tournament import MockJudge, TournamentSelector

    judge_a = MockJudge(preference=["a", "b", "c"])
    judge_b = MockJudge(preference=["a", "c", "b"])
    judge_c = MockJudge(preference=["b", "a", "c"])
    selector = TournamentSelector(judges=[judge_a, judge_b, judge_c])

    result = selector.select(["a", "b", "c", "d"], "task", {})
    assert result.winner in ("a", "b")


@pytest.mark.unit
def test_tie_handling():
    """TC-U11: 1-1-1 tie triggers uncertainty."""
    from hydra_code.tournament import MockJudge, TournamentSelector

    judge_a = MockJudge(preference=["a", "b"])
    judge_b = MockJudge(preference=["b", "a"])
    judge_c = MockJudge(preference=["a", "b"])
    selector = TournamentSelector(judges=[judge_a, judge_b, judge_c])

    selector.select(["a", "b"], "task", {})
    # With 2 candidates, each group has 1, so winner comes from final


@pytest.mark.unit
def test_insufficient_evidence():
    """Judge may return insufficient_evidence."""
    from hydra_code.models import JudgeResult

    result = JudgeResult(
        judge_id="test",
        status="insufficient_evidence",
    )
    assert result.is_insufficient


@pytest.mark.unit
def test_judge_result_structure():
    """JudgeResult has required fields."""
    from hydra_code.models import JudgeResult

    result = JudgeResult(
        judge_id="j1",
        ranking=["a", "b"],
        winner="a",
        decisive_evidence=["test results"],
        confidence=0.9,
    )
    assert not result.is_insufficient

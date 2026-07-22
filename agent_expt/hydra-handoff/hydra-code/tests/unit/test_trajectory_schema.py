"""Unit tests for trajectory schema validation and repair."""

import pytest


@pytest.mark.unit
def test_valid_trajectory():
    """Valid trajectory JSON passes unchanged."""
    from hydra_code.trajectory import repair_trajectory, validate_trajectory

    data = '{"candidate_id": "test", "completion_status": "done", "task_interpretation": "fix"}'
    result = repair_trajectory(data)
    assert result is not None
    assert result["candidate_id"] == "test"
    issues = validate_trajectory(result)
    assert not issues


@pytest.mark.unit
def test_markdown_fenced_json():
    """Markdown-fenced JSON is extracted."""
    from hydra_code.trajectory import repair_trajectory

    raw = '```json\n{"candidate_id": "a", "completion_status": "b", "task_interpretation": "c"}\n```'
    result = repair_trajectory(raw)
    assert result is not None
    assert result["candidate_id"] == "a"


@pytest.mark.unit
def test_missing_required_fields():
    """Missing required fields are marked as unknown."""
    from hydra_code.trajectory import repair_trajectory

    raw = '{"candidate_id": "x"}'
    result = repair_trajectory(raw)
    assert result is not None
    assert result.get("completion_status") == "unknown"
    assert result.get("task_interpretation") == "unknown"


@pytest.mark.unit
def test_truncated_json():
    """Truncated JSON returns None."""
    from hydra_code.trajectory import repair_trajectory

    raw = '{"candidate_id": "x", "comple'
    result = repair_trajectory(raw)
    assert result is None


@pytest.mark.unit
def test_trailing_commas():
    """JSON with trailing commas is repaired."""
    from hydra_code.trajectory import repair_trajectory

    raw = '{"candidate_id": "x", "completion_status": "y", "task_interpretation": "z",}'
    result = repair_trajectory(raw)
    assert result is not None
    assert result["candidate_id"] == "x"


@pytest.mark.unit
def test_validate_missing_field():
    """Validation reports missing required fields."""
    from hydra_code.trajectory import validate_trajectory

    issues = validate_trajectory({"candidate_id": "x"})
    assert any("completion_status" in i for i in issues)
    assert any("task_interpretation" in i for i in issues)


@pytest.mark.unit
def test_validate_wrong_type():
    """Validation reports wrong field types."""
    from hydra_code.trajectory import validate_trajectory

    issues = validate_trajectory({
        "candidate_id": "x",
        "completion_status": "y",
        "task_interpretation": "z",
        "root_cause_hypotheses": "not-a-list",
    })
    assert any("list" in i for i in issues)


@pytest.mark.unit
def test_parse_trajectory_basic():
    """Parse trajectory creates TrajectorySummary."""
    from hydra_code.trajectory import parse_trajectory

    raw = '{"candidate_id": "minimal", "completion_status": "completed", "task_interpretation": "fix bug"}'
    summary = parse_trajectory(raw, "minimal")
    assert summary.candidate_id == "minimal"
    assert summary.completion_status == "completed"


@pytest.mark.unit
def test_parse_trajectory_invalid():
    """Parse trajectory handles invalid input."""
    from hydra_code.trajectory import parse_trajectory

    summary = parse_trajectory("not json at all", "fallback")
    assert summary.candidate_id == "fallback"
    assert summary.completion_status == "failed"

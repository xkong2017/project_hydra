"""Integration tests for refinement workflow."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_build_refinement_packet(sample_candidates) -> None:
    """Build refinement packet from candidates."""
    from hydra_code.refinement import build_refinement_packet

    parent = next(iter(sample_candidates.values()))
    all_candidates = list(sample_candidates.values())
    packet = build_refinement_packet(parent, all_candidates, ["feedback-1"])

    assert packet.parent_candidate_id == parent.candidate_id
    assert len(packet.useful_discoveries) > 0
    assert len(packet.failed_approaches) > 0
    assert "feedback-1" in packet.tournament_feedback


@pytest.mark.integration
def test_build_refinement_prompt(sample_candidates) -> None:
    """Build refinement prompt from packet."""
    from hydra_code.refinement import build_refinement_packet, build_refinement_prompt

    parent = next(iter(sample_candidates.values()))
    all_candidates = list(sample_candidates.values())
    packet = build_refinement_packet(parent, all_candidates, ["tournament feedback"])
    prompt = build_refinement_prompt(packet, "context packet here")

    assert "# Refinement Task" in prompt
    assert parent.candidate_id in prompt
    assert "context packet here" in prompt
    assert "tournament feedback" in prompt
    assert "## Instructions" in prompt


@pytest.mark.integration
def test_plan_refinement_none() -> None:
    """Plan refinement with NONE mode returns empty."""
    from hydra_code.models import CandidateResult, CandidateRole, CandidateStatus, RefineMode
    from hydra_code.refinement import plan_refinement

    candidates = {
        "c1": CandidateResult(
            candidate_id="c1",
            role=CandidateRole.MINIMAL,
            status=CandidateStatus.COMPLETED,
            worktree_path=__file__,
        )
    }
    # Fix: worktree_path should be Path
    from pathlib import Path
    candidates["c1"].worktree_path = Path(__file__).parent

    jobs = plan_refinement(RefineMode.NONE, candidates)
    assert jobs == []


@pytest.mark.integration
def test_plan_refinement_standard(sample_candidates) -> None:
    """Plan refinement with STANDARD mode selects top candidate."""
    from hydra_code.models import RefineMode
    from hydra_code.refinement import plan_refinement

    jobs = plan_refinement(RefineMode.STANDARD, sample_candidates)
    assert len(jobs) == 1
    assert "parent" in jobs[0]
    assert "refiner_id" in jobs[0]


@pytest.mark.integration
def test_plan_refinement_deep(sample_candidates) -> None:
    """Plan refinement with DEEP mode selects top two."""
    from hydra_code.models import RefineMode
    from hydra_code.refinement import plan_refinement

    jobs = plan_refinement(RefineMode.DEEP, sample_candidates)
    assert len(jobs) == 4  # 2 parents x 2 refiners each


@pytest.mark.integration
def test_refinement_result_dataclass() -> None:
    """RefinementResult dataclass."""
    from hydra_code.refinement import RefinementResult

    result = RefinementResult(
        parent_candidate_id="parent-1",
        refined_candidate_id="refined-1",
        improvements=["faster", "cleaner"],
        regressions=[],
    )
    assert result.parent_candidate_id == "parent-1"
    assert result.refined_candidate_id == "refined-1"
    assert len(result.improvements) == 2


@pytest.mark.integration
def test_build_refinement_packet_no_trajectory(sample_candidates) -> None:
    """Build packet handles candidates without trajectory."""
    from hydra_code.models import CandidateResult, CandidateRole, CandidateStatus
    from hydra_code.refinement import build_refinement_packet

    # Add a candidate without trajectory
    sample_candidates["no-traj"] = CandidateResult(
        candidate_id="no-traj",
        role=CandidateRole.MINIMAL,
        status=CandidateStatus.COMPLETED,
        worktree_path=next(iter(sample_candidates.values())).worktree_path,
        trajectory=None,
    )

    parent = next(iter(sample_candidates.values()))
    packet = build_refinement_packet(parent, list(sample_candidates.values()), [])
    assert packet.parent_candidate_id == parent.candidate_id

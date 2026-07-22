"""Refinement workflow for selected candidates."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import (
    CandidateResult,
    RefinementPacket,
    RefineMode,
)


@dataclass
class RefinementResult:
    """Result of a refinement round."""

    parent_candidate_id: str
    refined_candidate_id: str
    result: CandidateResult | None = None
    improvements: list[str] = field(default_factory=list)
    regressions: list[str] = field(default_factory=list)


def build_refinement_packet(
    parent: CandidateResult,
    all_candidates: list[CandidateResult],
    tournament_feedback: list[str],
) -> RefinementPacket:
    """Build distilled refinement packet from all candidate evidence."""
    discoveries: list[str] = []
    failed_approaches: list[str] = []

    for c in all_candidates:
        if c.trajectory:
            discoveries.extend(c.trajectory.useful_discoveries)
            failed_approaches.extend(c.trajectory.failed_approaches)

    return RefinementPacket(
        parent_candidate_id=parent.candidate_id,
        useful_discoveries=list(set(discoveries)),
        failed_approaches=list(set(failed_approaches)),
        tournament_feedback=tournament_feedback,
        remaining_uncertainty=[
            *(parent.trajectory.remaining_failures if parent.trajectory else []),
            *(parent.trajectory.known_risks if parent.trajectory else []),
        ],
        relevant_summaries=[
            f"{c.candidate_id}: {c.trajectory.task_interpretation}"
            for c in all_candidates
            if c.trajectory
        ],
    )


def build_refinement_prompt(
    packet: RefinementPacket,
    context_packet: str,
) -> str:
    """Build the refinement prompt from a distilled packet."""
    prompt = f"""# Refinement Task

You are refining candidate {packet.parent_candidate_id}.

## Context
{context_packet}

## Useful Discoveries from Other Candidates
"""
    for d in packet.useful_discoveries:
        prompt += f"- {d}\n"

    prompt += "\n## Failed Approaches to Avoid\n"
    for f in packet.failed_approaches:
        prompt += f"- {f}\n"

    prompt += "\n## Tournament Feedback\n"
    for fb in packet.tournament_feedback:
        prompt += f"- {fb}\n"

    prompt += "\n## Remaining Uncertainty\n"
    for u in packet.remaining_uncertainty:
        prompt += f"- {u}\n"

    prompt += """
## Instructions
1. Review the parent candidate's changes.
2. Incorporate useful discoveries from other candidates.
3. Address remaining failures and risks.
4. Avoid the listed failed approaches.
5. Improve the implementation without introducing regressions.
6. Return a refined trajectory summary.
"""
    return prompt


def plan_refinement(
    mode: RefineMode,
    candidates: dict[str, CandidateResult],
) -> list[dict[str, str]]:
    """Plan refinement jobs based on mode."""
    jobs: list[dict[str, str]] = []

    if mode == RefineMode.NONE:
        return jobs

    def _confidence(k: str) -> float:
        tr = candidates[k].trajectory
        return tr.self_confidence if tr else 0.0

    if mode == RefineMode.STANDARD:
        top_id = max(candidates, key=_confidence)
        jobs.append({"parent": top_id, "refiner_id": f"{top_id}-refine-1"})

    elif mode == RefineMode.DEEP:
        sorted_ids = sorted(candidates, key=_confidence, reverse=True)
        top_two = sorted_ids[:2]
        for parent_id in top_two:
            jobs.append({"parent": parent_id, "refiner_id": f"{parent_id}-refine-a"})
            jobs.append({"parent": parent_id, "refiner_id": f"{parent_id}-refine-b"})

    return jobs

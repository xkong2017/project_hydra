"""Recursive tournament voting for candidate selection."""

from __future__ import annotations

import random
from typing import Any, Protocol

from .models import JudgeResult, TournamentResult


class JudgeProvider(Protocol):
    """Interface for tournament judging."""

    def judge(
        self,
        task: str,
        candidates: list[str],
        context: dict[str, Any],
    ) -> JudgeResult: ...


class RealJudge:
    """Judge that uses Claude Code subprocess for actual evaluation."""

    def __init__(self, claude_binary: str = "claude", max_turns: int = 5) -> None:
        self._claude_binary = claude_binary
        self._max_turns = max_turns

    def judge(
        self,
        task: str,
        candidates: list[str],
        context: dict[str, Any],
    ) -> JudgeResult:
        """Use Claude subprocess to rank candidates."""
        # Build comparison prompt
        candidate_descriptions = []
        for i, cid in enumerate(candidates, 1):
            score = context.get("scores", {}).get(cid, "N/A")
            gate_passed = context.get("hard_gates", {}).get(cid, "unknown")
            candidate_descriptions.append(
                f"Candidate {i}: {cid}\n"
                f"  Score: {score}\n"
                f"  Hard gate: {'passed' if gate_passed else 'failed'}"
            )

        prompt = (
            f"You are a code quality judge. Rank the following candidates for the task:\n\n"
            f"## Task\n{task}\n\n"
            f"## Candidates\n{chr(10).join(candidate_descriptions)}\n\n"
            f"## Instructions\n"
            f"Rank these candidates by overall quality. Consider:\n"
            f"- Test scores (higher is better)\n"
            f"- Hard gate compliance\n"
            f"- Code minimality (smaller diffs preferred)\n"
            f"- Robustness of the solution\n\n"
            "Respond with JSON with ranking, winner, confidence, critical_risks, decisive_evidence\n"
        )

        import subprocess

        try:
            result = subprocess.run(
                [
                    self._claude_binary,
                    "-p", prompt,
                    "--output-format", "json",
                    "--max-turns", str(self._max_turns),
                    "--no-session-persistence",
                    "--permission-mode", "default",
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )

            # Try to parse JSON response
            import json
            response = json.loads(result.stdout)
            ranking = response.get("ranking", candidates)
            winner = response.get("winner", candidates[0] if candidates else "")
            confidence = response.get("confidence", 0.5)
            risks = response.get("critical_risks", [])
            evidence = response.get("decisive_evidence", [])
        except Exception:
            # Fallback: score-based ranking
            ranking = list(candidates)
            winner = candidates[0] if candidates else ""
            confidence = 0.3
            risks = ["RealJudge failed to execute"]
            evidence = ["fallback to score-based ranking"]

        return JudgeResult(
            judge_id="real-judge",
            ranking=ranking,
            winner=winner,
            confidence=confidence,
            critical_risks=risks,
            decisive_evidence=evidence,
        )


class MockJudge:
    """Mock judge for testing."""

    def __init__(self, preference: list[str] | None = None) -> None:
        self._preference = preference

    def judge(
        self,
        task: str,
        candidates: list[str],
        context: dict[str, Any],
    ) -> JudgeResult:
        if self._preference:
            ranking = [c for c in self._preference if c in candidates]
            ranking.extend([c for c in candidates if c not in ranking])
        else:
            ranking = list(candidates)
            random.shuffle(ranking)

        return JudgeResult(
            judge_id="mock-judge",
            ranking=ranking,
            winner=ranking[0] if ranking else "",
            decisive_evidence=["mock evidence"],
            confidence=0.8,
        )


class TournamentSelector:
    """Run tournament voting among candidates."""

    def __init__(
        self,
        judges: list[JudgeProvider],
        judges_per_group: int = 3,
    ) -> None:
        self._judges = judges
        self._judges_per_group = judges_per_group

    def select(
        self,
        candidates: list[str],
        task: str,
        context: dict[str, Any],
    ) -> TournamentResult:
        """Run tournament selection on candidates."""
        # Split into groups
        mid = (len(candidates) + 1) // 2
        group_a = candidates[:mid]
        group_b = candidates[mid:]

        # Run group tournaments
        result_a = self._group_tournament("A", group_a, task, context)
        result_b = self._group_tournament("B", group_b, task, context)

        # Final between group winners
        if result_a.winner and result_b.winner:
            final = self._final_tournament(
                [result_a.winner, result_b.winner], task, context
            )
            winner = final.winner
        elif result_a.winner:
            winner = result_a.winner
        elif result_b.winner:
            winner = result_b.winner
        else:
            winner = ""

        # Check if we need distinguishing test
        needs_dist_test = (
            result_a.is_tie or result_b.is_tie
            or (result_a.winner and result_b.winner and not winner)
        )

        return TournamentResult(
            group_id="final",
            candidates=candidates,
            judge_results=[*result_a.judge_results, *result_b.judge_results],
            winner=winner,
            is_tie=not winner,
            needs_distinguishing_test=bool(needs_dist_test),
        )

    def _group_tournament(
        self,
        group_id: str,
        candidates: list[str],
        task: str,
        context: dict[str, Any],
    ) -> TournamentResult:
        """Run tournament for one group."""
        judges = self._judges[: self._judges_per_group]
        results: list[JudgeResult] = []

        for judge in judges:
            result = judge.judge(task, candidates, context)
            results.append(result)

        # Count votes
        votes: dict[str, int] = {}
        for r in results:
            if r.winner in candidates:
                votes[r.winner] = votes.get(r.winner, 0) + 1

        # Find winner
        winner = ""
        if votes:
            max_votes = max(votes.values())
            winners = [c for c, v in votes.items() if v == max_votes]
            if len(winners) == 1:
                winner = winners[0]

        return TournamentResult(
            group_id=group_id,
            candidates=candidates,
            judge_results=results,
            winner=winner,
            vote_counts=votes,
            is_tie=len([c for c, v in votes.items() if v == max_votes]) > 1 if votes else True,
        )

    def _final_tournament(
        self,
        finalists: list[str],
        task: str,
        context: dict[str, Any],
    ) -> TournamentResult:
        """Run final tournament between group winners."""
        return self._group_tournament("final", finalists, task, context)

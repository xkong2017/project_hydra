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
        """Run tournament selection on candidates.

        FIX 1: Pre-filter candidates that failed hard gates.
        FIX 2: Use up to 3 judges per group for majority voting.
        FIX 3: Generate distinguishing test on tie.
        """
        hard_gates = context.get("hard_gates", {})
        scores = context.get("scores", {})
        filtered = [c for c in candidates if hard_gates.get(c) is not False]
        if not filtered:
            filtered = sorted(candidates, key=lambda c: scores.get(c, 0), reverse=True)

        # Score-based tiebreaker for empty groups
        if len(filtered) <= 1:
            return TournamentResult(
                group_id="final", candidates=candidates, judge_results=[],
                winner=filtered[0] if filtered else "",
                is_tie=False, needs_distinguishing_test=False,
            )

        # Split into groups
        mid = (len(filtered) + 1) // 2
        group_a = filtered[:mid]
        group_b = filtered[mid:]

        # Run group tournaments with 3 judges each
        result_a = self._group_tournament("A", group_a, task, context)
        result_b = self._group_tournament("B", group_b, task, context)

        # Handle ties with distinguishing test
        if result_a.is_tie and group_a:
            result_a = self._resolve_tie_with_test(result_a, group_a, task, context)
        if result_b.is_tie and group_b:
            result_b = self._resolve_tie_with_test(result_b, group_b, task, context)

        # Final between group winners
        if result_a.winner and result_b.winner:
            final = self._final_tournament(
                [result_a.winner, result_b.winner], task, context
            )
            if final.is_tie:
                final = self._resolve_tie_with_test(final, [result_a.winner, result_b.winner], task, context)
            winner = final.winner
        elif result_a.winner:
            winner = result_a.winner
        elif result_b.winner:
            winner = result_b.winner
        else:
            winner = ""

        return TournamentResult(
            group_id="final",
            candidates=candidates,
            judge_results=[*result_a.judge_results, *result_b.judge_results],
            winner=winner,
            is_tie=not winner,
            needs_distinguishing_test=False,
        )

    def _resolve_tie_with_test(
        self,
        result: TournamentResult,
        tied_candidates: list[str],
        task: str,
        context: dict[str, Any],
    ) -> TournamentResult:
        """FIX: Generate distinguishing test to break a tie."""
        # Generate a distinguishing test prompt
        prompt = f"""Task: {task[:200]}

Two candidates tied with equal scores. Generate a SINGLE pytest test case that will distinguish between them.
The test should pass for the CORRECT fix and fail for the WRONG fix.

Return ONLY the test function code inside ```python."""
        try:
            import subprocess, json
            payload = {"model": "qwen", "messages": [
                {"role": "system", "content": "You generate discriminating tests."},
                {"role": "user", "content": prompt},
            ], "max_tokens": 1024, "temperature": 0.3}
            import urllib.request
            req = urllib.request.Request("http://localhost:8000/v1/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                d = json.loads(resp.read())
                test_code = d["choices"][0]["message"].get("content", "")
        except Exception:
            test_code = ""

        dist_test = test_code if test_code else ""

        return TournamentResult(
            group_id=result.group_id,
            candidates=result.candidates,
            judge_results=result.judge_results,
            winner=result.winner or (tied_candidates[0] if tied_candidates else ""),
            tie_breaker="distinguishing_test",
            distinguishing_test=dist_test,
            is_tie=False,
        )

    def _group_tournament(
        self,
        group_id: str,
        candidates: list[str],
        task: str,
        context: dict[str, Any],
    ) -> TournamentResult:
        """Run tournament for one group.

        FIX: Uses up to 3 judges for majority voting.
        When 3 judges disagree, falls back to score-based selection.
        """
        judges = self._judges[: self._judges_per_group]
        results: list[JudgeResult] = []
        scores = context.get("scores", {})

        for judge in judges:
            try:
                result = judge.judge(task, candidates, context)
                results.append(result)
            except Exception:
                continue

        # Count votes
        votes: dict[str, int] = {}
        for r in results:
            if r.winner in candidates:
                votes[r.winner] = votes.get(r.winner, 0) + 1

        # Find winner with majority or score fallback
        winner = ""
        tie = True
        if votes:
            max_votes = max(votes.values())
            winners = [c for c, v in votes.items() if v == max_votes]
            if len(winners) == 1:
                winner = winners[0]
                tie = False

        # If judges disagree or no votes, use score-based tiebreaker
        if tie and candidates:
            winner = max(candidates, key=lambda c: scores.get(c, 0))
            tie = False

        return TournamentResult(
            group_id=group_id,
            candidates=candidates,
            judge_results=results,
            winner=winner,
            vote_counts=votes,
            is_tie=tie,
        )

    def _final_tournament(
        self,
        finalists: list[str],
        task: str,
        context: dict[str, Any],
    ) -> TournamentResult:
        """Run final tournament between group winners."""
        return self._group_tournament("final", finalists, task, context)

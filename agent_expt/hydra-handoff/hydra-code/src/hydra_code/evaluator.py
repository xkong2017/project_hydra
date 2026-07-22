"""Candidate evaluation: test matrix, hard gates, and scoring."""

from __future__ import annotations

import asyncio
import shlex
import time
from pathlib import Path

from .models import (
    CandidateResult,
    CandidateScore,
    HardGateResult,
    ScoreWeights,
    TestMatrix,
    TestMatrixEntry,
    TestResult,
    TestVerdict,
)

FORBIDDEN_FILES = {
    ".env",
    ".gitconfig",
    ".git-credentials",
}


class CandidateEvaluator:
    """Evaluate candidates against tests and hard gates."""

    def __init__(
        self,
        weights: ScoreWeights | None = None,
        test_timeout: int = 120,
        max_test_concurrency: int | None = None,
    ) -> None:
        self.weights = weights or ScoreWeights()
        self.test_timeout = test_timeout
        self.max_test_concurrency = max_test_concurrency

    async def run_test_matrix(
        self,
        candidates: dict[str, CandidateResult],
        test_commands: list[str],
        base_sha: str,
    ) -> TestMatrix:
        """Run each test against each candidate concurrently."""
        matrix = TestMatrix()
        matrix.candidates = {cid: res.role.value for cid, res in candidates.items()}
        matrix.tests = {f"cmd-{i}": cmd for i, cmd in enumerate(test_commands)}

        # Build all test jobs
        jobs: list[tuple[str, asyncio.Task]] = []
        for candidate_id, result in candidates.items():
            for test_id, command in matrix.tests.items():
                coro = self._run_single_test_async(
                    candidate_id, result, test_id, command
                )
                job_key = f"{candidate_id}:{test_id}"
                jobs.append((job_key, coro))  # type: ignore[arg-type]

        # Run with optional concurrency limit
        if self.max_test_concurrency and self.max_test_concurrency > 1:
            semaphore = asyncio.Semaphore(self.max_test_concurrency)

            async def _limited(coro: asyncio.Task) -> TestMatrixEntry:
                async with semaphore:
                    return await coro

            entries = await asyncio.gather(
                *[_limited(c) for _, c in jobs]
            )
        else:
            entries = await asyncio.gather(
                *[c for _, c in jobs]
            )

        matrix.results = list(entries)
        return matrix

    async def _run_single_test_async(
        self,
        candidate_id: str,
        result: CandidateResult,
        test_id: str,
        command: str,
    ) -> TestMatrixEntry:
        """Run one test against one candidate using async subprocess."""
        start = time.monotonic()
        stdout_path = result.worktree_path / f"test_{test_id}.out"
        stderr_path = result.worktree_path / f"test_{test_id}.err"

        args = shlex.split(command)

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(result.worktree_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.test_timeout,
                )
                duration = time.monotonic() - start
                proc_rc = proc.returncode or 0
                verdict = TestVerdict.PASS if proc_rc == 0 else TestVerdict.FAIL
                exit_code = proc_rc

                stdout_path.write_bytes(stdout_bytes)
                stderr_path.write_bytes(stderr_bytes)

            except TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                duration = self.test_timeout
                verdict = TestVerdict.TIMEOUT
                exit_code = -1

        except (OSError, FileNotFoundError):
            duration = time.monotonic() - start
            verdict = TestVerdict.FAIL
            exit_code = -1

        test_result = TestResult(
            candidate_id=candidate_id,
            test_id=test_id,
            command=command,
            exit_code=exit_code,
            duration_seconds=duration,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            verdict=verdict,
        )

        return TestMatrixEntry(
            candidate_id=candidate_id,
            test_id=test_id,
            results=[test_result],
            verdict=verdict,
        )

    def check_hard_gates(
        self,
        candidate: CandidateResult,
        matrix: TestMatrix,
        base_sha: str,
    ) -> HardGateResult:
        """Apply hard rejection gates (sync version, checks without git subprocess)."""
        reasons: list[str] = []

        if not candidate.patch_path or not candidate.patch_path.exists():
            reasons.append("Patch cannot be extracted")

        candidate_results = [
            r for r in matrix.results if r.candidate_id == candidate.candidate_id
        ]
        for r in candidate_results:
            if r.verdict == TestVerdict.FAIL:
                reasons.append(f"Required test {r.test_id} failed")

        return HardGateResult(
            candidate_id=candidate.candidate_id,
            passed=len(reasons) == 0,
            rejection_reasons=reasons,
        )

    async def check_hard_gates_async(
        self,
        candidate: CandidateResult,
        matrix: TestMatrix,
        base_sha: str,
    ) -> HardGateResult:
        """Apply hard rejection gates to a candidate (async version)."""
        reasons: list[str] = []

        if not candidate.patch_path or not candidate.patch_path.exists():
            reasons.append("Patch cannot be extracted")

        candidate_results = [
            r for r in matrix.results if r.candidate_id == candidate.candidate_id
        ]
        for r in candidate_results:
            if r.verdict == TestVerdict.FAIL:
                reasons.append(f"Required test {r.test_id} failed")
        # Check forbidden files
        if candidate.worktree_path.exists():
            try:
                proc = await asyncio.create_subprocess_exec(
                    "git", "diff", "--name-only", base_sha, "HEAD",
                    cwd=str(candidate.worktree_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_bytes, _ = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=30,
                )
                if proc.returncode == 0:
                    changed_files = stdout_bytes.decode().strip().split("\n")
                    for f in changed_files:
                        if Path(f).name in FORBIDDEN_FILES:
                            reasons.append(f"Modified forbidden file: {f}")
            except (TimeoutError, ProcessLookupError):
                pass

        return HardGateResult(
            candidate_id=candidate.candidate_id,
            passed=len(reasons) == 0,
            rejection_reasons=reasons,
        )

    def compute_scores(
        self,
        candidates: dict[str, CandidateResult],
        matrix: TestMatrix,
        gates: dict[str, HardGateResult],
    ) -> dict[str, CandidateScore]:
        """Compute evidence-based scores for all candidates."""
        scores: dict[str, CandidateScore] = {}

        for candidate_id, result in candidates.items():
            gate = gates.get(candidate_id)
            if gate and not gate.passed:
                scores[candidate_id] = CandidateScore(
                    candidate_id=candidate_id,
                    hard_gate_passed=False,
                    hard_gate_reasons=gate.rejection_reasons,
                )
                continue

            candidate_results = [
                r for r in matrix.results if r.candidate_id == candidate_id
            ]

            # Calculate component scores
            issue_pass = sum(
                1 for r in candidate_results if r.test_id.startswith("issue-") and r.verdict == TestVerdict.PASS
            )
            issue_total = sum(1 for r in candidate_results if r.test_id.startswith("issue-"))
            issue_score = issue_pass / issue_total if issue_total else 0.0

            reg_pass = sum(
                1 for r in candidate_results if r.test_id.startswith("reg-") and r.verdict == TestVerdict.PASS
            )
            reg_total = sum(1 for r in candidate_results if r.test_id.startswith("reg-"))
            reg_score = reg_pass / reg_total if reg_total else 0.0

            # Build/lint score from all tests
            total_pass = sum(1 for r in candidate_results if r.verdict == TestVerdict.PASS)
            total = len(candidate_results)
            build_score = total_pass / total if total else 0.0

            # Minimality: smaller diffs score higher
            minimality = 1.0
            if result.trajectory and result.trajectory.diff_stats:
                insertions = result.trajectory.diff_stats.get("insertions", 0)
                if insertions > 100:
                    minimality = 0.5

            total_score = (
                issue_score * self.weights.issue_specific_tests
                + reg_score * self.weights.regression_tests
                + build_score * self.weights.build_lint_type
                + 0.0 * self.weights.generated_edge_tests
                + minimality * self.weights.scope_minimality
                + 1.0 * self.weights.static_risk
            )

            scores[candidate_id] = CandidateScore(
                candidate_id=candidate_id,
                total_score=total_score,
                issue_specific_score=issue_score,
                regression_score=reg_score,
                build_lint_score=build_score,
                minimality_score=minimality,
                hard_gate_passed=True,
            )

        return scores

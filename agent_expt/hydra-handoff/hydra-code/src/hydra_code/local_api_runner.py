"""Local Qwen API runner — drop-in replacement for claude_runner.py.

Replaces claude -p subprocess with httpx calls to localhost:8000/v1.
Preserves retry, timeout, and trajectory parsing contracts.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import CandidateResult, CandidateRole, CandidateStatus, TrajectorySummary


API_BASE = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
API_MODEL = os.environ.get("VLLM_MODEL", "qwen")


class RetryableError(Exception):
    pass


class FatalError(Exception):
    pass


@dataclass
class RunnerConfig:
    max_turns: int = 1
    timeout_seconds: int = 600
    max_retries: int = 2
    retry_base_delay: float = 2.0
    retry_max_delay: float = 30.0
    max_tokens: int = 8192
    temperature: float = 0.3


class LocalApiRunner:
    """Runs local Qwen model via HTTP API instead of claude CLI."""

    def __init__(self, config: RunnerConfig | None = None) -> None:
        self.config = config or RunnerConfig()

    def _is_retryable(self, error: str) -> bool:
        retryable = ["429", "econnreset", "timeout", "capacity", "500", "503"]
        return any(pat in error.lower() for pat in retryable)

    def _extract_code_fixes(self, content: str, reasoning: str) -> list[str]:
        """Extract code fixes from model output. Returns list of file contents."""
        fixes = []
        for text in [content, reasoning]:
            in_code = False
            code_lines = []
            for line in text.split("\n"):
                s = line.strip()
                if s.startswith("```python"):
                    in_code = True
                    code_lines = []
                    continue
                if s.startswith("```") and in_code:
                    if code_lines:
                        fixes.append("\n".join(code_lines))
                    in_code = False
                    code_lines = []
                    continue
                if in_code:
                    code_lines.append(line)
            if in_code and code_lines:
                fixes.append("\n".join(code_lines))
        return fixes

    def _parse_trajectory_from_text(self, text: str, worktree_path: Path) -> TrajectorySummary:
        """Parse raw model output into a TrajectorySummary."""
        files_mentioned = []
        commands = []
        errors = []

        for line in text.split("\n"):
            fp_match = re.search(r"(?:file|path)[=:>\-]\s*['\"]?([^'\"\s]+\.py)", line)
            if fp_match:
                fp = fp_match.group(1)
                if fp not in files_mentioned:
                    files_mentioned.append(fp)

        diff_stats: dict[str, int] = {}
        try:
            from .worktrees import count_diff_stats
            diff_stats = count_diff_stats(worktree_path, "HEAD~1")
        except Exception:
            diff_stats = {"files_changed": len(files_mentioned), "insertions": 0, "deletions": 0}

        return TrajectorySummary(
            candidate_id="",
            completion_status="completed",
            task_interpretation=text[:200],
            relevant_files=files_mentioned,
            commands_executed=[],
            tests_run=[],
            changes=[f"Fixed: {f}" for f in files_mentioned],
            diff_stats=diff_stats,
            failed_approaches=[],
            known_risks=[],
            self_confidence=0.6,
        )

    async def _call_api(self, prompt: str, system_prompt: str = "") -> tuple[str, str, str]:
        """Call local Qwen API. Returns (content, reasoning, finish_reason)."""
        import httpx

        payload = {
            "model": API_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt or "You are an expert software engineer fixing bugs. Edit the code to fix the issue. Return ONLY the corrected file inside ```python."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }

        async with httpx.AsyncClient(timeout=self.config.timeout_seconds + 10) as client:
            try:
                resp = await client.post(
                    f"{API_BASE}/chat/completions",
                    json=payload,
                    timeout=self.config.timeout_seconds + 10,
                )
                resp.raise_for_status()
                data = resp.json()
                msg = data["choices"][0]["message"]
                content = msg.get("content") or ""
                reasoning = msg.get("reasoning") or ""
                finish = data["choices"][0].get("finish_reason", "")
                return (content, reasoning, finish)
            except httpx.TimeoutException:
                return ("", "", "timeout")
            except Exception as e:
                return ("", "", f"error: {e}")

    async def _extract_trajectory(self, content: str, reasoning: str) -> dict:
        """FIX 1: Two-stage hierarchical distillation.

        Stage 1: Extract ALL observations (raw extraction).
        Stage 2: Condense observations into structured summary.
        """
        full_text = content + "\n" + reasoning
        if len(full_text) < 100:
            return {"root_cause_hypotheses": [], "evidence_for": [], "evidence_against": [],
                    "useful_discoveries": [], "failed_approaches": [], "remaining_uncertainty": []}

        # Stage 1: Raw extraction — gather all observations
        stage1_prompt = f"""Extract every observation, insight, and finding from this bug-fix attempt.
Be exhaustive — list everything the attempt discovered, even if it seems minor.

Return JSON with:
{{"observations":["each distinct observation"]}}

Fix attempt:
{full_text[:3000]}"""
        c1, r1, _ = await self._call_api(stage1_prompt, "You extract raw observations from debugging sessions. Be exhaustive.")
        raw_obs_text = c1 or r1

        # Stage 2: Condensation — distill observations into structured summary
        stage2_prompt = f"""Condense these observations into a structured analysis.

Return JSON with these fields:
{{
  "root_cause_hypotheses": ["2-3 most likely root causes, ranked by plausibility"],
  "evidence_for": ["observations that SUPPORT each hypothesis"],
  "evidence_against": ["observations that CONTRADICT each hypothesis"],
  "useful_discoveries": ["important things learned that could help other approaches"],
  "failed_approaches": ["specific approaches attempted that did NOT work and why"],
  "remaining_uncertainty": ["what is still unknown or unclear"]
}}

Raw observations:
{raw_obs_text[:2000]}

Return ONLY valid JSON."""
        c2, r2, _ = await self._call_api(stage2_prompt, "You synthesize structured analysis from observations. Return only valid JSON.")

        import json as j, re
        for text in [c2, r2]:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    return j.loads(m.group())
                except j.JSONDecodeError:
                    pass
        return {"root_cause_hypotheses": [], "evidence_for": [], "evidence_against": [],
                "useful_discoveries": [], "failed_approaches": [], "remaining_uncertainty": []}

    async def run(
        self,
        prompt: str,
        worktree_path: Path,
        candidate_id: str,
        role: CandidateRole | None,
        output_dir: Path,
    ) -> CandidateResult:
        """Run a single Qwen API call — matches claude_runner's interface."""
        start_time = time.monotonic()
        output_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = output_dir / f"{candidate_id}.stdout.log"
        stderr_path = output_dir / f"{candidate_id}.stderr.log"

        last_exception: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                content, reasoning, finish = await self._call_api(prompt)
                duration = time.monotonic() - start_time

                stdout_path.write_text(
                    json.dumps({"content": content, "reasoning": reasoning, "finish_reason": finish}, indent=2)
                )

                if "error" in finish:
                    stderr_path.write_text(finish)
                    if attempt < self.config.max_retries and self._is_retryable(finish):
                        await asyncio.sleep(self.config.retry_base_delay * (2 ** attempt))
                        continue
                    return CandidateResult(
                        candidate_id=candidate_id, role=role or CandidateRole.MINIMAL,
                        status=CandidateStatus.FAILED, worktree_path=worktree_path,
                        duration_seconds=duration, exit_code=1,
                        stdout_path=stdout_path, stderr_path=stderr_path,
                        error=finish[:500],
                    )

                # Check content=null (reasoning consumed all tokens)
                if not content.strip() and reasoning.strip():
                    stderr_path.write_text("content=null: reasoning consumed token budget")
                    if attempt < self.config.max_retries:
                        # Retry with higher max_tokens
                        self.config.max_tokens = min(self.config.max_tokens * 2, 32768)
                        await asyncio.sleep(self.config.retry_base_delay)
                        continue
                    return CandidateResult(
                        candidate_id=candidate_id, role=role or CandidateRole.MINIMAL,
                        status=CandidateStatus.FAILED, worktree_path=worktree_path,
                        duration_seconds=duration, exit_code=1,
                        stdout_path=stdout_path, stderr_path=stderr_path,
                        error=f"content=null after {self.config.max_retries} retries",
                    )

                # Check that fixes can be extracted
                fixes = self._extract_code_fixes(content, reasoning)
                if not fixes:
                    stderr_path.write_text("No code blocks found in output")
                    if attempt < self.config.max_retries:
                        await asyncio.sleep(self.config.retry_base_delay * (2 ** attempt))
                        continue
                    return CandidateResult(
                        candidate_id=candidate_id, role=role or CandidateRole.MINIMAL,
                        status=CandidateStatus.FAILED, worktree_path=worktree_path,
                        duration_seconds=duration, exit_code=1,
                        stdout_path=stdout_path, stderr_path=stderr_path,
                        error="no code blocks in response",
                    )

                # Write extracted fixes to worktree
                for fix_content in fixes:
                    target = find_target_file(fix_content, worktree_path)
                    if target:
                        target.write_text(fix_content)
                        stderr_path.write_text(f"Applied fix to: {target}")

                # Trajectory extraction disabled by default — experiments showed
                # Qwen3 trajectory summaries add noise vs signal, degrading refinement.
                # The test-feedback loop on original source code is more effective.
                trajectory = self._parse_trajectory_from_text(
                    content + "\n" + reasoning, worktree_path
                )

                return CandidateResult(
                    candidate_id=candidate_id, role=role or CandidateRole.MINIMAL,
                    status=CandidateStatus.COMPLETED, worktree_path=worktree_path,
                    duration_seconds=duration, exit_code=0,
                    stdout_path=stdout_path, stderr_path=stderr_path,
                    trajectory=trajectory,
                )

            except TimeoutError:
                duration = time.monotonic() - start_time
                return CandidateResult(
                    candidate_id=candidate_id, role=role or CandidateRole.MINIMAL,
                    status=CandidateStatus.TIMEOUT, worktree_path=worktree_path,
                    duration_seconds=duration, exit_code=-1,
                    stdout_path=stdout_path, stderr_path=stderr_path,
                    error="timeout exceeded",
                )
            except Exception as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_base_delay * (2 ** attempt))
                    continue
                raise

        raise last_exception or FatalError("Unknown failure")


def find_target_file(fix_content: str, worktree_path: Path) -> Path | None:
    """Find which file in the worktree the fix applies to."""
    lines = fix_content.split("\n")
    for line in lines[:20]:
        m = re.match(r"#\s*(?:FILE|file):\s*(.+)", line)
        if m:
            candidate = worktree_path / m.group(1).strip()
            if candidate.exists():
                return candidate
        m = re.match(r"#\s*(\S+\.py)", line)
        if m:
            candidate = worktree_path / m.group(1)
            if candidate.exists():
                return candidate

    return find_source_file(fix_content, worktree_path)


def find_source_file(fix_content: str, worktree_path: Path) -> Path | None:
    """Try to find the file by looking at first import/def/class in fix."""
    py_files = sorted(worktree_path.rglob("*.py"))
    if not py_files:
        return None
    return py_files[0]

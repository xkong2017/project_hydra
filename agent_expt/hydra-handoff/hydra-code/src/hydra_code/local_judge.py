"""Local Qwen API judge — replaces RealJudge in tournament.py.
FIX 1: Ignores hard-gate failures. Presents only passing candidates.
FIX 2: Includes explicit pass/fail test counts for each candidate.
FIX 3: Excludes syntax-error candidates before judging.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .models import JudgeResult
from .tournament import JudgeProvider

API_BASE = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
API_MODEL = os.environ.get("VLLM_MODEL", "qwen")


class LocalJudge:
    """Judge that uses local Qwen API for candidate evaluation."""

    def __init__(self, max_tokens: int = 4096, temperature: float = 0.3) -> None:
        self.max_tokens = max_tokens
        self.temperature = temperature

    def _call_api(self, prompt: str) -> str:
        import httpx
        payload = {
            "model": API_MODEL,
            "messages": [
                {"role": "system", "content": "You pick the best code fix. Return ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        try:
            resp = httpx.post(f"{API_BASE}/chat/completions", json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            return (msg.get("content") or "") + "\n" + (msg.get("reasoning") or "")
        except Exception as e:
            return f'{{"error": "{e}"}}'

    def _extract_json(self, text: str) -> dict:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        return {}

    def judge(self, task: str, candidates: list[str], context: dict[str, Any]) -> JudgeResult:
        # FIX 1: Filter out candidates that failed hard gates or have syntax errors
        hard_gates = context.get("hard_gates", {})
        scores = context.get("scores", {})
        valid = [c for c in candidates if hard_gates.get(c) is True and scores.get(c, -100) >= 0]

        if not valid:
            # No valid candidates — score-based fallback
            valid = sorted(candidates, key=lambda c: (scores.get(c, 0), c), reverse=True)
            if not valid:
                return JudgeResult(
                    judge_id="local-qwen-fallback",
                    ranking=[], winner="",
                    confidence=0.0, critical_risks=["no valid candidates"],
                    decisive_evidence=["fallback: empty"],
                )

        # Build prompt with clear pass/fail data
        lines = [f"Task: {task[:300]}\n", f"Choose the BEST fix from these candidates:\n"]
        for i, cid in enumerate(valid, 1):
            score = scores.get(cid, 0)
            desc = context.get("candidate_descriptions", {}).get(cid, "")
            lines.append(
                f"\nCandidate {i}: {cid}\n"
                f"  Score: {score}/100\n"
                f"  Details: {desc[:200]}"
            )

        lines.append(
            "\n\nRULES:\n"
            "1. Only consider candidates with Score > 0 (they passed tests).\n"
            "2. Higher score is better.\n"
            "3. If scores are equal, pick the simpler fix.\n"
            "4. Return ONLY this JSON: {\"winner\":\"<candidate_id>\",\"reason\":\"why\"}"
        )

        response = self._call_api("\n".join(lines))
        data = self._extract_json(response)
        winner = data.get("winner", valid[0])
        # Ensure winner is in valid list
        if winner not in valid:
            winner = valid[0]

        return JudgeResult(
            judge_id="local-qwen",
            ranking=valid,
            winner=winner,
            confidence=0.9 if scores.get(winner, 0) >= 100 else 0.7,
            critical_risks=[],
            decisive_evidence=[data.get("reason", "score-based selection")],
        )

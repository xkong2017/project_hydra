"""Trajectory summary validation and repair."""

from __future__ import annotations

import json
import re
from typing import Any

from .models import TrajectorySummary

REQUIRED_FIELDS = {
    "candidate_id",
    "completion_status",
    "task_interpretation",
}

OPTIONAL_FIELDS = {
    "root_cause_hypotheses",
    "evidence_for",
    "evidence_against",
    "relevant_files",
    "relevant_symbols",
    "changes",
    "commands_executed",
    "tests_run",
    "test_results",
    "remaining_failures",
    "generated_tests",
    "diff_stats",
    "known_risks",
    "useful_discoveries",
    "failed_approaches",
    "recommended_next_step",
    "self_confidence",
}


def extract_json(text: str) -> str | None:
    """Extract JSON from text that may contain markdown fences or prose."""
    text = text.strip()

    # Try direct parse first
    if text.startswith("{"):
        return text

    # Try markdown fences
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    # Try to find JSON object in text
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        return json_match.group(0)

    return None


def validate_trajectory(data: dict[str, Any]) -> list[str]:
    """Validate trajectory data against schema. Returns list of issues."""
    issues: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in data:
            issues.append(f"Missing required field: {field}")

    # Type checks
    if "root_cause_hypotheses" in data and not isinstance(data["root_cause_hypotheses"], list):
        issues.append("root_cause_hypotheses must be a list")
    if "self_confidence" in data:
        conf = data["self_confidence"]
        if not isinstance(conf, (int, float)):
            issues.append("self_confidence must be numeric")

    return issues


def repair_trajectory(raw_text: str) -> dict[str, Any] | None:
    """Attempt to extract and repair trajectory JSON."""
    json_str = extract_json(raw_text)
    if json_str is None:
        return None

    try:
        data: dict[str, Any] = json.loads(json_str)
    except json.JSONDecodeError:
        # Try common repair: trailing commas
        repaired = re.sub(r",\s*([}\]])", r"\1", json_str)
        try:
            data: dict[str, Any] = json.loads(repaired)
        except json.JSONDecodeError:
            return None

    # Fill missing required fields with unknown
    for field in REQUIRED_FIELDS:
        if field not in data:
            data[field] = "unknown"

    return data


def parse_trajectory(raw_text: str, candidate_id: str) -> TrajectorySummary:
    """Parse raw trajectory output into a TrajectorySummary."""
    data = repair_trajectory(raw_text)

    if data is None:
        return TrajectorySummary(
            candidate_id=candidate_id,
            completion_status="failed",
            task_interpretation="unknown",
        )

    return TrajectorySummary(
        candidate_id=data.get("candidate_id", candidate_id),
        completion_status=data.get("completion_status", "unknown"),
        task_interpretation=data.get("task_interpretation", "unknown"),
        root_cause_hypotheses=data.get("root_cause_hypotheses", []),
        evidence_for=data.get("evidence_for", []),
        evidence_against=data.get("evidence_against", []),
        relevant_files=data.get("relevant_files", []),
        relevant_symbols=data.get("relevant_symbols", []),
        changes=data.get("changes", []),
        commands_executed=data.get("commands_executed", []),
        tests_run=data.get("tests_run", []),
        test_results=data.get("test_results", []),
        remaining_failures=data.get("remaining_failures", []),
        generated_tests=data.get("generated_tests", []),
        diff_stats=data.get("diff_stats", {}),
        known_risks=data.get("known_risks", []),
        useful_discoveries=data.get("useful_discoveries", []),
        failed_approaches=data.get("failed_approaches", []),
        recommended_next_step=data.get("recommended_next_step", ""),
        self_confidence=float(data.get("self_confidence", 0.0)),
    )

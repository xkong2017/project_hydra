"""Final reporting for HydraCode-6."""

from __future__ import annotations

from pathlib import Path

from .models import (
    CandidateResult,
    CandidateScore,
    HardGateResult,
    TestMatrix,
    TestVerdict,
    TournamentResult,
)
from .utils import atomic_write_text, redact_secrets


def generate_report(
    run_id: str,
    task: str,
    candidates: dict[str, CandidateResult],
    scores: dict[str, CandidateScore],
    gates: dict[str, HardGateResult],
    matrix: TestMatrix | None,
    tournament: TournamentResult | None,
    final_candidate: str | None,
    started_at: str,
    completed_at: str,
    output_dir: Path,
) -> Path:
    """Generate the final validation report."""
    report = f"""# HydraCode Run Report

Run ID: {run_id}
Task: {task}
Started: {started_at}
Completed: {completed_at}

## Summary

Total candidates: {len(candidates)}
Passed gates: {sum(1 for g in gates.values() if g.passed)}
Rejected: {sum(1 for g in gates.values() if not g.passed)}
Final selection: {final_candidate or "none"}
"""

    # Candidate results
    report += "\n## Candidate Results\n"
    for cid, result in candidates.items():
        score = scores.get(cid)
        gate = gates.get(cid)
        report += f"""
### {cid} ({result.role.value})
- Status: {result.status.value}
- Duration: {result.duration_seconds:.1f}s
- Exit code: {result.exit_code}
- Score: {score.total_score if score else 0.0:.3f} ({"gate passed" if gate and gate.passed else "REJECTED"})
"""
        if gate and not gate.passed:
            report += "  Rejection reasons:\n"
            for reason in gate.rejection_reasons:
                report += f"  - {reason}\n"

    # Tournament results
    if tournament:
        report += "\n## Tournament\n"
        report += f"Winner: {tournament.winner}\n"
        report += f"Was tie: {tournament.is_tie}\n"
        report += f"Needs distinguishing test: {tournament.needs_distinguishing_test}\n"

    # Test matrix summary
    if matrix:
        report += "\n## Test Matrix Summary\n"
        pass_count = sum(1 for r in matrix.results if r.verdict == TestVerdict.PASS)
        total = len(matrix.results)
        report += f"Passed: {pass_count}/{total}\n"

    # Redact secrets
    report = redact_secrets(report)

    report_path = output_dir / "report.md"
    atomic_write_text(report_path, report)
    return report_path

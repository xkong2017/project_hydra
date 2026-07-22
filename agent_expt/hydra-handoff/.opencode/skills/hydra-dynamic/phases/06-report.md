# Phase 6: Report — Audit Trail & Cleanup

**Goal**: Generate a human-readable audit report and clean up worktrees.

## Steps

### 1. Generate report
Collect all data and write `.hydra/runs/$run_id/report.md`:

```markdown
# HydraCode Dynamic Workflow Report

Run ID: hydra-1234567890
Task: Fix pagination off-by-one bug
Date: 2026-07-22

## Summary
- Status: Completed
- Winner: candidate-2
- Score: 0.92
- Rubric score: 0.84
- Wall time: 187.3s
- Agent count: 4 (adaptive)
- Candidates evaluated: 4 (3 completed, 1 timeout, 0 cancelled due to early convergence)

## Tournament Results
| Candidate | Constraint               | Score | Rubric | Winner |
|-----------|--------------------------|-------|--------|--------|
| cand-2    | Handle all edge cases    | 0.92  | 0.84   | ★ WIN  |
| cand-0    | Minimal diff (≤3 lines)  | 0.87  | 0.80   |        |
| cand-4    | Test-driven development  | 0.78  | 0.72   |        |

## Rubric Breakdown (Winner: candidate-2)
| Criterion       | Score | Weight | Contribution |
|-----------------|-------|--------|-------------|
| Correctness     | 5/5   | 30%    | 0.30        |
| Minimality      | 4/5   | 25%    | 0.20        |
| Robustness      | 3/5   | 20%    | 0.12        |
| Maintainability | 4/5   | 15%    | 0.12        |
| Test quality    | 3/5   | 10%    | 0.06        |
| **Total**       |       |        | **0.84**    |

## Test Matrix
| Test              | cand-0 | cand-2 | cand-4 |
|-------------------|--------|--------|--------|
| test_pagination   | PASS   | PASS   | PASS   |
| test_regression   | PASS   | PASS   | FAIL   |
| ruff check        | PASS   | PASS   | PASS   |
| mypy              | FAIL   | PASS   | PASS   |

## Winner Patch Summary
- Files changed: 1 (src/pagination.py)
- Insertions: 5
- Deletions: 3
- Root cause: Off-by-one in page offset calculation

## Generated Tests
- test_pagination_edge_cases.py (candidate-4) — VALID, harvested
- test_boundary_conditions.py (candidate-2) — PASSES_ON_BASE, rejected

## Risks
- None identified (judge confirmed safe)
```

### 2. Print report
```
$ cat .hydra/runs/$run_id/report.md
```

### 3. Clean up worktrees (unless --keep-worktrees)
```bash
git worktree prune
rm -rf ".hydra/worktrees/$run_id"
```

### 4. Final state
Save final state to `run.json`:
```json
{
  "phase": "complete",
  "winner": "candidate-2",
  "winning_patch": "patches/candidate-2.patch",
  "wall_time_seconds": 187.3,
  ...rest of state
}
```

### 5. Output summary
```
===== WORKFLOW COMPLETE =====
Task: Fix pagination off-by-one bug
Winner: candidate-2 (handle edge cases constraint)
Score: 0.92
Time: 3m 7s
Patch: .hydra/runs/hydra-1234567890/patches/candidate-2.patch
Report: .hydra/runs/hydra-1234567890/report.md
```

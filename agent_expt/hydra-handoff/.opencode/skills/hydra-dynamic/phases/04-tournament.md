# Phase 4: Tournament — Select the Winner

**Goal**: Score top candidates with a structured rubric and select the winner. Uses 1 judge by default; escalates to 2 only if scores are close.

## Steps

### 1. Identify top candidates
Take the top candidates by score (those that passed hard gates):
```bash
python -m hydra_code tournament ".hydra/runs/$run_id/scores.json" --output ".hydra/runs/$run_id/tournament.json"
```

If the Python engine is unavailable, do this manually.

### 2. Score with rubric (single judge)
Spawn 1 judge sub-agent. It receives:
- The task description
- Each candidate's trajectory summary + diff stats + test results
- The scoring breakdown

The judge applies this rubric, scoring each candidate 1-5:

| Criterion | Weight | 1 (Poor) | 3 (Good) | 5 (Excellent) |
|-----------|--------|----------|----------|---------------|
| **Correctness** | 30% | Fails tests | All tests pass | All tests pass + edge cases verified |
| **Minimality** | 25% | Changes 20+ lines | Changes 5-10 lines | Changes < 5 lines |
| **Robustness** | 20% | No edge case handling | Handles obvious edge cases | Handles null/empty/boundary/error |
| **Maintainability** | 15% | Cryptic diff | Clear intent | Self-documenting, matches codebase style |
| **Test quality** | 10% | No new tests or weakened tests | 1 new test | 2+ new tests covering edge cases |

Final score = sum of (criterion_score / 5 * weight).

The judge returns a structured verdict:
```json
{
  "rubric_scores": {
    "candidate-2": {"correctness": 5, "minimality": 4, "robustness": 3, "maintainability": 4, "test_quality": 3, "total": 0.84},
    "candidate-0": {"correctness": 5, "minimality": 5, "robustness": 2, "maintainability": 5, "test_quality": 1, "total": 0.80}
  },
  "winner": "candidate-2",
  "confidence": 0.84,
  "decisive_evidence": ["candidate-2 passes all tests with minimal diff and handles edge cases"],
  "critical_risks": []
}
```

### 3. Escalate if close
If the top two candidates' rubric totals are within 10% of each other, spawn a second judge for a tiebreak. Otherwise, single judge verdict stands.

### 4. Aggregate
- Take the highest rubric total from the judge (or average of 2 judges if escalated)
- Save results to `.hydra/runs/$run_id/tournament.json`

### 5. Report
```
Tournament complete: candidate-2 wins (rubric score 0.84)
  Correctness:  5/5  (30% weight)
  Minimality:   4/5  (25% weight)
  Robustness:   3/5  (20% weight)
  Maintainability: 4/5 (15% weight)
  Test quality: 3/5  (10% weight)
  ---
  Total: 0.84
```

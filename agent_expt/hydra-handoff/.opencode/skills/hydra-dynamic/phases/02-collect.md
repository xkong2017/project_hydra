# Phase 2: Collect — Gather Results from Agents

**Goal**: Collect trajectory summaries, patches, and tests from all completed sub-agents.

## Steps

### 1. Collect trajectories
For each candidate that completed:
- Read `.hydra/runs/$run_id/trajectories/$candidate_id.json`
- Parse into structured format
- Note any parsing failures

### 2. Extract patches
For each candidate:
- Read `.hydra/runs/$run_id/patches/$candidate_id.patch`
- Record diff stats (insertions, deletions, files changed)
- Note candidates with no patch

### 3. Harvest tests
For each candidate, check for new/modified test files in their worktree:
```bash
git diff --name-only HEAD
```
- Identify test files (containing "test" in name)
- Check for test weakening patterns (assert True, @pytest.mark.skip, etc.)
- Deduplicate across candidates

### 4. Update run state
```json
{
  "phase": "collect",
  "candidates": {
    "candidate-0": {"status": "completed", "patch": "patches/candidate-0.patch", "trajectory": "trajectories/candidate-0.json", "duration_seconds": 45},
    "candidate-1": {"status": "failed", "error": "timeout"},
    ...
  }
}
```

### 5. Report collection summary
Print a summary:
```
Completed: 5/6 candidates
  candidate-0: +12 -3 lines, 8 tests ran, 2 new tests
  candidate-1: TIMEOUT
  candidate-2: +5 -1 lines, 3 tests ran, 0 new tests
  ...
```

# Phase 5: Refine — Deepen the Winning Fix (optional)

**Goal**: Optionally refine the winning candidate's fix — broaden scope, add edge cases, improve testing, or address judge concerns.

## When to run
- Always for `deep` mode
- Skip for `fast` mode
- Optional for `standard` mode (skip if winner scored > 0.85 with high confidence)

## Steps

### 1. Load the winning patch
```bash
winner=$(python -c "import json; print(json.load(open('.hydra/runs/$run_id/tournament.json'))['winner'])")
patch_file=".hydra/runs/$run_id/patches/$winner.patch"
```

### 2. Apply the winning patch to the original worktree
```bash
wt_path=".hydra/worktrees/$run_id/$winner-refined"
git worktree add "$wt_path" HEAD
cd "$wt_path"
git apply "$OLDPWD/$patch_file"
```

### 3. Spawn a refinement agent
Spawn a sub-agent for refinement. Give it:
- The original task
- The winning patch
- All judge feedback
- The tournament results
- Instructions to: improve the fix, add edge case handling, strengthen tests, keep the same or smaller scope

### 4. Collect the refined patch
```bash
git diff HEAD > ".hydra/runs/$run_id/patches/$winner-refined.patch"
```

### 5. Re-validate
Run the full test matrix against the refined patch to ensure no regressions:
```bash
pytest -q
ruff check .
mypy . --ignore-missing-imports 2>/dev/null
```
If any check fails, revert to original winning patch.

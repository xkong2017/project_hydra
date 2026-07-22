# Phase 3: Evaluate — Test Matrix & Scoring

**Goal**: Run each candidate's fix against the full test suite, compute granular scores, and apply hard gates.

## Steps

### 1. Build the test matrix
For each candidate, run the test suite in its worktree:

```bash
# For each candidate worktree
cd .hydra/worktrees/$run_id/candidate-$i
pytest -q --json-report 2>/dev/null || pytest -q 2>&1 | tail -5
pytest --coverage 2>/dev/null  # if available
```

Also run lint and type checks:
```bash
ruff check . 2>/dev/null                            # lint
mypy . --ignore-missing-imports 2>/dev/null          # type check (Python)
# or use project-native equivalents (tsc, cargo check, etc.)
```

Capture granular results per candidate:
```
                   | test_a | test_b | test_c | ruff | mypy | diff_lines | new_tests
candidate-0       |  PASS  |  PASS  |  FAIL  | PASS | FAIL |         +3 |        0
candidate-1       |  FAIL  |  PASS  |  TIMEO | PASS | PASS |        +15 |        2
candidate-2       |  PASS  |  PASS  |  PASS  | PASS | PASS |         +5 |        1
...
```

Compute diff stats:
```bash
git diff HEAD --stat | tail -1 | awk '{print $4+$6}'  # total lines changed
```

Count new tests added:
```bash
git diff HEAD --name-only | grep -i test | wc -l
```

### 2. Run hard gates
Reject candidates that:
- Have no extractable patch (`patch --dry-run` fails)
- Fail required tests (FAIL_TO_PASS cases from task manifest)
- Modify forbidden files (`.env`, `.gitconfig`, `.git-credentials`)
- Introduce regressions in PASS_TO_PASS tests

### 3. Compute granular scores
Use the Python engine:
```bash
python -m hydra_code evaluate "$run_id" --output ".hydra/runs/$run_id/scores.json"
```

If the engine is unavailable, compute manually using this formula:

```
Score = (pass_rate * 0.30)
      + (lint_ok * 0.10)
      + (typecheck_ok * 0.10)
      + (min(1.0, 5 / diff_lines) * 0.15)    # smaller diff = higher score
      + (min(1.0, new_tests * 0.15) * 0.10)   # up to ~7 new tests = full score
      - (regression_count * 0.10)              # penalty for regressions
      + (0.05 if edge_tests_present else 0)    # bonus for thoughtful edge case tests
```

Where:
- `pass_rate` = fraction of all tests passed (0.0 to 1.0)
- `lint_ok` = 1 if `ruff check` passes, 0 otherwise
- `typecheck_ok` = 1 if type check passes, 0 otherwise
- `diff_lines` = total insertions + deletions
- `new_tests` = count of new/modified test files
- `regression_count` = number of previously-passing tests that now fail
- `edge_tests_present` = 1 if candidate added tests for edge cases (empty input, boundary values, error states)

This produces differentiated scores even when all candidates pass the same tests.

### 4. Report evaluation results
```
Scores:
  candidate-0: 0.87  [PASS]  +3 lines, 0 new tests, lint FAIL
  candidate-1: 0.00  [FAIL: timeout]
  candidate-2: 0.92  [PASS]  +5 lines, 1 new test, all checks pass
  candidate-3: 0.65  [PASS]  +22 lines, 3 new tests, typecheck FAIL
  candidate-4: 0.78  [PASS]  +8 lines, 2 new tests, all checks pass
  candidate-5: 0.00  [FAIL: no patch]
```

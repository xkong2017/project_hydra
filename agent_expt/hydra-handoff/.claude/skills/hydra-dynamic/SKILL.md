---
name: hydra-dynamic
description: Parallel test-time scaling workflow. Spawns 6 sub-agents with different strategy angles, evaluates through tournament, and produces a final fix.
---

# Hydra-Dynamic: Multi-Agent Parallel Coding Workflow

Run **6 concurrent sub-agents** against a coding task, each with a different strategy angle. Collect patches and trajectories, evaluate via test matrix and tournament, select the winner, optionally refine, and produce a final audit report.

## When to use
- Bugs, refactoring, or features where one-shot might miss the best approach
- Tasks where multiple strategy angles increase success probability
- Any time you want parallel exploration + tournament selection

## Workflow overview

```
Phase 1: DISPATCH    → generate context, create 6 worktrees, spawn sub-agents
Phase 2: COLLECT     → gather trajectories, patches, and tests from completed agents
Phase 3: EVALUATE    → build test matrix, compute evidence scores, run hard gates
Phase 4: TOURNAMENT  → 3 judges rank candidates, select winner
Phase 5: REFINE      → (optional) deepen the winning patch
Phase 6: REPORT      → generate audit report, clean up worktrees
```

## How to run

```
hydra-dynamic: Fix the pagination off-by-one bug
```

## Phase instructions

Execute phases sequentially using the files in `phases/`.

### Phase 1 — Dispatch
File: `phases/01-dispatch.md`

### Phase 2 — Collect
File: `phases/02-collect.md`

### Phase 3 — Evaluate
File: `phases/03-evaluate.md`

### Phase 4 — Tournament
File: `phases/04-tournament.md`

### Phase 5 — Refine (optional)
File: `phases/05-refine.md`

### Phase 6 — Report
File: `phases/06-report.md`

## Engine

The Python library at `hydra-code/src/hydra_code/` provides scoring, evaluation, tournament, and reporting logic. Call it via:

```bash
python -m hydra_code evaluate <run_id>
python -m hydra_code tournament <scores.json>
python -m hydra_code report <run_id>
```

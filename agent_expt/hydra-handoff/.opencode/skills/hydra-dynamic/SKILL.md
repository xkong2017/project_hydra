---
name: hydra-dynamic
description: Parallel test-time scaling workflow. Spawns 2-6 sub-agents with concrete behavioral constraints, evaluates through tournament, and produces a final fix.
---

# Hydra-Dynamic: Multi-Agent Parallel Coding Workflow

Run **2-6 concurrent sub-agents** against a coding task (adaptive based on complexity), each with a concrete behavioral constraint that forces genuinely different output. Collect patches and trajectories, evaluate via test matrix and tournament, select the winner, optionally refine, and produce a final audit report.

## When to use
- Bugs, refactoring, or features where one-shot might miss the best approach
- Tasks where multiple strategy angles increase success probability
- Any time you want parallel exploration + tournament selection

## Workflow overview

```
Phase 1: DISPATCH    → analyze complexity, create worktrees (adaptive count), spawn agents
Phase 2: COLLECT     → gather trajectories, patches, and tests from completed agents
Phase 3: EVALUATE    → build test matrix + lint + typecheck, compute granular scores, run hard gates
Phase 4: TOURNAMENT  → 1 judge with rubric (escalate to 2 on tie), select winner
Phase 5: REFINE      → (optional) deepen the winning patch
Phase 6: REPORT      → generate audit report, clean up worktrees
```

## How to run

```bash
# Load the skill and feed a task
# The agent will auto-execute through all 6 phases
hydra-dynamic: Fix the pagination off-by-one bug
```

## Phase instructions

Read the corresponding phase file for detailed steps. Execute phases sequentially.

### Phase 1 — Dispatch
Execute the instructions in `phases/01-dispatch.md`.

### Phase 2 — Collect
Execute the instructions in `phases/02-collect.md`.

### Phase 3 — Evaluate
Execute the instructions in `phases/03-evaluate.md`.

### Phase 4 — Tournament
Execute the instructions in `phases/04-tournament.md`.

### Phase 5 — Refine (optional)
Execute the instructions in `phases/05-refine.md`.

### Phase 6 — Report
Execute the instructions in `phases/06-report.md`.

## Engine

The Python library at `hydra-code/src/hydra_code/` provides scoring, evaluation, tournament, and reporting logic. Call it via:

```bash
python -m hydra_code evaluate <run_id>
python -m hydra_code tournament <scores.json>
python -m hydra_code report <run_id>
```

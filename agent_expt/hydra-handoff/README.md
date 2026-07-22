# Hydra-Dynamic

Parallel test-time scaling workflow for coding tasks. Spawns **2-6 sub-agents** (adaptive based on complexity) with concrete behavioral constraints, evaluates via test matrix and rubric-based tournament, and produces a final fix.

---

## Architecture

```
                              ┌─────────────────────────────┐
                              │       Coding Task            │
                              │  (bug fix / refactor / feat) │
                              └──────────┬──────────────────┘
                                         │
                              ┌──────────▼──────────────────┐
                              │    Complexity Analysis      │
                              │  (files / ambiguity / ACs)  │
                              └──────┬──────┬──────┬───────┘
                                     │      │      │
                          ┌──────────┘    ┌─┴─┐    └──────────┐
                     ┌────▼────┐    ┌─────▼──────┐    ┌──────▼─────┐
                     │ Simple  │    │  Medium    │    │  Complex   │
                     │ 1 file  │    │ 2-3 files  │    │  5+ files  │
                     │ 2 agents│    │ 4 agents   │    │  6 agents  │
                     └────┬────┘    └─────┬──────┘    └──────┬─────┘
                          │              │              │
                     ┌────▼──────────────▼──────────────▼──────┐
                     │          Worktree Isolation            │
                     │  git worktree add — one per candidate  │
                     └────────────────┬───────────────────────┘
                                      │
                     ┌────────────────▼───────────────────────┐
                     │      Parallel Sub-Agent Dispatch       │
                     │  ┌────────┐ ┌────────┐ ┌────────┐     │
                     │  │Minimal │ │ Robust │ │  TDD   │  …  │
                     │  │ ≤3 ln  │ │Decimal │ │tests 1st│     │
                     │  └────────┘ └────────┘ └────────┘     │
                     │     ▲          ▲          ▲            │
                     │     └────┬─────┴──────────┤            │
                     │          │     Local      │            │
                     │     ┌────┴─────┴──────────┴────┐       │
                     │     │   Qwen LLM (port 8000)   │       │
                     │     │   vLLM · qwen3.6-27B    │       │
                     │     └─────────────────────────┘       │
                     └────────────────┬───────────────────────┘
                                      │
                     ┌────────────────▼───────────────────────┐
                     │           Evaluation Pipeline          │
                     │  ┌──────────┐ ┌────────┐ ┌──────────┐ │
                     │  │Test Matrix│ │ Lint   │ │Typecheck │ │
                     │  │  pytest  │ │ ruff   │ │  mypy    │ │
                     │  └──────────┘ └────────┘ └──────────┘ │
                     │           │                   │       │
                     │     ┌─────▼───────────────────▼──┐    │
                     │     │  Granular Evidence Score   │    │
                     │     │  pass_rate×0.30 + lint×0.10│    │
                     │     │  + typecheck×0.10          │    │
                     │     │  - diff_penalty + test_bonus│   │
                     │     └────────────┬───────────────┘    │
                     └────────────────┬───────────────────────┘
                                      │
                     ┌────────────────▼───────────────────────┐
                     │  Tournament (Rubric Judge)             │
                     │  ┌────────┬───────┬────────┬────────┐ │
                     │  │Correct │Minimal│Robust  │  Maint │ │
                     │  │  30%   │  25%  │  20%   │  15%   │ │
                     │  └────────┴───────┴────────┴────────┘ │
                     │         Test quality: 10%              │
                     │         Escalate to 2nd judge if ≤10%  │
                     └────────────────┬───────────────────────┘
                                      │
                     ┌────────────────▼───────────────────────┐
                     │    ┌── Optional Refinement (Phase 5)   │
                     │    ▼                                   │
                     │  ┌──────────────────────────────────┐  │
                     │  │   Final Fix + Audit Report       │  │
                     │  │   Patch file · report.md · traj  │  │
                     │  └──────────────────────────────────┘  │
                     └────────────────────────────────────────┘
```

---

## Pipeline Phases

| Phase | Name | What happens |
|-------|------|-------------|
| 1 | **Dispatch** | Analyze complexity → create worktrees (2/4/6) → assign concrete behavioral constraints to each agent |
| 2 | **Collect** | Gather trajectories, patches, and tests from completed agents |
| 3 | **Evaluate** | Run test matrix + lint + typecheck → compute granular evidence scores → apply hard gates |
| 4 | **Tournament** | Single judge with 5-criterion rubric (escalate to 2nd on tie) → select winner |
| 5 | **Refine** | Optional — deepen the winning patch, re-validate |
| 6 | **Report** | Generate audit report with rubric breakdown and evidence |

---

## Behavioral Constraints (Phase 1)

Instead of abstract strategy labels, each agent gets a concrete constraint that forces genuinely different output:

| Agent | Constraint | Output difference |
|-------|-----------|------------------|
| Minimal | "Change ≤3 lines, smallest correct diff" | Tiny patches, low risk |
| Robust | "Full type annotations, handle all edge cases" | Bulletproof code |
| TDD | "Write tests first, then minimum fix" | Test-covered, minimal |
| Clean | "Refactor for clarity, then fix" | Readable, maintainable |
| Deep | "Find deepest root cause, fix everywhere needed" | Systemic fix |
| Abstract | "Introduce helper/class that makes bug structurally impossible" | Architectural |

---

## Scoring Formula (Phase 3)

```
Score = (pass_rate × 0.30)   ──  test results
      + (lint_ok × 0.10)     ──  ruff check
      + (typecheck_ok × 0.10) ──  mypy / tsc / cargo check
      + (5/diff_lines × 0.15) ──  smaller diffs rewarded
      + (new_tests × 0.15 × 0.10)  ──  test coverage bonus
      - (regressions × 0.10)  ──  regression penalty
      + (edge_tests × 0.05)   ──  edge case test bonus
```

---

## Configuration

| File | Purpose |
|------|---------|
| `~/.config/opencode/opencode.json` | Provider definition for `local-8000` (baseURL, model, timeout) |
| `opencode.jsonc` | Project-level model override: `local-8000/qwen` |
| `.opencode/skills/hydra-dynamic/SKILL.md` | Skill definition + 6 phase instructions |
| `.claude/skills/hydra-dynamic/` | Claude Code compatible copy |

---

## Quick Start

```bash
# Prerequisites: vLLM server with Qwen on port 8000
# Verify the server:
curl http://localhost:8000/v1/models

# Run opencode from the project directory:
cd /home/mike2026/agent_expt/hydra-handoff
opencode

# Inside opencode, load the skill:
hydra-dynamic: Fix the pagination off-by-one bug in tests/e2e/fixtures/pagination/paginator.py

# Or run non-interactively:
opencode run --model local-8000/qwen --auto "Fix the bug in ..."
```

---

## Benchmark: Single-Call vs Multi-Agent

| Fixture | Type | Single Qwen | Multi-agent needed? |
|---------|------|-------------|-------------------|
| pagination | Off-by-one | **1/8 failed** | Untested |
| cache_isolation | Missing key | ✅ Pass | No |
| async_race | Missing await | ✅ Pass | No |
| parser | Type mismatch | ✅ Pass | No |
| misleading_test | Missing dict key | ✅ Pass | No |
| multi_file | Cross-module | ✅ Pass | No |
| requests_6028 | Auth dropped | ✅ Pass | No |

The existing fixtures are too simple to demonstrate multi-agent advantage. To properly evaluate, run against [SWE-bench Verified](https://www.swebench.com/) hard tasks (22 available in `manifests/swebench_verified_filtered_hard.json`).

---

## Python Engine

The `hydra-code/` subdirectory contains the Python scoring, evaluation, tournament, and reporting engine:

```
hydra-code/src/hydra_code/
├── evaluator.py       Evidence scoring and formula computation
├── tournament.py      Candidate ranking and winner selection
├── reporting.py       Audit report generation
├── context_packet.py  Shared agent context builder
├── worktrees.py       Git worktree management
├── trajectory.py      Agent trajectory parsing
├── test_harvester.py  Test file collection and deduplication
├── refinement.py      Fix deepening pass
├── models.py          Data models (Candidate, Score, etc.)
├── cli.py             CLI entry points
├── config.py          Configuration management
├── benchmark.py       SWE-bench integration
└── orchestrator.py    Full pipeline orchestration
```

See `hydra-code/README.md` for the Python engine documentation.

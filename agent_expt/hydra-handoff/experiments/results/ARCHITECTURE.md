# HydraCode-6: System Architecture

## Overview

HydraCode-6 is a **parallel multi-agent coding pipeline** that improves code generation quality by running 6 strategies in parallel, selecting the best via tournament voting, and refining it with test-feedback. Designed for local LLMs (Qwen3.6-27B via vLLM) and production use with Claude Code CLI.

```
                     ┌─────────────────────────────┐
                     │      USER SPECIFICATION      │
                     │  (task + source + tests)     │
                     └──────────────┬──────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (orchestrator.py)                  │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ 1. PREFLIGHT: check dirty repo, resolve base SHA            │  │
│  │ 2. CONTEXT_PACKET: build task context + prompt              │  │
│  │ 3. CANDIDATE_GENERATION: launch parallel rollouts           │  │
│  │ 4. EVALUATION: run test matrix, score, apply hard gates     │  │
│  │ 5. TOURNAMENT: recursive tournament voting                  │  │
│  │ 6. REFINEMENT: test-feedback refinement                     │  │
│  │ 7. FINAL_VALIDATION: static inspection + diff               │  │
│  │ 8. REPORTING: output patch, summary, metrics                │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────┐
│                        RUNNER TIER                                │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐  │
│  │   ClaudeRunner       │  │   LocalApiRunner                  │  │
│  │   (claude CLI)       │  │   (vLLM HTTP API)                │  │
│  │                      │  │                                  │  │
│  │   claude -p "..."    │  │   POST /v1/chat/completions      │  │
│  │   --max-turns 25     │  │   model="qwen"                   │  │
│  │   --permission-mode  │  │   max_tokens=8192                │  │
│  └──────────────────────┘  └──────────────────────────────────┘  │
│           │                            │                          │
│           ▼                            ▼                          │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │               Git Worktrees (worktrees.py)                 │   │
│  │  Isolated per-candidate copies of the repo                │   │
│  │  create_worktree() → extract_patch() → cleanup            │   │
│  └───────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

## Core Architecture

### 1. Pipeline Phases

```
                         PHASE 1: FAST (3 strategies)
                         ┌──────┬──────┬──────┐
                         │ tdd  │ root │ mini │
                         │      │cause │ mal  │
                         └──┬───┴──┬───┴──┬───┘
                            │      │      │
                            ▼      ▼      ▼
                         ┌─────────────────────┐
                         │  Any candidate       │
                         │  passes all tests?   │──YES──→ DONE (~60s)
                         └──────────┬──────────┘
                                    │ NO
                                    ▼
                         PHASE 2: EXTRA (3 strategies)
                         ┌──────┬──────┬──────┐
                         │ arch │ adver│ alter│
                         │itec. │sarial│native│
                         └──┬───┴──┬───┴──┬───┘
                            │      │      │
                            ▼      ▼      ▼
                         ┌─────────────────────┐
                         │  Any candidate       │
                         │  passes all tests?   │──YES──→ DONE (~150s)
                         └──────────┬──────────┘
                                    │ NO
                                    ▼
                         PHASE 3: REFINEMENT
                         ┌─────────────────────┐
                         │  Best candidate's    │
                         │  code + test errors  │
                         │  → model refixes     │
                         │  the ORIGINAL source │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │  Passes tests?       │──YES──→ DONE (~250s)
                         │  or report FAIL      │
                         └─────────────────────┘
```

### 2. Strategy Diversity

Each strategy uses a different **role prompt** to steer the model's approach:

| Strategy | Role Prompt | Strength |
|----------|-------------|----------|
| **tdd** | "Read the tests first, then write the minimum fix." | Best overall; shortest reasoning; 100% on easy tasks |
| **root-cause** | "Trace the data flow to find the exact root cause." | Good for subtle bugs where understanding matters |
| **minimal** | "Fix with the smallest possible change." | Avoids over-engineering |
| **architecture** | "Consider API contracts and module boundaries." | Catches cross-module issues |
| **adversarial** | "Find edge cases the obvious fix misses." | Useful for security/validation bugs |
| **alternative** | "Explore a different solution strategy." | Diversity when obvious fix is wrong |

Empirical ranking (from 50-task benchmark):
```
tdd (35% wins) > root-cause (20%) > minimal (20%) > architecture (10%) > alternative (10%) > adversarial (5%)
```

### 3. Selection: Tournament Voting

```
Candidates: [tdd, root-cause, minimal, architecture, adversarial, alternative]
                    │
                    ▼
         ┌──────────────────────────┐
         │  HARD GATE FILTER        │
         │  Remove candidates with: │
         │  • syntax errors         │
         │  • forbidden file edits  │
         │  • test weakening        │
         └────────────┬─────────────┘
                      │
         ┌────────────▼─────────────┐
         │  3 JUDGES VOTE           │
         │  Judge 1: Score-based    │
         │  Judge 2: LLM (temp=0.3) │
         │  Judge 3: LLM (temp=0.5) │
         └────────────┬─────────────┘
                      │
         ┌────────────▼─────────────┐
         │  MAJORITY WINS           │
         │  Tie → distinguishing    │
         │  test generated          │
         └──────────────────────────┘
```

### 4. Refinement: Test-Feedback Loop

```
┌──────────────────────────────────────────────────────┐
│  INPUT:                                               │
│    - Original source code (the buggy file)            │
│    - Best candidate's attempt (wrong fix)             │
│    - Test error output (pytest verbose)               │
│                                                       │
│  PROMPT STRUCTURE:                                    │
│    "The previous fix was INCORRECT.                   │
│     Here are the test failures:                       │
│     ```
│     FAILED test_X ... assert 5 == 10                  │
│     ```                                               │
│                                                       │
│     Original source:                                  │
│     ```python                                          │
│     def add(a, b): return a - b                       │
│     ```                                               │
│                                                       │
│     Fix the ORIGINAL source. Return ONLY corrected     │
│     source.py inside ```python."                      │
│                                                       │
│  Retry: if refinement returns empty, try again with    │
│         shorter prompt                                │
└──────────────────────────────────────────────────────┘
```

## Module Architecture

```
hydra-code/src/hydra_code/
│
├── orchestrator.py        # Main pipeline controller
├── models.py              # Data models (RunConfig, CandidateResult, etc.)
├── cli.py                 # CLI entry point
│
├── claude_runner.py       # Claude Code subprocess runner (production)
├── local_api_runner.py    # Local Qwen API runner (for local dev)
│
├── local_judge.py         # Score-aware LLM judge for tournament
├── tournament.py          # Recursive tournament voting
│
├── refinement.py          # Test-feedback refinement builder
├── test_harvester.py      # Test extraction from worktrees
│
├── evaluator.py           # Test matrix, scoring, hard gates
├── trajectory.py          # Trajectory validation
├── anti_patterns.py       # Anti-pattern library
│
├── scheduler.py           # Async scheduler with priority
├── worktrees.py           # Git worktree management
├── context_packet.py      # Task context builder
├── metrics.py             # GPU monitoring and metrics
├── gpu_monitor.py         # GPU utilization tracking
├── signal_handler.py      # Graceful shutdown
├── config.py              # Configuration loader
├── task_manifest.py       # Task file loader
├── reporting.py           # Report generation
├── benchmark.py           # Benchmarking utilities
└── utils.py               # Shared utilities
```

## Data Flow

```
┌─────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  TASK    │   │  6×      │   │  EVAL    │   │  TOURN.  │
│  INPUT   │──▶│ROLLOUTS  │──▶│  Test    │──▶│  3-Judge │
│          │   │(parallel)│   │  Matrix  │   │  Voting  │
└─────────┘   └──────────┘   └──────────┘   └────┬─────┘
                                                  │
                                        ┌─────────▼──────┐
                                        │  REFINEMENT     │
                                        │  Test feedback  │
                                        │  + retry        │
                                        └────────┬───────┘
                                                  │
                                        ┌─────────▼──────┐
                                        │  FINAL PATCH   │
                                        │  (.diff)       │
                                        └────────────────┘
```

## Configuration

```python
# RunConfig (models.py)
task: str                    # Task description
concurrency: int = 6         # Max parallel rollouts
num_candidates: int = 6      # Number of candidates
single_agent: bool = False   # Single strategy mode (baseline)
base_ref: str = "HEAD"       # Git base ref
max_turns: int = 25          # Max Claude turns
agent_timeout_seconds: int = 600  # Per-rollout timeout
use_local_api: bool = False  # Use local Qwen API
max_tokens: int = 8192       # Max tokens per API call
refine_mode: RefineMode = STANDARD  # NONE, STANDARD, DEEP
```

## Key Empirical Findings

| Finding | Evidence | Implication |
|---------|----------|-------------|
| **Strategy diversity adds ~10%** | 56% → 66% on 50 tasks | Run multiple strategies |
| **Test-feedback refinement adds ~50%** | 23% → 73% on 22 failed tasks | Refinement is the most powerful step |
| **Trajectory summaries hurt Qwen** | 73% → 33% with PDR | Don't use text summaries with weaker models |
| **3 strategies ≈ 6 strategies on easy tasks** | 100% on 100 easy tasks | Use 3 first, 3 more only if needed |
| **content=null is Qwen3 bottleneck** | 30-40% of calls produce null | Retry with doubled max_tokens |
| **tdd strategy is universal best** | Wins 35% of time, fastest | Try tdd first in any optimization |

## Verified Performance

| Task Type | Tasks | Solve Rate | Avg Time |
|-----------|:-----:|:----------:|:--------:|
| Easy (arithmetic bugs) | 100 | **100%** | **7s** |
| Medium (single-file bugs) | 50 | **66%** | 63s |
| Hard (failed tasks) | 22 | **73%** | 330s |
| Real SWE-bench fixtures | 10 | **60%** | 180s |
| Feature development | 1 | **100%** | 103s |

# Phase 1: Dispatch — Analyze, Create Worktrees, Spawn Agents

**Goal**: Analyze task complexity, create isolated worktrees, and launch sub-agents in parallel (2-6 depending on complexity).

## Steps

### 1. Understand the task
Read the task description. If a `task.md` or `PRD.md` exists in the repo, read it.

### 2. Analyze task complexity
Determine how many agents to dispatch:
- **Simple** (1 file, clear bug/fix): 2 agents
- **Medium** (2-3 files, moderate ambiguity): 4 agents
- **Complex** (cross-module, multiple hypotheses): 6 agents

Criteria for complexity classification:
- Number of files likely affected (< 2 = simple, 2-4 = medium, 5+ = complex)
- Ambiguity in root cause (clear = simple, vague = complex)
- Number of acceptance criteria (< 3 = simple, 3-6 = medium, 7+ = complex)

Set the agent count:
```bash
agent_count=2  # or 4 or 6
```

### 3. Generate a run ID
```bash
run_id="hydra-$(date +%s)"
mkdir -p ".hydra/runs/$run_id"
echo "$run_id"
```

### 4. Generate the context packet
Use the Python engine to build a deterministic context packet shared by all workers:

```bash
python -m hydra_code.context_packet --task "..." --repo . --output ".hydra/runs/$run_id/context.md"
```

If the module doesn't have a `__main__`, create the packet manually:
- Repository structure (`find . -maxdepth 3 -type f | grep -v .git | grep -v node_modules`)
- Test commands detected from pyproject.toml / package.json / Makefile / Cargo.toml
- CLAUDE.md instructions (if present)
- Task description + acceptance criteria
- Worker output contract

### 5. Get the current SHA
```bash
base_sha=$(git rev-parse HEAD)
branch=$(git rev-parse --abbrev-ref HEAD)
```

### 6. Save run state
Write an initial `run.json` to `.hydra/runs/$run_id/run.json`:
```json
{"run_id": "...", "phase": "dispatch", "task": "...", "base_sha": "...", "branch": "...", "agent_count": 2, "candidates": {}}
```

### 7. Create worktrees (adaptive count)
```bash
for i in $(seq 0 $((agent_count - 1))); do
  wt_path=".hydra/worktrees/$run_id/candidate-$i"
  git worktree add "$wt_path" HEAD
done
```

### 8. Define concrete behavioral constraints
Each constraint drives genuinely different output. Store in `.hydra/runs/$run_id/angles.json`:

If agent_count = 2:
```json
[
  {"id": "candidate-0", "constraint": "change no more than 3 lines, prefer the smallest correct diff", "prompt_file": "prompts/candidate_minimal.md"},
  {"id": "candidate-1", "constraint": "add full type annotations and handle all edge cases including empty/null inputs", "prompt_file": "prompts/candidate_robust.md"}
]
```

If agent_count = 4:
```json
[
  {"id": "candidate-0", "constraint": "change no more than 3 lines, prefer the smallest correct diff"},
  {"id": "candidate-1", "constraint": "add full type annotations and handle all edge cases including empty/null inputs"},
  {"id": "candidate-2", "constraint": "write new tests first (test-driven), then implement the minimum fix to make them pass"},
  {"id": "candidate-3", "constraint": "refactor the surrounding function for clarity, then fix; prefer readability over minimality"}
]
```

If agent_count = 6:
```json
[
  {"id": "candidate-0", "constraint": "change no more than 3 lines, prefer the smallest correct diff"},
  {"id": "candidate-1", "constraint": "add full type annotations and handle all edge cases including empty/null inputs"},
  {"id": "candidate-2", "constraint": "write new tests first (test-driven), then implement the minimum fix to make them pass"},
  {"id": "candidate-3", "constraint": "refactor the surrounding function for clarity, then fix; prefer readability over minimality"},
  {"id": "candidate-4", "constraint": "find the deepest root cause and fix it there, even if it requires changing calling code"},
  {"id": "candidate-5", "constraint": "introduce a minimal abstraction (helper function/class) that makes the bug structurally impossible"}
]
```

### 9. Spawn agents in parallel (early-termination aware)
Spawn all agents in background. After the first 2 complete, check if their patches are functionally equivalent (same files changed, similar diff). If they converged, cancel remaining agents:

```
Spawn a sub-agent for each candidate-0 through candidate-{agent_count-1}.
Each agent works in its worktree at .hydra/worktrees/<run_id>/<candidate_id>.
Each agent receives:
  - The context packet
  - Its constraint string (as the primary instruction)
  - The task description
  - Instructions to implement a fix, run tests, and return a structured trajectory
Agents must run in background (parallel).

After the first 2 agents complete:
  - Compare their patches for functional equivalence
  - If similar (same files, overlapping line ranges), cancel remaining agents as convergence
  - Otherwise, let all remaining agents finish
  - Track which were cancelled vs. completed vs. timed out
```

**Sub-agent contract** (what each agent must return):
1. A structured trajectory JSON (saved to `.hydra/runs/$run_id/trajectories/$candidate_id.json`)
2. A patch file (`.hydra/runs/$run_id/patches/$candidate_id.patch`)
3. Any new/modified test files
4. A `done` signal via SendMessage or a marker file in `.hydra/runs/$run_id/done/`

### 10. Wait for completion
Poll for all `done` markers or time out after 600 seconds. Track which completed vs. timed out vs. failed vs. cancelled.

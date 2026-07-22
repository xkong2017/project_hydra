# hydra-code Skill

Invokes the HydraCode-6 CLI for parallel test-time scaling of local agentic coding.

## Usage

```bash
# Start a new run with a task description
hydra-code run "fix the pagination off-by-one bug"

# Run from a task file
hydra-code run --task-file task.md --mode deep --concurrency 6

# Check status of a running run
hydra-code status <run_id>

# View report after completion
hydra-code report <run_id>

# Resume an interrupted run
hydra-code resume <run_id>

# Clean up artifacts
hydra-code clean <run_id>

# Run benchmark suite
hydra-code benchmark benchmarks/config.yaml
```

## Key Options

| Flag | Description | Default |
|------|-------------|---------|
| `--mode` | Run mode: `fast`, `standard`, `deep` | `standard` |
| `--concurrency` | Number of parallel agents | 6 |
| `--max-turns` | Max turns per agent | 25 |
| `--agent-timeout-seconds` | Agent timeout | 600 |
| `--test-timeout-seconds` | Test timeout | 120 |
| `--base-ref` | Git base ref | `HEAD` |
| `--keep-worktrees` | Keep worktrees after run | false |
| `--dry-run` | Dry run (no agents spawned) | false |
| `--no-refine` | Skip refinement phase | false |
| `--no-generated-tests` | Skip generated test validation | false |

## Workflow

1. Spawns N isolated Git worktrees (one per agent)
2. Each agent attempts to solve the task independently
3. Patches and tests are harvested from each candidate
4. A tournament votes to select the best candidate
5. A refinement pass repairs the winner's patch
6. A final report summarizes scores and selection
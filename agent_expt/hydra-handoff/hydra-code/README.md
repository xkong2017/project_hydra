# HydraCode-6

Parallel test-time scaling orchestrator for local agentic coding. Runs 6 concurrent Claude Code sessions in isolated Git worktrees, harvests patches and tests, and selects the best candidate through recursive tournament voting.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                      CLI (cli.py)                        │
├──────────────────────────────────────────────────────────┤
│                  Orchestrator (orchestrator.py)          │
│  ┌─────────┬─────────┬─────────┬─────────┬─────────┐    │
│  │Worker 1 │Worker 2 │Worker 3 │Worker 4 │ ...     │    │
│  │(wtree)  │(wtree)  │(wtree)  │(wtree)  │         │    │
│  └─────────┴─────────┴─────────┴─────────┴─────────┘    │
│  ┌──────────────────────────────────────────────────────┐│
│  │  Harvester → Test Matrix → Tournament → Refinement  ││
│  └──────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Install
pip install -e ./hydra-code

# Run on a task
hydra-code run "fix the pagination bug" --mode standard --concurrency 6

# Check status
hydra-code status <run_id>

# View results
hydra-code report <run_id>
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `run` | Start a new HydraCode run |
| `resume` | Resume an interrupted run |
| `status` | Show run status |
| `report` | Show run report |
| `clean` | Clean up run artifacts |
| `benchmark` | Run benchmark suite |

### Run Options

| Flag | Default | Description |
|------|---------|-------------|
| `--mode` | `standard` | `fast`, `standard`, or `deep` |
| `--concurrency` | 6 | Parallel agent count |
| `--max-turns` | 25 | Max turns per agent |
| `--agent-timeout-seconds` | 600 | Agent timeout |
| `--test-timeout-seconds` | 120 | Test suite timeout |
| `--base-ref` | `HEAD` | Git base reference |
| `--keep-worktrees` | false | Retain worktrees after run |
| `--dry-run` | false | Dry run mode |
| `--no-refine` | false | Skip refinement phase |
| `--no-generated-tests` | false | Skip generated test validation |

## Pipeline Stages

1. **Worktree Creation** — Spawn N isolated Git worktrees from a base ref
2. **Agent Execution** — Each worktree runs a Claude Code session solving the task
3. **Harvesting** — Collect patches and new tests from each candidate
4. **Validation** — Run test matrices, check hard gates, validate patches
5. **Tournament** — Recursive voting to select the best candidate
6. **Refinement** — Iterative repair pass on the winning patch
7. **Reporting** — Generate final report with scores and evidence

## Testing

```bash
# Unit tests
pytest tests/ -m unit -v

# Integration tests
pytest tests/ -m integration -v

# Full suite (excludes fixture repos which are in collect_ignore)
pytest tests/ -v

# Linting
ruff check src/ tests/

# Type checking
mypy src/
```

## Project Status

| Component | Status |
|-----------|--------|
| Core pipeline (US-001 to US-014) | Complete |
| Unit tests (18 modules, 48+ tests) | Complete |
| Integration tests (8 modules) | Complete |
| E2E fixture repos (F1-F7) | Complete |
| Mocked E2E tests | Complete |
| Claude Code skill | Complete |
| Real LLM smoke tests | Requires vLLM infra |

## Requirements

- Python 3.12+
- Git 2.30+
- Claude Code CLI (for agent execution)
- vLLM server (optional, for local LLM serving)
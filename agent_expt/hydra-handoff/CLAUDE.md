# Hydra-Dynamic Workflow

## Available Skills
- **hydra-dynamic**: Parallel test-time scaling workflow. Adaptive 2-6 sub-agents with concrete behavioral constraints, evaluates through tournament, and produces a final fix.

## Quick Start
```bash
# Load the hydra-dynamic skill
# Then give it a task like:
hydra-dynamic: Fix the pagination off-by-one bug
```

## Local LLM
OpenCode is configured at `~/.config/opencode/opencode.json` with provider `local-8000` and model `qwen` (vLLM exposes model ID as `qwen`, not `qwen/qwen3.6-27b`).

## Project Structure
- `hydra-code/src/hydra_code/` — Python engine (scoring, evaluation, tournament, reporting)
- `.opencode/skills/hydra-dynamic/` — OpenCode skill definition
- `.claude/skills/hydra-dynamic/` — Claude Code skill definition
- `opencode.jsonc` — OpenCode project config
- `tests/e2e/fixtures/` — SWE-Verified Lite fixture repos

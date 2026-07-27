# Hydra-Dynamic Workflow

## Quick Start
Run this as a bash command — it always works:
```bash
hydra-dynamic "Build a todo API with create, list, complete, delete"
```
Or use existing source + tests:
```bash
hydra-dynamic --source source.py --test test_source.py
```
The command is at `~/bin/hydra-dynamic` (on PATH). It calls the local Qwen model on port 8000.

## Local LLM
OpenCode config: `~/.config/opencode/opencode.json` (provider `local-8000`, model `qwen`)

## Project Structure
- `hydra-dynamic` — CLI entry point (standalone, no skill system needed)
- `hydra-code/src/hydra_code/` — Python engine
- `.opencode/skills/hydra-dynamic/` — OpenCode skill definition
- `run_dev.py` — Python fallback if the CLI isn't available
- `tests/e2e/fixtures/` — Test fixtures

## How the pipeline works
1. Generates pytest tests from your description
2. Generates code skeleton
3. Runs 6 strategies in parallel (tdd, root-cause, minimal, architecture, adversarial, alternative)
4. Picks the best via scoring
5. Refines with test-feedback if needed
6. Writes output/source.py + output/test_source.py

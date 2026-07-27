---
name: hydra-dynamic
description: Run 6 parallel strategies against a coding task. Auto-generates tests, runs tournament, refines with test-feedback. One command, working code out.
---

# Hydra-Dynamic

Invoke via bash — this always works:

```bash
hydra-dynamic "Build a todo API with create, list, complete, delete"
```

Or with existing source + tests:

```bash
hydra-dynamic --source source.py --test test_source.py
```

## What it does

1. Generates pytest tests from your description
2. Generates a code skeleton
3. Runs 6 strategies in parallel (tdd, root-cause, minimal, architecture, adversarial, alternative)
4. Picks the best result
5. Refines with test-feedback if needed
6. Writes output/source.py + output/test_source.py

## Requirements

- vLLM server running on port 8000 with `qwen` model loaded
- The `hydra-dynamic` command is at `~/bin/hydra-dynamic` (symlinked from repo root)

## How to invoke

**In Claude Code / claude_local.sh:**
```
hydra-dynamic: Build a todo API
```

**In OpenCode:**
```
hydra-dynamic: Build a todo API
```

**Directly (always works):**
```bash
hydra-dynamic "Build a todo API"
```

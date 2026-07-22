"""Context packet generation for HydraCode-6."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run_cmd(args: list[str], cwd: Path | None = None) -> str:
    """Run a command and return stdout."""
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout


def detect_test_commands(repo_root: Path) -> list[str]:
    """Detect likely test commands from the repository."""
    commands = []
    # Check common test runners
    if (repo_root / "pyproject.toml").exists():
        commands.append("pytest -q")
    if (repo_root / "package.json").exists():
        commands.append("npm test")
    if (repo_root / "Makefile").exists():
        commands.append("make test")
    if (repo_root / "Cargo.toml").exists():
        commands.append("cargo test --quiet")
    return commands


def detect_build_commands(repo_root: Path) -> list[str]:
    """Detect likely build/lint commands."""
    commands = []
    if (repo_root / "pyproject.toml").exists():
        commands.extend(["ruff check .", "mypy src"])
    if (repo_root / "package.json").exists():
        commands.extend(["npm run lint", "npm run typecheck"])
    return commands


def get_repo_structure(repo_root: Path, max_depth: int = 3) -> str:
    """Get a summary of the repository structure."""
    result = _run_cmd(["find", ".", "-maxdepth", str(max_depth), "-type", "f"], cwd=repo_root)
    # Filter out common noise
    lines = []
    for line in result.strip().split("\n"):
        if any(skip in line for skip in (".git/", "node_modules/", "__pycache__/", ".venv/")):
            continue
        lines.append(line)
    return "\n".join(lines[:200])


def read_claude_instructions(repo_root: Path) -> str:
    """Read repository instructions from CLAUDE.md."""
    claude_md = repo_root / "CLAUDE.md"
    if claude_md.exists():
        return claude_md.read_text()
    return ""


def generate_context_packet(
    task: str,
    repo_root: Path,
    base_sha: str,
    branch: str,
    acceptance_criteria: list[str] | None = None,
    constraints: list[str] | None = None,
) -> str:
    """Generate the deterministic context packet shared by all workers."""
    test_cmds = detect_test_commands(repo_root)
    build_cmds = detect_build_commands(repo_root)
    structure = get_repo_structure(repo_root)
    instructions = read_claude_instructions(repo_root)

    packet = f"""# HydraCode Context Packet

## Task
{task}

## Repository
- Root: {repo_root}
- Base SHA: {base_sha}
- Branch: {branch}

## Acceptance Criteria
"""
    if acceptance_criteria:
        for i, criterion in enumerate(acceptance_criteria, 1):
            packet += f"{i}. {criterion}\n"
    else:
        packet += "(Derived from task description)\n"

    packet += f"""
## Repository Structure
```
{structure}
```

## Detected Commands
- Test: {", ".join(test_cmds) if test_cmds else "not detected"}
- Build/Lint: {", ".join(build_cmds) if build_cmds else "not detected"}

## Constraints
"""
    if constraints:
        for c in constraints:
            packet += f"- {c}\n"
    else:
        packet += "- Standard repository constraints apply\n"

    if instructions:
        packet += f"\n## Repository Instructions\n{instructions}\n"

    packet += """
## Worker Output Contract
1. Investigate the repository to understand the problem.
2. Implement a candidate fix in this worktree.
3. Add useful tests when appropriate.
4. Run targeted validation.
5. Leave changes in this worktree.
6. Return a structured trajectory summary.
7. Never edit the main checkout.
"""
    return packet

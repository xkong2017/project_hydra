"""SWE-Verified Lite evaluation harness for the hydra-dynamic workflow.

Usage (for the agent):
  python scripts/eval_swe.py list                          # List available tasks
  python scripts/eval_swe.py run <task_id>                  # Run one task (agent handles workflow)
  python scripts/eval_swe.py verify <task_id> <run_dir>     # Verify fix against test suite
  python scripts/eval_swe.py report <results.json>          # Generate summary report

This script is designed to be called by the lead agent during the workflow.
Each task is a small repo with a documented bug and test suite.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "e2e" / "fixtures"


@dataclass
class SweTask:
    id: str
    path: Path
    description: str
    difficulty: str = "medium"
    setup_commands: list[str] = field(default_factory=list)
    validation_commands: list[str] = field(default_factory=list)


def discover_tasks() -> list[SweTask]:
    """Discover available SWE tasks from fixtures directory."""
    tasks: list[SweTask] = []

    # Fixture descriptions from benchmarks/config.yaml
    known = {
        "pagination": ("Off-by-one in pagination page calculation", "easy"),
        "async_race": ("Race condition in async resource cleanup", "hard"),
        "parser": ("JSON parser int vs float incompatibility", "medium"),
        "misleading_test": ("Test passes on wrong code (false positive)", "hard"),
        "multi_file": ("API change spanning multiple files", "hard"),
        "rounding": ("Banker's rounding vs commercial rounding in financial calculations", "hard"),
        "requests_6028": ("Proxy auth: prepend_scheme_if_needed loses auth info", "medium"),
    }

    if not FIXTURES_DIR.exists():
        print(f"Fixtures directory not found: {FIXTURES_DIR}", file=sys.stderr)
        return tasks

    for child in sorted(FIXTURES_DIR.iterdir()):
        if not child.is_dir() or child.name.startswith(".") or child.name == "__pycache__":
            continue
        desc, diff = known.get(child.name, (f"Bug fix in {child.name}", "medium"))
        tasks.append(SweTask(
            id=child.name,
            path=child,
            description=desc,
            difficulty=diff,
            setup_commands=_detect_setup(child),
            validation_commands=_detect_validation(child),
        ))

    return tasks


def _detect_setup(task_path: Path) -> list[str]:
    """Detect setup commands for a task."""
    cmds = []

    # Create a temporary working copy (fixtures may be in a git repo)
    cmds.append(f"mkdir -p /tmp/hydra-eval/{task_path.name}")
    cmds.append(f"cp -r {task_path}/* /tmp/hydra-eval/{task_path.name}/")

    # Install deps if pyproject.toml or requirements.txt present
    if (task_path / "pyproject.toml").exists():
        cmds.append(f"cd /tmp/hydra-eval/{task_path.name} && pip install -e . 2>/dev/null || true")
    if (task_path / "requirements.txt").exists():
        cmds.append(f"cd /tmp/hydra-eval/{task_path.name} && pip install -r requirements.txt 2>/dev/null || true")

    return cmds


def _detect_validation(task_path: Path) -> list[str]:
    """Detect validation test commands."""
    if (task_path / "pyproject.toml").exists() or (task_path / "setup.py").exists():
        return ["pytest -q"]
    if (task_path / "package.json").exists():
        return ["npm test"]
    if (task_path / "Makefile").exists():
        return ["make test"]
    return ["pytest -q"]


def cmd_list() -> None:
    """List available SWE tasks."""
    tasks = discover_tasks()
    if not tasks:
        print("No SWE tasks found.")
        return

    print(f"Available SWE-Verified Lite tasks ({len(tasks)}):")
    print()
    for t in tasks:
        print(f"  {t.id:<20} {t.difficulty:<8} {t.description}")
    print()
    print(f"To run: python scripts/eval_swe.py run <task_id>")


def cmd_run(task_id: str) -> None:
    """Run the dynamic workflow on a SWE task.

    This function:
    1. Sets up the task in /tmp/hydra-eval/<task_id>
    2. Prints the task description for the agent
    3. Returns the fixture path
    """
    tasks = discover_tasks()
    task = next((t for t in tasks if t.id == task_id), None)
    if not task:
        print(f"Task not found: {task_id}")
        sys.exit(1)

    # Create working copy
    work_dir = Path(f"/tmp/hydra-eval/{task_id}")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    for cmd in task.setup_commands:
        subprocess.run(cmd, shell=True, capture_output=True)

    print(f"=== Task: {task.id} ===")
    print(f"Description: {task.description}")
    print(f"Difficulty: {task.difficulty}")
    print(f"Work dir: {work_dir}")
    print(f"Validation: {'; '.join(task.validation_commands)}")
    print()
    print("---")
    print(f"Run the hydra-dynamic workflow on {work_dir} to fix the bug.")
    print("After completing, verify with:")
    print(f"  python scripts/eval_swe.py verify {task_id} <run_dir>")
    print("---")

    return str(work_dir)


def cmd_verify(task_id: str, run_dir: str) -> None:
    """Verify that the fix passes the test suite."""
    tasks = discover_tasks()
    task = next((t for t in tasks if t.id == task_id), None)
    if not task:
        print(f"Task not found: {task_id}")
        sys.exit(1)

    work_dir = Path(f"/tmp/hydra-eval/{task_id}")
    if not work_dir.exists():
        print(f"Work dir not found: {work_dir}")
        sys.exit(1)

    # Apply the winning patch if present
    patch_dir = Path(run_dir) / "patches"
    if patch_dir.exists():
        patches = list(patch_dir.glob("*.patch"))
        if patches:
            for p in patches:
                subprocess.run(
                    ["git", "apply", str(p)],
                    cwd=str(work_dir),
                    capture_output=True,
                )

    # Run validation
    start = time.time()
    all_passed = True
    results = []

    for cmd in task.validation_commands:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        passed = result.returncode == 0
        all_passed = all_passed and passed
        results.append({
            "command": cmd,
            "passed": passed,
            "stdout": result.stdout[-500:] if result.stdout else "",
            "stderr": result.stderr[-500:] if result.stderr else "",
        })

    elapsed = time.time() - start

    print(f"=== Verification: {task.id} ===")
    print(f"Status: {'PASS' if all_passed else 'FAIL'}")
    print(f"Time: {elapsed:.1f}s")
    print(f"Commands: {len(results)}")
    for r in results:
        print(f"  {r['command']}: {'PASS' if r['passed'] else 'FAIL'}")
    print()

    return all_passed


def cmd_report(results_file: str) -> None:
    """Generate SWE evaluation summary report."""
    with open(results_file) as f:
        results = json.load(f)

    passed = sum(1 for r in results if r.get("passed"))
    failed = sum(1 for r in results if not r.get("passed"))
    total = len(results)

    print(f"=== SWE Evaluation Report ===")
    print(f"Total tasks: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Pass rate: {passed/total*100:.1f}%" if total else "N/A")
    print()
    for r in results:
        status = "PASS" if r.get("passed") else "FAIL"
        print(f"  {r['task_id']:<20} {status:<6} {r.get('wall_time_sec', 0):.1f}s")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "list":
        cmd_list()
    elif command == "run":
        if len(sys.argv) < 3:
            print("Usage: python scripts/eval_swe.py run <task_id>")
            sys.exit(1)
        cmd_run(sys.argv[2])
    elif command == "verify":
        if len(sys.argv) < 4:
            print("Usage: python scripts/eval_swe.py verify <task_id> <run_dir>")
            sys.exit(1)
        cmd_verify(sys.argv[2], sys.argv[3])
    elif command == "report":
        if len(sys.argv) < 3:
            print("Usage: python scripts/eval_swe.py report <results.json>")
            sys.exit(1)
        cmd_report(sys.argv[2])
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

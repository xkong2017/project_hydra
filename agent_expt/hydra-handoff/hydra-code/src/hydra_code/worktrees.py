"""Git worktree management for HydraCode-6."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from .models import CandidateRole
from .utils import atomic_write_text

WORKTROOTS_BASE = Path(".hydra/worktrees").resolve()


class _WorktreeParams(NamedTuple):
    """Parameters for a single worktree creation."""

    run_id: str
    candidate_id: str
    role: CandidateRole | None
    base_sha: str


async def _run_git_async(
    args: list[str],
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a git command asynchronously and return the result."""
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    return subprocess.CompletedProcess(
        args=args,
        returncode=proc.returncode or 0,
        stdout=stdout_bytes.decode(),
        stderr=stderr_bytes.decode(),
    )


async def _create_single_worktree_async(
    params: _WorktreeParams,
    repo_root: Path | None,
) -> WorktreeInfo:
    """Create a single worktree asynchronously."""
    worktree_path = WORKTROOTS_BASE / params.run_id / params.candidate_id
    branch_name = f"hydra/{params.run_id}/{params.candidate_id}"

    worktree_path.mkdir(parents=True, exist_ok=True)

    # Remove stale branch if it exists, to ensure clean state
    await _run_git_async(["branch", "-D", branch_name], cwd=repo_root)
    await _run_git_async(["branch", branch_name, params.base_sha], cwd=repo_root)

    # Create worktree on the branch (force to override stale registrations)
    result = await _run_git_async(
        ["worktree", "add", "-f", "--detach", str(worktree_path), branch_name],
        cwd=repo_root,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create worktree for {params.candidate_id}: {result.stderr}")

    return WorktreeInfo(
        candidate_id=params.candidate_id,
        role=params.role,
        run_id=params.run_id,
        path=worktree_path,
        branch=branch_name,
        base_sha=params.base_sha,
        created=True,
    )


async def create_worktrees_batch(
    params_list: list[_WorktreeParams],
    repo_root: Path | None = None,
    max_concurrency: int = 16,
) -> list[WorktreeInfo]:
    """Create multiple worktrees in parallel.

    Each worktree creation is independent (different branch, different path),
    so git lock contention is minimal — each operation acquires/releases quickly.
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _limited(params: _WorktreeParams) -> WorktreeInfo:
        async with semaphore:
            return await _create_single_worktree_async(params, repo_root)

    tasks = [_limited(p) for p in params_list]
    results = await asyncio.gather(*tasks)
    return list(results)


@dataclass
class WorktreeInfo:
    """Metadata for a managed worktree."""

    candidate_id: str
    role: CandidateRole | None
    run_id: str
    path: Path
    branch: str
    base_sha: str
    created: bool = False
    has_changes: bool = False


def _run_git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the result."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=30,
    )


def get_repo_root(cwd: Path | None = None) -> Path:
    """Get the repository root directory."""
    result = _run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError("Not a git repository")
    return Path(result.stdout.strip())


def get_current_sha(ref: str = "HEAD", cwd: Path | None = None) -> str:
    """Get the commit SHA for a reference."""
    result = _run_git(["rev-parse", ref], cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"Cannot resolve ref: {ref}")
    return result.stdout.strip()


def get_current_branch() -> str:
    """Get the current branch name."""
    result = _run_git(["branch", "--show-current"])
    return result.stdout.strip() or "detached"


def check_dirty_repo() -> list[str]:
    """Check for uncommitted changes. Returns list of dirty indicators."""
    issues: list[str] = []
    result = _run_git(["status", "--porcelain"])
    if result.returncode == 0 and result.stdout.strip():
        issues.append("Uncommitted changes detected")
        for line in result.stdout.strip().split("\n"):
            status = line[:2]
            file_path = line[3:]
            if status.startswith("??"):
                issues.append(f"Untracked file: {file_path}")
            elif status == " D" or status == "D ":
                issues.append(f"Deleted file: {file_path}")
            elif status in (" M", "M ", "MM"):
                issues.append(f"Modified file: {file_path}")
            else:
                issues.append(f"Changed file ({status}): {file_path}")
    return issues


def create_worktree(
    run_id: str,
    candidate_id: str,
    role: CandidateRole | None,
    base_sha: str,
    repo_root: Path | None = None,
) -> WorktreeInfo:
    """Create a worktree for a candidate from the exact base SHA."""
    worktree_path = WORKTROOTS_BASE / run_id / candidate_id
    branch_name = f"hydra/{run_id}/{candidate_id}"

    worktree_path.mkdir(parents=True, exist_ok=True)

    # Remove stale branch if it exists, to ensure clean state
    _run_git(["branch", "-D", branch_name], cwd=repo_root)
    _run_git(["branch", branch_name, base_sha], cwd=repo_root)

    # Create worktree on the branch (force to override stale registrations)
    result = _run_git(["worktree", "add", "-f", "--detach", str(worktree_path), branch_name], cwd=repo_root)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create worktree: {result.stderr}")

    return WorktreeInfo(
        candidate_id=candidate_id,
        role=role,
        run_id=run_id,
        path=worktree_path,
        branch=branch_name,
        base_sha=base_sha,
        created=True,
    )


def remove_worktree(worktree_path: Path, force: bool = False, repo_root: Path | None = None) -> None:
    """Remove a worktree safely."""
    if not worktree_path.exists():
        return

    # Check for uncommitted changes
    try:
        dirty = check_dirty_repo_at(worktree_path)
        if dirty and not force:
            raise RuntimeError(
                f"Worktree {worktree_path} has uncommitted changes. "
                "Persist patch before removing."
            )
    except Exception:
        pass

    # Prune worktree
    _run_git(["worktree", "prune", str(worktree_path)], cwd=repo_root)

    # Remove branch if it exists
    if repo_root:
        _run_git(["branch", "-D", worktree_path.name], cwd=repo_root)

    # Remove directory
    if worktree_path.exists():
        shutil.rmtree(worktree_path)


def check_dirty_repo_at(worktree_path: Path) -> list[str]:
    """Check for uncommitted changes in a specific worktree."""
    result = _run_git(["status", "--porcelain"], cwd=worktree_path)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().split("\n")
    return []


def extract_patch(worktree_path: Path, base_sha: str, output_path: Path) -> str:
    """Extract a patch from a worktree relative to the base SHA."""
    result = _run_git(["diff", base_sha, "HEAD"], cwd=worktree_path)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to extract patch: {result.stderr}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(output_path, result.stdout)
    return result.stdout


def count_diff_stats(worktree_path: Path, base_sha: str) -> dict[str, int]:
    """Get diff statistics for a worktree."""
    import re

    result = _run_git(["diff", "--stat", base_sha, "HEAD"], cwd=worktree_path)
    stats = {"files_changed": 0, "insertions": 0, "deletions": 0}
    if result.returncode == 0:
        for line in result.stdout.strip().split("\n"):
            if "file changed" in line:
                m = re.search(r"(\d+)\s+file", line)
                if m:
                    stats["files_changed"] = int(m.group(1))
                m = re.search(r"(\d+)\s+insertion", line)
                if m:
                    stats["insertions"] = int(m.group(1))
                m = re.search(r"(\d+)\s+deletion", line)
                if m:
                    stats["deletions"] = int(m.group(1))
    return stats


def list_worktrees() -> list[Path]:
    """List all active worktrees."""
    result = _run_git(["worktree", "list"])
    trees = []
    if result.returncode == 0:
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if parts:
                trees.append(Path(parts[0]))
    return trees


def cleanup_worktrees(run_id: str, keep: bool = False, repo_root: Path | None = None) -> None:
    """Clean up worktrees for a run."""
    run_worktrees = WORKTROOTS_BASE / run_id
    if not run_worktrees.exists():
        return

    if keep:
        return

    for candidate_dir in sorted(run_worktrees.iterdir()):
        if candidate_dir.is_dir():
            try:
                remove_worktree(candidate_dir, force=True, repo_root=repo_root)
            except Exception:
                pass

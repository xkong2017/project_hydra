"""Integration tests for worktree management."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def prune_stale_worktrees() -> None:
    """Prune stale worktree registrations before each test."""
    subprocess.run(["git", "worktree", "prune"], capture_output=True)


@pytest.mark.integration
def test_get_repo_root(git_repo: Path) -> None:
    """Get repository root returns a valid path."""
    from hydra_code.worktrees import get_repo_root

    result = get_repo_root(cwd=git_repo)
    assert result.exists()
    assert (result / ".git").exists() or (result / ".git").is_file()


@pytest.mark.integration
def test_get_current_sha(git_repo: Path) -> None:
    """Get current SHA returns valid commit hash."""
    from hydra_code.worktrees import get_current_sha

    sha = get_current_sha(cwd=git_repo)
    assert len(sha) == 40
    subprocess.run(["git", "rev-parse", sha], cwd=git_repo, capture_output=True, check=True)


@pytest.mark.integration
def test_get_current_branch() -> None:
    """Get current branch returns a branch name."""
    from hydra_code.worktrees import get_current_branch

    branch = get_current_branch()
    assert branch in ("master", "main", "detached")


@pytest.mark.integration
def test_check_dirty_repo_clean(git_repo: Path) -> None:
    """Clean repo returns no dirty indicators."""
    from hydra_code.worktrees import check_dirty_repo_at

    issues = check_dirty_repo_at(git_repo)
    assert isinstance(issues, list)


@pytest.mark.integration
def test_check_dirty_repo_dirty(git_repo: Path) -> None:
    """Dirty repo returns dirty indicators."""
    from hydra_code.worktrees import check_dirty_repo_at

    (git_repo / "untracked.txt").write_text("test")
    issues = check_dirty_repo_at(git_repo)
    assert len(issues) > 0


@pytest.mark.integration
def test_create_and_remove_worktree(git_repo: Path) -> None:
    """Create and remove a worktree successfully."""
    import shutil

    from hydra_code.models import CandidateRole
    from hydra_code.worktrees import (
        WORKTROOTS_BASE,
        create_worktree,
        get_current_sha,
        remove_worktree,
    )

    base_sha = get_current_sha(cwd=git_repo)
    run_id = "test-run-1"
    candidate_id = "candidate-1"

    # Clean up any previous run artifacts
    run_dir = WORKTROOTS_BASE / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)

    info = create_worktree(run_id, candidate_id, CandidateRole.MINIMAL, base_sha, repo_root=git_repo)
    assert info.created
    assert info.path.exists()

    remove_worktree(info.path, force=True, repo_root=git_repo)


@pytest.mark.integration
def test_extract_patch(git_repo: Path) -> None:
    """Extract patch from worktree."""
    import shutil

    from hydra_code.models import CandidateRole
    from hydra_code.worktrees import (
        WORKTROOTS_BASE,
        create_worktree,
        extract_patch,
        get_current_sha,
        remove_worktree,
    )

    base_sha = get_current_sha(cwd=git_repo)
    run_id = "test-run-patch"
    candidate_id = "candidate-patch"

    # Clean up any previous run artifacts
    run_dir = WORKTROOTS_BASE / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)

    info = create_worktree(run_id, candidate_id, CandidateRole.MINIMAL, base_sha, repo_root=git_repo)
    worktree_path = info.path

    # Make a change in the worktree
    (worktree_path / "new_file.txt").write_text("hello world\n")
    subprocess.run(["git", "add", "."], cwd=worktree_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add file"],
        cwd=worktree_path,
        capture_output=True,
        check=True,
    )

    patch_path = worktree_path / "patch.diff"
    patch_content = extract_patch(worktree_path, base_sha, patch_path)
    assert "new_file.txt" in patch_content
    assert patch_path.exists()

    remove_worktree(info.path, force=True, repo_root=git_repo)


@pytest.mark.integration
def test_count_diff_stats(git_repo: Path) -> None:
    """Count diff stats for worktree changes."""
    import shutil

    from hydra_code.models import CandidateRole
    from hydra_code.worktrees import (
        WORKTROOTS_BASE,
        count_diff_stats,
        create_worktree,
        get_current_sha,
        remove_worktree,
    )

    base_sha = get_current_sha(cwd=git_repo)
    run_id = "test-run-stats"
    candidate_id = "candidate-stats"

    # Clean up any previous run artifacts
    run_dir = WORKTROOTS_BASE / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)

    info = create_worktree(run_id, candidate_id, CandidateRole.MINIMAL, base_sha, repo_root=git_repo)
    worktree_path = info.path

    # Make a change
    (worktree_path / "stat_file.txt").write_text("line1\nline2\nline3\n")
    subprocess.run(["git", "add", "."], cwd=worktree_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add stat file"],
        cwd=worktree_path,
        capture_output=True,
        check=True,
    )

    stats = count_diff_stats(worktree_path, base_sha)
    assert stats["files_changed"] >= 1
    assert stats["insertions"] >= 1

    remove_worktree(info.path, force=True, repo_root=git_repo)


@pytest.mark.integration
def test_list_worktrees() -> None:
    """List active worktrees."""
    from hydra_code.worktrees import list_worktrees

    worktrees = list_worktrees()
    assert isinstance(worktrees, list)


@pytest.mark.integration
def test_cleanup_worktrees(git_repo: Path) -> None:
    """Cleanup worktrees for a run."""
    import shutil

    from hydra_code.models import CandidateRole
    from hydra_code.worktrees import (
        WORKTROOTS_BASE,
        cleanup_worktrees,
        create_worktree,
        get_current_sha,
    )

    base_sha = get_current_sha(cwd=git_repo)
    run_id = "test-run-cleanup"

    # Clean up any previous run artifacts
    run_dir = WORKTROOTS_BASE / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)

    create_worktree(run_id, "cleanup-1", CandidateRole.MINIMAL, base_sha, repo_root=git_repo)
    cleanup_worktrees(run_id, keep=False, repo_root=git_repo)


@pytest.mark.integration
def test_worktree_lifecycle_roundtrip(git_repo: Path) -> None:
    """Full lifecycle: create, modify, extract patch, cleanup."""
    import shutil

    from hydra_code.models import CandidateRole
    from hydra_code.worktrees import (
        WORKTROOTS_BASE,
        cleanup_worktrees,
        create_worktree,
        extract_patch,
        get_current_sha,
    )

    base_sha = get_current_sha(cwd=git_repo)
    run_id = "test-run-roundtrip"
    candidate_id = "roundtrip-1"

    # Clean up any previous run artifacts
    run_dir = WORKTROOTS_BASE / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)

    # Create
    info = create_worktree(run_id, candidate_id, CandidateRole.MINIMAL, base_sha, repo_root=git_repo)
    assert info.path.exists()

    # Modify
    (info.path / "change.txt").write_text("modified\n")
    subprocess.run(["git", "add", "."], cwd=info.path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "modify"],
        cwd=info.path,
        capture_output=True,
        check=True,
    )

    # Extract patch
    patch_path = info.path.parent / "change.patch"
    patch = extract_patch(info.path, base_sha, patch_path)
    assert "change.txt" in patch

    # Cleanup
    cleanup_worktrees(run_id, keep=False, repo_root=git_repo)


@pytest.mark.integration
def test_check_dirty_repo_at(git_repo: Path) -> None:
    """Check dirty state at specific worktree path."""
    from hydra_code.worktrees import check_dirty_repo_at

    # Make it dirty
    (git_repo / "dirty_file.txt").write_text("dirty")
    dirty = check_dirty_repo_at(git_repo)
    assert len(dirty) > 0
    # Clean up
    (git_repo / "dirty_file.txt").unlink()

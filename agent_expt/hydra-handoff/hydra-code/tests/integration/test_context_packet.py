"""Integration tests for context packet generation."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.integration
def test_generate_context_packet_structure(git_repo: Path) -> None:
    """Context packet contains all required sections."""
    from hydra_code.context_packet import generate_context_packet

    packet = generate_context_packet(
        task="Fix the pagination bug",
        repo_root=git_repo,
        base_sha="abc123",
        branch="main",
    )
    assert "# HydraCode Context Packet" in packet
    assert "## Task" in packet
    assert "Fix the pagination bug" in packet
    assert "## Repository" in packet
    assert "abc123" in packet
    assert "## Acceptance Criteria" in packet
    assert "## Repository Structure" in packet
    assert "## Detected Commands" in packet
    assert "## Constraints" in packet
    assert "## Worker Output Contract" in packet


@pytest.mark.integration
def test_context_packet_deterministic(git_repo: Path) -> None:
    """Context packet is deterministic for same inputs."""
    from hydra_code.context_packet import generate_context_packet

    packet1 = generate_context_packet(
        task="Fix bug",
        repo_root=git_repo,
        base_sha="sha1",
        branch="main",
    )
    packet2 = generate_context_packet(
        task="Fix bug",
        repo_root=git_repo,
        base_sha="sha1",
        branch="main",
    )
    assert packet1 == packet2


@pytest.mark.integration
def test_context_packet_includes_git_state(git_repo: Path) -> None:
    """Context packet includes repo structure from git."""
    from hydra_code.context_packet import generate_context_packet

    packet = generate_context_packet(
        task="Test task",
        repo_root=git_repo,
        base_sha="def456",
        branch="feature",
    )
    assert "def456" in packet
    assert "feature" in packet
    # Should include detected test commands
    assert "pytest" in packet or "Test:" in packet


@pytest.mark.integration
def test_context_packet_acceptance_criteria(git_repo: Path) -> None:
    """Context packet includes acceptance criteria when provided."""
    from hydra_code.context_packet import generate_context_packet

    criteria = ["All tests pass", "No regressions"]
    packet = generate_context_packet(
        task="Fix bug",
        repo_root=git_repo,
        base_sha="abc",
        branch="main",
        acceptance_criteria=criteria,
    )
    assert "All tests pass" in packet
    assert "No regressions" in packet


@pytest.mark.integration
def test_context_packet_constraints(git_repo: Path) -> None:
    """Context packet includes constraints when provided."""
    from hydra_code.context_packet import generate_context_packet

    constraints = ["Do not modify API", "Keep changes minimal"]
    packet = generate_context_packet(
        task="Fix bug",
        repo_root=git_repo,
        base_sha="abc",
        branch="main",
        constraints=constraints,
    )
    assert "Do not modify API" in packet
    assert "Keep changes minimal" in packet


@pytest.mark.integration
def test_context_packet_claude_instructions(git_repo: Path) -> None:
    """Context packet includes CLAUDE.md if present."""
    from hydra_code.context_packet import generate_context_packet

    (git_repo / "CLAUDE.md").write_text("# Custom Instructions\nDo X.\n")
    packet = generate_context_packet(
        task="Fix bug",
        repo_root=git_repo,
        base_sha="abc",
        branch="main",
    )
    assert "Custom Instructions" in packet
    assert "Do X" in packet


@pytest.mark.integration
def test_detect_test_commands(git_repo: Path) -> None:
    """Detect test commands based on project files."""
    from hydra_code.context_packet import detect_test_commands

    commands = detect_test_commands(git_repo)
    assert "pytest -q" in commands

    # Add package.json
    (git_repo / "package.json").write_text('{"name": "test"}')
    commands = detect_test_commands(git_repo)
    assert "npm test" in commands


@pytest.mark.integration
def test_detect_build_commands(git_repo: Path) -> None:
    """Detect build/lint commands based on project files."""
    from hydra_code.context_packet import detect_build_commands

    commands = detect_build_commands(git_repo)
    assert "ruff check ." in commands
    assert "mypy src" in commands


@pytest.mark.integration
def test_get_repo_structure(git_repo: Path) -> None:
    """Get repository file structure."""
    from hydra_code.context_packet import get_repo_structure

    structure = get_repo_structure(git_repo)
    assert "README.md" in structure
    assert "pyproject.toml" in structure
    # Should filter out .git/
    assert ".git/" not in structure


@pytest.mark.integration
def test_read_claude_instructions_missing(git_repo: Path) -> None:
    """Return empty string when CLAUDE.md is missing."""
    from hydra_code.context_packet import read_claude_instructions

    result = read_claude_instructions(git_repo)
    assert result == ""

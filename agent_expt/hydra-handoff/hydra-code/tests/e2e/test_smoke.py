"""Smoke and concurrency tests requiring real LLM infrastructure.

These tests verify the full pipeline against a real local LLM (e.g., Qwen
served via vLLM) with the Claude Code CLI. They are gated behind an
environment variable so they skip gracefully in CI without the hardware.

To run:
    HYDRA_SMOKE=1 VLLM_URL=http://localhost:8000 CLAUDE_BIN=/path/to/claude \
    pytest tests/e2e/test_smoke.py -v
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SMOKE_ENABLED = os.environ.get("HYDRA_SMOKE", "0") == "1"


def _get_env(var: str) -> str:
    val = os.environ.get(var, "")
    if not val:
        raise OSError(
            f"Environment variable {var!r} not set. "
            "Set HYDRA_SMOKE=1 to enable smoke tests."
        )
    return val


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.smoke
@pytest.mark.skipif(not SMOKE_ENABLED, reason="Set HYDRA_SMOKE=1 to enable")
def test_smoke_single_agent():
    """Run a single-agent pipeline against a real local LLM."""
    claude_bin = _get_env("CLAUDE_BIN")
    fixture_dir = Path("tests/e2e/fixtures/pagination").resolve()

    result = subprocess.run(
        [
            sys.executable, "-m", "hydra_code.cli", "run",
            "--mode", "fast",
            "--concurrency", "1",
            "--max-turns", "5",
            "--agent-timeout-seconds", "180",
            "--base-ref", "HEAD",
            "--repo-dir", str(fixture_dir),
            "--no-dirty-check",
            "Fix the bug in this repository",
        ],
        capture_output=True,
        text=True,
        timeout=600,
        env={**os.environ, "CLAUDE_BIN": claude_bin},
    )
    assert result.returncode == 0, f"Smoke test failed:\n{result.stderr}"


@pytest.mark.smoke
@pytest.mark.skipif(not SMOKE_ENABLED, reason="Set HYDRA_SMOKE=1 to enable")
def test_smoke_six_worker_concurrency():
    """Run a 6-worker pipeline to verify concurrent execution."""
    claude_bin = _get_env("CLAUDE_BIN")
    fixture_dir = Path("tests/e2e/fixtures/pagination").resolve()

    result = subprocess.run(
        [
            sys.executable, "-m", "hydra_code.cli", "run",
            "--mode", "standard",
            "--concurrency", "6",
            "--max-turns", "5",
            "--agent-timeout-seconds", "300",
            "--base-ref", "HEAD",
            "--repo-dir", str(fixture_dir),
            "--no-dirty-check",
            "Fix the bug in this repository",
        ],
        capture_output=True,
        text=True,
        timeout=1800,
        env={**os.environ, "CLAUDE_BIN": claude_bin},
    )
    assert result.returncode == 0, f"Concurrency test failed:\n{result.stderr}"


@pytest.mark.smoke
@pytest.mark.skipif(not SMOKE_ENABLED, reason="Set HYDRA_SMOKE=1 to enable")
def test_smoke_all_fixtures():
    """Run the pipeline against all fixture repos F1-F7."""
    claude_bin = _get_env("CLAUDE_BIN")

    fixtures = [
        "pagination",
        "cache_isolation",
        "async_race",
        "parser",
        "misleading_test",
        "multi_file",
        "rounding",
    ]

    for fixture in fixtures:
        fixture_path = Path("tests/e2e/fixtures") / fixture
        if not fixture_path.exists():
            pytest.skip(f"Fixture {fixture!r} not found")

        result = subprocess.run(
            [
                sys.executable, "-m", "hydra_code.cli", "run",
                "--mode", "fast",
                "--concurrency", "1",
                "--max-turns", "3",
                "--agent-timeout-seconds", "120",
                "--base-ref", "HEAD",
                "--repo-dir", str(fixture_path.resolve()),
                "--no-dirty-check",
                "Fix the bug in this repository",
            ],
            capture_output=True,
            text=True,
            timeout=600,
            env={**os.environ, "CLAUDE_BIN": claude_bin},
        )
        assert result.returncode == 0, f"Fixture {fixture} failed:\n{result.stderr}"

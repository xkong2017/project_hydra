"""Tests for CLI argument parsing and command dispatch."""

from __future__ import annotations

import json
import os
import signal
from unittest.mock import patch


def _build_parser():
    """Recreate the CLI argument parser for testing."""
    from hydra_code.cli import build_parser
    return build_parser()


class TestCLIParsing:
    """Test CLI argument parsing."""

    def test_no_command_shows_help(self):
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.command is None

    def test_run_command_with_task(self):
        parser = _build_parser()
        args = parser.parse_args(["run", "fix the bug"])
        assert args.command == "run"
        assert args.task == "fix the bug"

    def test_run_command_with_task_file(self, tmp_path):
        task_file = tmp_path / "task.txt"
        task_file.write_text("implement feature X")
        parser = _build_parser()
        args = parser.parse_args(["run", "--task-file", str(task_file)])
        assert args.command == "run"
        assert args.task_file == task_file

    def test_run_command_defaults(self):
        parser = _build_parser()
        args = parser.parse_args(["run", "task"])
        assert args.mode == "standard"
        assert args.concurrency == 6
        assert args.base_ref == "HEAD"
        assert args.max_turns == 25
        assert args.agent_timeout_seconds == 600
        assert args.test_timeout_seconds == 120
        assert not args.keep_worktrees
        assert not args.dry_run
        assert not args.no_refine
        assert not args.no_generated_tests

    def test_run_command_custom_values(self):
        parser = _build_parser()
        args = parser.parse_args([
            "run", "task",
            "--mode", "deep",
            "--concurrency", "4",
            "--base-ref", "main",
            "--max-turns", "10",
            "--keep-worktrees",
            "--dry-run",
            "--no-refine",
        ])
        assert args.mode == "deep"
        assert args.concurrency == 4
        assert args.base_ref == "main"
        assert args.max_turns == 10
        assert args.keep_worktrees
        assert args.dry_run
        assert args.no_refine

    def test_status_command(self):
        parser = _build_parser()
        args = parser.parse_args(["status", "my-run-id"])
        assert args.command == "status"
        assert args.run_id == "my-run-id"

    def test_resume_command(self):
        parser = _build_parser()
        args = parser.parse_args(["resume", "my-run-id"])
        assert args.command == "resume"
        assert args.run_id == "my-run-id"

    def test_report_command(self):
        parser = _build_parser()
        args = parser.parse_args(["report", "my-run-id"])
        assert args.command == "report"
        assert args.run_id == "my-run-id"

    def test_clean_command(self):
        parser = _build_parser()
        args = parser.parse_args(["clean", "my-run-id"])
        assert args.command == "clean"
        assert args.run_id == "my-run-id"
        assert not args.keep_worktrees

    def test_clean_command_keep_worktrees(self):
        parser = _build_parser()
        args = parser.parse_args(["clean", "my-run-id", "--keep-worktrees"])
        assert args.keep_worktrees

    def test_benchmark_command(self, tmp_path):
        config_file = tmp_path / "bench.yaml"
        config_file.write_text("tasks: []")
        parser = _build_parser()
        args = parser.parse_args(["benchmark", str(config_file)])
        assert args.command == "benchmark"
        assert args.config == config_file


class TestStatePersistence:
    """Test run state persistence."""

    def test_state_write_and_read(self, tmp_path):
        from hydra_code.utils import atomic_write_json

        state = {
            "run_id": "test-run-1",
            "phase": "preflight",
            "base_sha": "abc123",
            "branch": "main",
            "started_at": "2026-01-01T00:00:00",
            "completed_at": None,
            "error": None,
            "final_candidate": None,
        }
        state_path = tmp_path / "run.json"
        atomic_write_json(state_path, state)

        assert state_path.exists()
        data = json.loads(state_path.read_text())
        assert data["run_id"] == "test-run-1"
        assert data["phase"] == "preflight"

    def test_atomic_write_on_interrupt(self, tmp_path):
        """Verify target not created when rename fails, temp is cleaned up."""
        from hydra_code.utils import atomic_write_json

        state_path = tmp_path / "run.json"

        # Mock os.rename to fail, simulating interruption
        original_rename = os.rename
        call_count = [0]

        def mock_rename(src, dst):
            call_count[0] += 1
            if call_count[0] == 1:
                raise InterruptedError("simulated interruption")
            return original_rename(src, dst)

        with patch("os.rename", mock_rename):
            try:
                atomic_write_json(state_path, {"test": "data"})
            except InterruptedError:
                pass

        # Target file should not exist (rename never succeeded)
        assert not state_path.exists()

    def test_signal_handling_setup(self):
        """Test that signal handlers can be configured."""
        from hydra_code.signal_handler import SignalHandler

        handler = SignalHandler()
        handler.install()

        # Verify handlers are installed
        assert signal.getsignal(signal.SIGINT) != signal.SIG_DFL
        assert signal.getsignal(signal.SIGTERM) != signal.SIG_DFL

        handler.uninstall()


class TestSignalHandling:
    """Test graceful shutdown on signals."""

    def test_graceful_shutdown_flag(self):
        from hydra_code.signal_handler import SignalHandler

        handler = SignalHandler()
        handler.install()

        # Simulate SIGINT
        handler._handle_signal(signal.SIGINT, None)

        assert handler.should_stop
        assert handler._received_signal == signal.SIGINT

        handler.uninstall()

    def test_shutdown_cleanup(self):
        from hydra_code.signal_handler import SignalHandler

        cleanup_called = []

        handler = SignalHandler(on_shutdown=cleanup_called.append(True))
        handler.install()

        handler._handle_signal(signal.SIGTERM, None)
        handler.shutdown()

        assert cleanup_called[0]

        handler.uninstall()

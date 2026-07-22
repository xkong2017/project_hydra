"""Claude Code subprocess runner."""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import time
from dataclasses import dataclass
from pathlib import Path

from .models import CandidateResult, CandidateRole, CandidateStatus, TrajectorySummary


class RetryableError(Exception):
    """Error that warrants a retry."""
    pass


class FatalError(Exception):
    """Error that should not be retried."""
    pass


@dataclass
class RunnerConfig:
    """Configuration for the Claude runner."""

    max_turns: int = 25
    timeout_seconds: int = 600
    max_retries: int = 3
    retry_base_delay: float = 2.0
    retry_max_delay: float = 60.0
    no_session_persistence: bool = True
    permission_mode: str = "acceptEdits"
    claude_binary: str = "claude"


class ClaudeRunner:
    """Launches and manages Claude Code subprocesses."""

    def __init__(self, config: RunnerConfig | None = None) -> None:
        self.config = config or RunnerConfig()

    def _build_command(self, prompt: str) -> list[str]:
        """Build the claude command line."""
        cmd = [
            self.config.claude_binary,
            "-p",
            "--output-format", "json",
            "--permission-mode", self.config.permission_mode,
            "--max-turns", str(self.config.max_turns),
        ]
        if self.config.no_session_persistence:
            cmd.append("--no-session-persistence")
        cmd.append(prompt)
        return cmd

    def _is_retryable(self, exit_code: int | None, stderr: str) -> bool:
        """Classify whether a failure is retryable."""
        if exit_code is None:
            return True
        retryable_patterns = ["429", "econnreset", "connection reset", "capacity", "timeout"]
        lower_err = stderr.lower()
        return any(pat in lower_err for pat in retryable_patterns)

    def _parse_trajectory(self, text: str, worktree_path: Path) -> TrajectorySummary:
        """Parse Claude session output into a TrajectorySummary.

        Tries JSON parsing first, falls back to regex extraction.
        """
        commands_executed: list[str] = []
        files_edited: list[str] = []
        files_written: list[str] = []
        tests_run: list[str] = []
        failed_approaches: list[str] = []
        known_risks: list[str] = []
        errors: list[str] = []

        # Try JSON parsing first
        try:
            data = json.loads(text)
            if isinstance(data, list):
                for event in data:
                    if isinstance(event, dict):
                        tool = event.get("type", "")
                        if tool == "bash":
                            cmd = event.get("command", "")
                            if cmd:
                                commands_executed.append(cmd)
                        elif tool == "edit":
                            fp = event.get("file_path", "")
                            if fp:
                                files_edited.append(fp)
                        elif tool == "write":
                            fp = event.get("file_path", "")
                            if fp:
                                files_written.append(fp)
                        elif tool in ("error", "exception"):
                            msg = event.get("message", str(event))
                            errors.append(msg)
        except (json.JSONDecodeError, TypeError):
            pass

        # Regex extraction from text output
        for line in text.split("\n"):
            bash_match = re.search(r"Bash\s+(?:tool)?[=:>\-]\s*(.+)", line)
            if bash_match:
                cmd = bash_match.group(1).strip()
                if cmd and cmd not in commands_executed:
                    commands_executed.append(cmd)

            edit_match = re.search(r"Edit\s+.*?(?:file|path)[=:>\-]\s*['\"]?([^'\"\\\s]+)", line)
            if edit_match:
                fp = edit_match.group(1)
                if fp not in files_edited:
                    files_edited.append(fp)

            write_match = re.search(r"Write\s+.*?(?:file|path)[=:>\-]\s*['\"]?([^'\"\\\s]+)", line)
            if write_match:
                fp = write_match.group(1)
                if fp not in files_written:
                    files_written.append(fp)

            if re.search(r"(?:pytest|cargo test|npm test|go test)", line):
                tests_run.append(line.strip())

            if re.search(r"(?:error|Error|FAILED|failed|exception|Exception)", line):
                errors.append(line.strip())

        for err in errors:
            if "failed" in err.lower() or "error" in err.lower():
                failed_approaches.append(err)
            if "risk" in err.lower() or "warning" in err.lower():
                known_risks.append(err)

        all_files = list(dict.fromkeys(files_edited + files_written))

        diff_stats: dict[str, int] = {}
        try:
            from .worktrees import count_diff_stats
            diff_stats = count_diff_stats(worktree_path, "HEAD~1")
        except Exception:
            diff_stats = {"files_changed": len(all_files), "insertions": 0, "deletions": 0}

        return TrajectorySummary(
            candidate_id="",  # Set by caller
            completion_status="completed",
            task_interpretation="",
            relevant_files=all_files,
            commands_executed=commands_executed[:20],
            tests_run=[t for t in tests_run if t],
            changes=[f"Edited: {f}" for f in files_edited] + [f"Written: {f}" for f in files_written],
            diff_stats=diff_stats,
            failed_approaches=failed_approaches[:10],
            known_risks=known_risks[:10],
            self_confidence=0.7 if not errors else 0.5,
        )

    async def run(
        self,
        prompt: str,
        worktree_path: Path,
        candidate_id: str,
        role: CandidateRole | None,
        output_dir: Path,
    ) -> CandidateResult:
        """Run a single Claude Code session."""
        start_time = time.monotonic()
        stdout_path = output_dir / f"{candidate_id}.stdout.log"
        stderr_path = output_dir / f"{candidate_id}.stderr.log"

        last_exception: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                exit_code = await self._execute(
                    prompt=prompt,
                    worktree_path=worktree_path,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                )

                duration = time.monotonic() - start_time

                if exit_code == 0:
                    trajectory = self._parse_trajectory(
                        stdout_path.read_text(encoding="utf-8", errors="replace"),
                        worktree_path,
                    )
                    return CandidateResult(
                        candidate_id=candidate_id,
                        role=role or CandidateRole.MINIMAL,
                        status=CandidateStatus.COMPLETED,
                        worktree_path=worktree_path,
                        duration_seconds=duration,
                        exit_code=exit_code,
                        stdout_path=stdout_path,
                        stderr_path=stderr_path,
                        trajectory=trajectory,
                    )

                # Non-zero exit: check if retryable
                stderr = ""
                if stderr_path.exists():
                    stderr = stderr_path.read_text()

                if attempt < self.config.max_retries and self._is_retryable(exit_code, stderr):
                    delay = min(
                        self.config.retry_base_delay * (2 ** attempt),
                        self.config.retry_max_delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                return CandidateResult(
                    candidate_id=candidate_id,
                    role=role or CandidateRole.MINIMAL,
                    status=CandidateStatus.FAILED,
                    worktree_path=worktree_path,
                    duration_seconds=duration,
                    exit_code=exit_code,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    error=stderr[:500] if stderr else "non-zero exit",
                )

            except TimeoutError:
                duration = time.monotonic() - start_time
                return CandidateResult(
                    candidate_id=candidate_id,
                    role=role or CandidateRole.MINIMAL,
                    status=CandidateStatus.TIMEOUT,
                    worktree_path=worktree_path,
                    duration_seconds=duration,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    error="timeout exceeded",
                )
            except Exception as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    delay = min(
                        self.config.retry_base_delay * (2 ** attempt),
                        self.config.retry_max_delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

        raise last_exception or FatalError("Unknown failure")

    async def _execute(
        self,
        prompt: str,
        worktree_path: Path,
        stdout_path: Path,
        stderr_path: Path,
    ) -> int:
        """Execute the claude subprocess with timeout and streaming output."""
        cmd = self._build_command(prompt)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(worktree_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )

        # Ensure output directory exists before streaming
        stdout_path.parent.mkdir(parents=True, exist_ok=True)

        async def _stream_redirect(source, file):
            """Read from async stream and write chunks to file in real-time."""
            chunks = []
            async for chunk in source:
                file.write(chunk)
                file.flush()
                chunks.append(chunk)
            return b"".join(chunks)

        def _kill_process_group():
            """Kill the entire process group on timeout."""
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass

        def _kill_process_group_hard():
            """Force-kill the entire process group."""
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass

        # Open file handles inside try so finally always closes them
        f_out = open(stdout_path, "wb")
        f_err = open(stderr_path, "wb")

        try:
            # Create concurrent tasks for streaming and waiting
            out_task = asyncio.ensure_future(_stream_redirect(process.stdout, f_out))
            err_task = asyncio.ensure_future(_stream_redirect(process.stderr, f_err))

            # Wait for process with timeout
            exit_task = asyncio.ensure_future(process.wait())

            done, _pending = await asyncio.wait(
                [exit_task],
                timeout=self.config.timeout_seconds,
            )

            if exit_task not in done:
                # Timeout — kill process group
                exit_task.cancel()
                _kill_process_group()
                await asyncio.sleep(2)
                _kill_process_group_hard()

                # Cancel streaming tasks after process is dead
                out_task.cancel()
                err_task.cancel()
                raise TimeoutError("execution exceeded timeout")

            # Process finished normally — collect results from streamers
            try:
                await out_task
            except asyncio.CancelledError:
                pass
            try:
                await err_task
            except asyncio.CancelledError:
                pass

        finally:
            f_out.close()
            f_err.close()

        return process.returncode or 0

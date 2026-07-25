"""Main orchestrator for HydraCode-6."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from . import task_manifest
from .context_packet import generate_context_packet
from .evaluator import CandidateEvaluator
from .gpu_monitor import GpuMonitor, GpuMonitorConfig
from .metrics import MetricsRepository, PipelineMetrics
from .models import (
    STRATEGY_ANGLES,
    CandidateRole,
    CandidateSpec,
    CandidateStatus,
    HardGateResult,
    RefineMode,
    RunConfig,
    RunPhase,
    RunState,
)
from .refinement import (
    build_refinement_packet,
    build_refinement_prompt,
)
from .scheduler import JobPriority, Scheduler
from .tournament import JudgeProvider, MockJudge, TournamentSelector
from .utils import atomic_write_json, generate_run_id, timestamp_now
from .worktrees import (
    check_dirty_repo,
    create_worktree,
    extract_patch,
    get_current_branch,
    get_current_sha,
    get_repo_root,
)

logger = logging.getLogger(__name__)


class Orchestrator:
    """Orchestrates the full HydraCode pipeline."""

    def __init__(self, config: RunConfig, repo_root: Path | None = None) -> None:
        self.config = config
        self.repo_root = repo_root
        self.run_id = generate_run_id()
        self._state: RunState | None = None
        self._gpu_monitor: GpuMonitor | None = None
        # Throughput tracking
        self._candidate_start_time: float | None = None
        self._candidate_completed: int = 0
        self._candidate_lock = asyncio.Lock()

    @property
    def run_dir(self) -> Path:
        """Run output directory."""
        base = self.config.output_dir or Path(".hydra/runs")
        return base / self.run_id

    def _update_phase(self, phase: RunPhase) -> None:
        """Update the current pipeline phase."""
        if self._state:
            self._state.phase = phase
            self._persist_state()

    def _persist_state(self) -> None:
        """Persist run state atomically."""
        if not self._state:
            return
        state_data = {
            "run_id": self._state.run_id,
            "phase": self._state.phase.value,
            "base_sha": self._state.base_sha,
            "branch": self._state.branch,
            "started_at": self._state.started_at,
            "completed_at": self._state.completed_at,
            "error": self._state.error,
            "final_candidate": self._state.final_candidate,
        }
        atomic_write_json(self.run_dir / "run.json", state_data)

    async def run(self) -> str | None:
        """Execute the full HydraCode pipeline."""
        # Preflight
        self._update_phase(RunPhase.PREFLIGHT)
        repo_root = get_repo_root(cwd=self.repo_root)
        base_sha = get_current_sha(self.config.base_ref, cwd=repo_root)
        branch = get_current_branch()

        if not self.config.no_dirty_check:
            dirty = check_dirty_repo()
            if dirty:
                print(f"Dirty repository: {'; '.join(dirty)}")
                print("Commit or stash changes before running HydraCode.")
                return None

        self._state = RunState(
            run_id=self.run_id,
            phase=RunPhase.PREFLIGHT,
            config=self.config,
            repo_root=repo_root,
            base_sha=base_sha,
            branch=branch,
            started_at=timestamp_now(),
        )
        self._persist_state()

        # Context packet
        self._update_phase(RunPhase.CONTEXT_PACKET)
        context = generate_context_packet(
            task=self.config.task,
            repo_root=repo_root,
            base_sha=base_sha,
            branch=branch,
        )
        (self.run_dir / "context-packet.md").write_text(context)

        # Candidate generation
        self._update_phase(RunPhase.CANDIDATE_GENERATION)
        if not self.config.dry_run:
            await self._run_candidates(context, base_sha)
        else:
            print("Dry run: skipping candidate generation")

        # Evaluation
        self._update_phase(RunPhase.EVALUATION)
        if not self.config.dry_run:
            await self._evaluate_candidates(base_sha)

        # Tournament
        self._update_phase(RunPhase.TOURNAMENT)
        if not self.config.dry_run:
            await self._run_tournament()

        # Refinement (optional)
        self._update_phase(RunPhase.REFINEMENT)
        if not self.config.dry_run and self.config.refine_mode != RefineMode.NONE:
            await self._run_refinement(context, base_sha)

        # Final validation
        self._update_phase(RunPhase.FINAL_VALIDATION)
        if not self.config.dry_run:
            await self._final_validation()

        # Reporting
        self._update_phase(RunPhase.REPORTING)
        self._generate_report()

        # Complete
        self._update_phase(RunPhase.COMPLETED)
        if self._state:
            self._state.completed_at = timestamp_now()
            self._persist_state()

        print(f"Run complete: {self.run_id}")
        print(f"Output: {self.run_dir}")
        return self.run_id

    async def _run_candidates(
        self,
        context: str,
        base_sha: str,
    ) -> None:
        """Run all candidate workers concurrently with role replication."""
        num_candidates = self.config.num_candidates

        # Single-agent mode: only run minimal candidate for baseline comparison
        if self.config.single_agent:
            specs = [CandidateSpec(role=CandidateRole.MINIMAL, replica_index=0)]
        else:
            specs = self._generate_candidate_specs(num_candidates)

        # Start GPU monitor for dynamic scaling
        if self.config.enable_gpu_scaling:
            gpu_config = GpuMonitorConfig(
                metrics_url=self.config.gpu_monitor_url,
                min_concurrency=self.config.concurrency // 2,
                max_concurrency=self.config.concurrency,
            )
            self._gpu_monitor = GpuMonitor(gpu_config)
            await self._gpu_monitor.start()

        # Create scheduler with optional dynamic capacity
        dynamic_capacity = None
        if self._gpu_monitor:
            dynamic_capacity = self._gpu_monitor.get_target_concurrency

        scheduler = Scheduler(
            max_concurrent=self.config.concurrency,
            dynamic_capacity=dynamic_capacity,
        )

        # Periodically update scheduler capacity from GPU monitor
        capacity_update_task = None
        if self._gpu_monitor:
            capacity_update_task = asyncio.ensure_future(
                self._capacity_update_loop(scheduler)
            )

        self._candidate_start_time = time.monotonic()
        self._candidate_completed = 0

        jobs = []
        for spec in specs:
            candidate_id = spec.id
            strategy_angle = STRATEGY_ANGLES[spec.replica_index % len(STRATEGY_ANGLES)]
            coro = self._run_single_candidate(
                candidate_id=candidate_id,
                spec=spec,
                context=context,
                base_sha=base_sha,
                strategy_angle=strategy_angle,
            )
            jobs.append((candidate_id, coro, JobPriority.NORMAL))

        results = await scheduler.submit_batch(jobs)

        # Stop GPU monitor
        if capacity_update_task:
            capacity_update_task.cancel()
            try:
                await capacity_update_task
            except asyncio.CancelledError:
                pass
        if self._gpu_monitor:
            await self._gpu_monitor.stop()

        # Log throughput
        self._log_throughput(len(results))

    def _generate_candidate_specs(self, num_candidates: int) -> list[CandidateSpec]:
        """Generate candidate specs by cycling through roles with replicas."""
        specs = []
        roles = list(CandidateRole)
        for i in range(num_candidates):
            role = roles[i % len(roles)]
            replica_index = i // len(roles)
            specs.append(CandidateSpec(role=role, replica_index=replica_index))
        return specs

    async def _capacity_update_loop(self, scheduler: Scheduler) -> None:
        """Periodically update scheduler capacity from GPU monitor."""
        while True:
            await asyncio.sleep(4.0)
            if self._gpu_monitor:
                target = await self._gpu_monitor.get_target_concurrency()
                await scheduler.update_capacity(target)
                logger.info("Scheduler capacity updated to %d", target)

    async def _increment_completed(self) -> None:
        """Thread-safe counter for completed candidates."""
        async with self._candidate_lock:
            self._candidate_completed += 1

    def _log_throughput(self, total_candidates: int) -> None:
        """Log throughput metrics after candidate generation."""
        if self._candidate_start_time is None:
            return
        elapsed = time.monotonic() - self._candidate_start_time
        candidates_per_minute = total_candidates / (elapsed / 60.0) if elapsed > 0 else 0.0

        throughput_data: dict[str, object] = {
            "total_candidates": total_candidates,
            "completed": self._candidate_completed,
            "elapsed_seconds": round(elapsed, 2),
            "candidates_per_minute": round(candidates_per_minute, 2),
        }
        if self._gpu_monitor:
            throughput_data["gpu_diagnostics"] = self._gpu_monitor.get_diagnostics()

        atomic_write_json(self.run_dir / "throughput.json", throughput_data)
        print(f"  Throughput: {total_candidates} candidates in {elapsed:.1f}s ({candidates_per_minute:.1f}/min)")

    async def _run_single_candidate(
        self,
        candidate_id: str,
        spec: CandidateSpec,
        context: str,
        base_sha: str,
        strategy_angle: str = "",
    ) -> None:
        """Run a single candidate worker with role replication support."""
        role = spec.role
        replica_index = spec.replica_index

        # Create worktree
        worktree_info = create_worktree(
            self.run_id, candidate_id, role, base_sha
        )

        # Build prompt with per-replica diversity
        prompt = f"{context}\n\n## Role: {role.value}"
        if replica_index > 0:
            prompt += f" (Replica {replica_index})"
        prompt += "\n"
        role_instructions = {
            CandidateRole.MINIMAL: "Prefer the smallest correct patch. Avoid unrelated refactoring.",
            CandidateRole.ROOT_CAUSE: "Trace data flow and control flow. Establish root cause before editing.",
            CandidateRole.TEST_DRIVEN: "Reproduce the failure first. Write a failing test before the fix.",
            CandidateRole.ARCHITECTURE: "Examine APIs, module boundaries, and compatibility.",
            CandidateRole.ADVERSARIAL: "Search for edge cases, hidden regressions, and invalid assumptions.",
            CandidateRole.ALTERNATIVE: "Challenge the obvious fix. Explore a different solution strategy.",
        }
        prompt += f"\n{role_instructions.get(role, '')}\n"
        if strategy_angle:
            prompt += f"\n## Approach: {strategy_angle}\n"

        # Run session — use local API or Claude CLI
        from .claude_runner import ClaudeRunner, RunnerConfig
        from .local_api_runner import LocalApiRunner, RunnerConfig as LocalRunnerConfig

        if self.config.use_local_api:
            runner: ClaudeRunner | LocalApiRunner = LocalApiRunner(
                LocalRunnerConfig(
                    timeout_seconds=self.config.agent_timeout_seconds,
                    max_tokens=self.config.max_tokens or 8192,
                    temperature=0.3,
                )
            )
        else:
            runner = ClaudeRunner(
                RunnerConfig(
                    max_turns=self.config.max_turns,
                    timeout_seconds=self.config.agent_timeout_seconds,
                    claude_binary=self.config.claude_binary or "claude",
                )
            )

        output_dir = self.run_dir / "candidates" / candidate_id
        output_dir.mkdir(parents=True, exist_ok=True)

        result = await runner.run(
            prompt=prompt,
            worktree_path=worktree_info.path,
            candidate_id=candidate_id,
            role=role,
            output_dir=output_dir,
        )

        # Extract patch
        patch_path = output_dir / "candidate.patch"
        try:
            extract_patch(worktree_info.path, base_sha, patch_path)
            result.patch_path = patch_path
        except Exception:
            pass

        # Store result
        if self._state:
            self._state.candidates[candidate_id] = result

        # Increment completed counter
        await self._increment_completed()

        # Persist candidate summary
        summary_data = {
            "candidate_id": candidate_id,
            "role": role.value,
            "replica_index": replica_index,
            "status": result.status.value,
            "duration": result.duration_seconds,
            "exit_code": result.exit_code,
        }
        atomic_write_json(output_dir / "summary.json", summary_data)

    async def _evaluate_candidates(self, base_sha: str) -> None:
        """Run evaluation: test matrix, hard gates, and scoring."""
        if not self._state or not self._state.candidates:
            print("  No candidates to evaluate")
            return

        evaluator = CandidateEvaluator(
            weights=self.config.score_weights,
            test_timeout=self.config.test_timeout_seconds,
        )

        # Build test commands from task context
        # For now, use a simple pass test - in real usage, this would come from task manifest
        test_commands = self._build_test_commands()

        # Run test matrix
        matrix = await evaluator.run_test_matrix(
            self._state.candidates,
            test_commands,
            base_sha,
        )
        self._state.test_matrix = matrix

        # Check hard gates for each candidate
        gates: dict[str, HardGateResult] = {}
        for candidate_id, result in self._state.candidates.items():
            gate = await evaluator.check_hard_gates_async(result, matrix, base_sha)
            gates[candidate_id] = gate

        # Compute scores
        scores = evaluator.compute_scores(self._state.candidates, matrix, gates)

        # Store results
        self._state.scores = scores
        self._state.hard_gates = gates

        # Write evaluation results
        eval_data = {
            "test_matrix": {
                "candidates": matrix.candidates,
                "tests": matrix.tests,
                "results": [
                    {
                        "candidate_id": e.candidate_id,
                        "test_id": e.test_id,
                        "verdict": e.verdict.value,
                    }
                    for e in matrix.results
                ],
            },
            "hard_gates": {
                cid: {
                    "passed": g.passed,
                    "reasons": g.rejection_reasons,
                }
                for cid, g in gates.items()
            },
            "scores": {
                cid: {
                    "total": s.total_score,
                    "issue_specific": s.issue_specific_score,
                    "regression": s.regression_score,
                    "build_lint": s.build_lint_score,
                    "minimality": s.minimality_score,
                    "hard_gate_passed": s.hard_gate_passed,
                }
                for cid, s in scores.items()
            },
        }
        atomic_write_json(self.run_dir / "evaluation.json", eval_data)

        # Print summary
        sorted_scores = sorted(scores.items(), key=lambda x: x[1].total_score, reverse=True)
        print(f"  Evaluation complete: {len(sorted_scores)} candidates scored")
        for cid, score in sorted_scores[:3]:
            print(f"    {cid}: {score.total_score:.3f}")

    async def _run_tournament(self) -> None:
        """Run tournament to select the best candidate."""
        if not self._state or not self._state.candidates:
            print("  No candidates for tournament")
            return

        # Build context for judges
        context = {
            "scores": {
                cid: s.total_score for cid, s in self._state.scores.items()
            },
            "hard_gates": {
                cid: g.passed for cid, g in self._state.hard_gates.items()
            },
        }

        # Create judge(s)
        judges: list[JudgeProvider] = [MockJudge()]

        # Add real judge if configured
        # TODO: Add RealJudge that uses Claude API for actual evaluation

        tournament = TournamentSelector(judges=judges, judges_per_group=3)
        candidate_ids = list(self._state.candidates.keys())
        result = tournament.select(candidate_ids, self.config.task, context)

        # Store tournament result
        tournament_data = {
            "group_id": result.group_id,
            "candidates": result.candidates,
            "winner": result.winner,
            "is_tie": result.is_tie,
            "needs_distinguishing_test": result.needs_distinguishing_test,
            "judge_results": [
                {
                    "judge_id": jr.judge_id,
                    "winner": jr.winner,
                    "ranking": jr.ranking,
                    "confidence": jr.confidence,
                }
                for jr in result.judge_results
            ],
            "vote_counts": result.vote_counts,
        }
        atomic_write_json(self.run_dir / "tournament.json", tournament_data)

        # Store in state
        self._state.tournament_results = [result]

        print(f"  Tournament complete: winner = {result.winner}")
        if result.is_tie:
            print("  Warning: Tournament resulted in a tie")

    async def _run_refinement(self, context: str, base_sha: str) -> None:
        """Run refinement on the top candidate."""
        if not self._state or not self._state.candidates:
            return

        # Find the top candidate by score
        if not self._state.scores:
            print("  No scores available for refinement")
            return

        sorted_scores = sorted(
            self._state.scores.items(),
            key=lambda x: x[1].total_score,
            reverse=True,
        )
        top_candidate_id = sorted_scores[0][0]
        parent = self._state.candidates.get(top_candidate_id)

        if not parent:
            return

        # Build refinement packet
        all_candidates = list(self._state.candidates.values())
        packet = build_refinement_packet(
            parent,
            all_candidates,
            tournament_feedback=[f"Selected by tournament: {top_candidate_id}"],
        )

        # Build refinement prompt
        context_packet = (self.run_dir / "context-packet.md").read_text()
        prompt = build_refinement_prompt(packet, context_packet)

        # Create refinement worktree
        refiner_id = f"{top_candidate_id}-refine"
        worktree_info = create_worktree(self.run_id, refiner_id, None, base_sha)

        # Run refinement
        from .claude_runner import ClaudeRunner, RunnerConfig

        runner = ClaudeRunner(
            RunnerConfig(
                max_turns=self.config.max_turns,
                timeout_seconds=self.config.agent_timeout_seconds,
                claude_binary=self.config.claude_binary or "claude",
            )
        )

        output_dir = self.run_dir / "refinements" / refiner_id
        output_dir.mkdir(parents=True, exist_ok=True)

        result = await runner.run(
            prompt=prompt,
            worktree_path=worktree_info.path,
            candidate_id=refiner_id,
            role=None,  # Refiner doesn't have a role
            output_dir=output_dir,
        )

        # Store refinement result
        if self._state:
            self._state.candidates[refiner_id] = result

        refinement_data = {
            "parent_candidate_id": top_candidate_id,
            "refined_candidate_id": refiner_id,
            "status": result.status.value,
            "duration": result.duration_seconds,
        }
        atomic_write_json(self.run_dir / "refinement.json", refinement_data)

        print(f"  Refinement complete: {refiner_id}")

    async def _final_validation(self) -> None:
        """Run final validation on the selected candidate."""
        if not self._state:
            return

        # Find the winner
        winner_id = self._state.final_candidate
        if not winner_id:
            # Default to top-scoring candidate
            if self._state.scores:
                sorted_scores = sorted(
                    self._state.scores.items(),
                    key=lambda x: x[1].total_score,
                    reverse=True,
                )
                winner_id = sorted_scores[0][0]
                self._state.final_candidate = winner_id

        if not winner_id:
            print("  No candidate selected for final validation")
            return

        winner = self._state.candidates.get(winner_id)
        if not winner:
            print(f"  Winner {winner_id} not found")
            return

        # Run validation tests
        validation_tests = self._build_validation_tests()
        results = []
        all_passed = True

        for test_cmd in validation_tests:
            proc_returncode = -1
            try:
                proc = await asyncio.create_subprocess_exec(
                    *test_cmd.split(),
                    cwd=str(winner.worktree_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _stdout, _stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.config.test_timeout_seconds,
                )
                proc_returncode = proc.returncode if proc.returncode is not None else -1
                passed = proc_returncode == 0
            except TimeoutError:
                proc.kill()
                passed = False
                proc_returncode = -1
            except (OSError, FileNotFoundError):
                passed = False
                proc_returncode = -1

            results.append({
                "command": test_cmd,
                "passed": passed,
                "exit_code": proc_returncode,
            })
            if not passed:
                all_passed = False

        # Write validation results
        validation_data = {
            "candidate_id": winner_id,
            "all_passed": all_passed,
            "tests": results,
        }
        atomic_write_json(self.run_dir / "validation.json", validation_data)

        print(f"  Final validation: {'PASS' if all_passed else 'FAIL'}")

    def _build_test_commands(self) -> list[str]:
        """Build test commands from task manifest or repo detection."""
        manifest_obj = task_manifest.load_or_detect(self.repo_root)
        return manifest_obj.test_commands

    def _build_validation_tests(self) -> list[str]:
        """Build validation tests from task manifest FAIL_TO_PASS cases."""
        manifest_obj = task_manifest.load_or_detect(self.repo_root)
        return manifest_obj.validation_commands

    def _generate_report(self) -> None:
        """Generate final run report."""
        if not self._state:
            return

        # Collect metrics
        total_candidates = len(self._state.candidates)
        completed = sum(
            1 for c in self._state.candidates.values()
            if c.status in [CandidateStatus.COMPLETED, CandidateStatus.SELECTED]
        )
        failed = sum(
            1 for c in self._state.candidates.values()
            if c.status == CandidateStatus.FAILED
        )

        # Calculate success rate
        success_rate = 0.0
        successful = 0
        if self._state.scores:
            # Count candidates with score > 0.5 as "successful"
            successful = sum(
                1 for s in self._state.scores.values()
                if s.total_score > 0.5 and s.hard_gate_passed
            )
            success_rate = successful / total_candidates if total_candidates else 0.0

        report = {
            "run_id": self._state.run_id,
            "phase": self._state.phase.value,
            "base_sha": self._state.base_sha,
            "branch": self._state.branch,
            "started_at": self._state.started_at,
            "completed_at": self._state.completed_at,
            "final_candidate": self._state.final_candidate,
            "metrics": {
                "total_candidates": total_candidates,
                "completed": completed,
                "failed": failed,
                "success_rate": success_rate,
            },
        }

        atomic_write_json(self.run_dir / "report.json", report)
        print(f"  Report: {total_candidates} candidates, {success_rate:.1%} success rate")

        # Persist PipelineMetrics for cross-run comparison
        pipeline_metrics = PipelineMetrics(
            run_id=self.run_id,
            mode="single" if self.config.single_agent else "multi",
            total_candidates=total_candidates,
            completed_candidates=completed,
            failed_candidates=failed,
            successful_candidates=successful,
            duration_seconds=0.0,  # Would need start time tracking
            task_id=self._state.config.task_file.name if self._state.config.task_file else None,
            winner=self._state.final_candidate,
        )
        metrics_repo = MetricsRepository()
        metrics_repo.store(pipeline_metrics)

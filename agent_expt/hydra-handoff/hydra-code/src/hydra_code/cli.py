"""CLI entry point for HydraCode-6."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from .config import build_run_config


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="hydra-code",
        description="Parallel test-time scaling for local agentic coding",
    )
    subparsers = parser.add_subparsers(dest="command")

    # run
    run_parser = subparsers.add_parser("run", help="Start a new HydraCode run")
    run_parser.add_argument("task", nargs="?", default=None, help="Coding task description")
    run_parser.add_argument("--task-file", type=Path, help="File containing task description")
    run_parser.add_argument("--mode", choices=["fast", "standard", "deep"], default="standard")
    run_parser.add_argument("--concurrency", type=int, default=6)
    run_parser.add_argument("--base-ref", default="HEAD")
    run_parser.add_argument("--max-turns", type=int, default=25)
    run_parser.add_argument("--agent-timeout-seconds", type=int, default=600)
    run_parser.add_argument("--test-timeout-seconds", type=int, default=120)
    run_parser.add_argument("--keep-worktrees", action="store_true")
    run_parser.add_argument("--output-dir", type=Path)
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--no-refine", action="store_true")
    run_parser.add_argument("--no-generated-tests", action="store_true")
    run_parser.add_argument("--repo-dir", type=Path, default=None, help="Target repo directory (default: current dir)")
    run_parser.add_argument("--no-dirty-check", action="store_true", help="Skip dirty repo check")

    # resume
    resume_parser = subparsers.add_parser("resume", help="Resume an interrupted run")
    resume_parser.add_argument("run_id", help="Run ID to resume")

    # status
    status_parser = subparsers.add_parser("status", help="Show run status")
    status_parser.add_argument("run_id", help="Run ID")

    # report
    report_parser = subparsers.add_parser("report", help="Show run report")
    report_parser.add_argument("run_id", help="Run ID")

    # clean
    clean_parser = subparsers.add_parser("clean", help="Clean up run artifacts")
    clean_parser.add_argument("run_id", help="Run ID")
    clean_parser.add_argument("--keep-worktrees", action="store_true")

    # benchmark
    bench_parser = subparsers.add_parser("benchmark", help="Run benchmark suite")
    bench_parser.add_argument("config", type=Path, help="Benchmark YAML config")

    # evaluate (engine subcommand — for dynamic workflow use)
    eval_parser = subparsers.add_parser("evaluate", help="Evaluate candidates against test matrix")
    eval_parser.add_argument("run_id", help="Run ID containing candidates")
    eval_parser.add_argument("--output", type=Path, default=None, help="Output path for scores JSON")

    # tournament (engine subcommand — for dynamic workflow use)
    tourn_parser = subparsers.add_parser("tournament", help="Run tournament selection on scored candidates")
    tourn_parser.add_argument("scores", type=Path, help="Scores JSON path")
    tourn_parser.add_argument("--output", type=Path, default=None, help="Output path for result JSON")

    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "run":
        cmd_run(args)
    elif args.command == "resume":
        cmd_resume(args.run_id)
    elif args.command == "status":
        cmd_status(args.run_id)
    elif args.command == "report":
        cmd_report(args.run_id)
    elif args.command == "clean":
        cmd_clean(args.run_id, args.keep_worktrees)
    elif args.command == "benchmark":
        cmd_benchmark(args.config)
    elif args.command == "evaluate":
        cmd_evaluate(args.run_id, args.output)
    elif args.command == "tournament":
        cmd_tournament(args.scores, args.output)
    else:
        parser.print_help()
        sys.exit(1)


def cmd_run(args: argparse.Namespace) -> None:
    """Handle the run command."""
    if not args.task and not args.task_file:
        print("Error: Provide a task description or --task-file", file=sys.stderr)
        sys.exit(1)

    if args.task_file:
        task = args.task_file.read_text()
    else:
        task = args.task or ""

    # Change to target repo directory if specified
    if args.repo_dir:
        os.chdir(str(args.repo_dir))

    config = build_run_config(
        task=task,
        mode=args.mode,
        concurrency=args.concurrency,
        base_ref=args.base_ref,
        max_turns=args.max_turns,
        agent_timeout=args.agent_timeout_seconds,
        test_timeout=args.test_timeout_seconds,
        keep_worktrees=args.keep_worktrees,
        output_dir=str(args.output_dir) if args.output_dir else None,
        dry_run=args.dry_run,
        no_refine=args.no_refine,
        no_generated_tests=args.no_generated_tests,
        no_dirty_check=args.no_dirty_check,
    )

    from .orchestrator import Orchestrator
    from .signal_handler import SignalHandler

    handler = SignalHandler()
    handler.install()

    orchestrator = Orchestrator(config)
    try:
        result = asyncio.run(orchestrator.run())
        if result:
            print(f"Run complete: {result}")
        else:
            print("Run completed with no selection")
    except Exception as e:
        print(f"Run failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if handler.should_stop:
            handler.shutdown()
        handler.uninstall()


def cmd_resume(run_id: str) -> None:
    """Handle the resume command."""

    from .config import build_run_config
    from .orchestrator import Orchestrator
    from .signal_handler import SignalHandler

    state_path = Path(".hydra/runs") / run_id / "run.json"
    if not state_path.exists():
        print(f"Run {run_id} not found", file=sys.stderr)
        sys.exit(1)

    state = json.loads(state_path.read_text())
    print(f"Resuming run {run_id} from phase: {state.get('phase', 'unknown')}")

    config = build_run_config(
        task=state.get("task", ""),
    )

    handler = SignalHandler()
    handler.install()

    orchestrator = Orchestrator(config)
    try:
        result = asyncio.run(orchestrator.run())
        if result:
            print(f"Run complete: {result}")
        else:
            print("Run completed with no selection")
    except Exception as e:
        print(f"Run failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if handler.should_stop:
            handler.shutdown()
        handler.uninstall()


def cmd_status(run_id: str) -> None:
    """Handle the status command."""
    state_path = Path(".hydra/runs") / run_id / "run.json"
    if not state_path.exists():
        print(f"Run {run_id} not found", file=sys.stderr)
        sys.exit(1)

    state = json.loads(state_path.read_text())
    print(f"Run ID: {run_id}")
    print(f"Phase: {state.get('phase', 'unknown')}")
    print(f"Candidates: {len(state.get('candidates', {}))}")
    if state.get("final_candidate"):
        print(f"Final: {state['final_candidate']}")
    if state.get("error"):
        print(f"Error: {state['error']}")


def cmd_report(run_id: str) -> None:
    """Handle the report command."""
    report_path = Path(".hydra/runs") / run_id / "report.md"
    if not report_path.exists():
        print(f"Report not found for run {run_id}", file=sys.stderr)
        sys.exit(1)

    print(report_path.read_text())


def cmd_clean(run_id: str, keep_worktrees: bool) -> None:
    """Handle the clean command."""
    from .worktrees import cleanup_worktrees

    cleanup_worktrees(run_id, keep=keep_worktrees)
    print(f"Cleaned run {run_id}" + (" (kept worktrees)" if keep_worktrees else ""))


def cmd_benchmark(config_path: Path) -> None:
    """Handle the benchmark command."""
    import yaml

    config = yaml.safe_load(config_path.read_text())
    print(f"Benchmark config loaded: {len(config.get('tasks', []))} tasks")
    print("Benchmark execution not yet fully implemented")


def cmd_evaluate(run_id: str, output: Path | None) -> None:
    """Evaluate candidates from a run and produce scores."""
    run_dir = Path(".hydra/runs") / run_id
    state_path = run_dir / "run.json"
    if not state_path.exists():
        print(f"Run {run_id} not found", file=sys.stderr)
        sys.exit(1)

    from .evaluator import CandidateEvaluator
    from .models import CandidateResult, TestMatrix

    state = json.loads(state_path.read_text())
    candidates: dict[str, CandidateResult] = {}
    for cid, cdata in state.get("candidates", {}).items():
        candidates[cid] = CandidateResult.model_validate(cdata)

    matrix = TestMatrix()
    matrix_path = run_dir / "test_matrix.json"
    if matrix_path.exists():
        matrix = TestMatrix.model_validate(json.loads(matrix_path.read_text()))

    evaluator = CandidateEvaluator()
    gates = {}
    for cid, candidate in candidates.items():
        gate = evaluator.check_hard_gates(candidate, matrix, state.get("base_ref", "HEAD"))
        gates[cid] = gate

    scores = evaluator.compute_scores(candidates, matrix, gates)

    scores_data = {
        cid: {
            "total_score": s.total_score,
            "hard_gate_passed": s.hard_gate_passed,
            "hard_gate_reasons": s.hard_gate_reasons,
            "issue_specific_score": s.issue_specific_score,
            "regression_score": s.regression_score,
            "build_lint_score": s.build_lint_score,
        }
        for cid, s in scores.items()
    }

    output_path = output or run_dir / "scores.json"
    output_path.write_text(json.dumps(scores_data, indent=2))
    print(f"Scores written to {output_path}")
    for cid, s in scores_data.items():
        status = "PASS" if s["hard_gate_passed"] else "FAIL"
        print(f"  {cid}: {s['total_score']:.3f} [{status}]")


def cmd_tournament(scores_path: Path, output: Path | None) -> None:
    """Run tournament selection on scored candidates."""
    if not scores_path.exists():
        print(f"Scores file not found: {scores_path}", file=sys.stderr)
        sys.exit(1)

    from .tournament import MockJudge, TournamentSelector

    scores_data = json.loads(scores_path.read_text())
    candidate_ids = list(scores_data.keys())

    if len(candidate_ids) < 2:
        print(f"Not enough candidates for tournament: {len(candidate_ids)}")
        if candidate_ids:
            output_path = output or scores_path.parent / "tournament.json"
            output_path.write_text(json.dumps({
                "winner": candidate_ids[0],
                "is_tie": False,
                "candidates": candidate_ids,
            }, indent=2))
        return

    selector = TournamentSelector(judges=[
        MockJudge(preference=candidate_ids),
        MockJudge(preference=list(reversed(candidate_ids))),
        MockJudge(preference=candidate_ids),
    ])
    result = selector.select(candidate_ids, "", {})

    output_path = output or scores_path.parent / "tournament.json"
    output_path.write_text(json.dumps({
        "winner": result.winner,
        "is_tie": result.is_tie,
        "candidates": candidate_ids,
        "scores_path": str(scores_path),
    }, indent=2))
    print(f"Tournament result written to {output_path}")
    print(f"Winner: {result.winner}" + (" (tie)" if result.is_tie else ""))


if __name__ == "__main__":
    main()

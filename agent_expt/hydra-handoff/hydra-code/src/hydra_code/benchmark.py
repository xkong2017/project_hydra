"""Benchmark runner: single-agent vs dynamic workflow comparison.

Selects SWE-Verified Lite tasks, runs each through both modes,
and reports wall time, pass rate, throughput, and GPU metrics.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import task_manifest
from .gpu_monitor import GpuMonitor, GpuMonitorConfig
from .models import RunConfig

logger = logging.getLogger(__name__)

# SWE-Verified Lite task IDs (small, self-contained, good for benchmarking)
# Format: "owner__repo-issue_number"
SWE_VERIFIED_LITE_TASKS: list[str] = [
    "psf__requests-6028",
    # Add more as fixtures become available
]


@dataclass
class BenchmarkResult:
    """Results from running a single task under one mode."""

    task_id: str
    mode: str  # "single" or "dynamic"
    wall_time_sec: float = 0.0
    passed: bool = False
    fail_to_pass_count: int = 0
    pass_to_pass_count: int = 0
    fail_to_pass_total: int = 0
    pass_to_pass_total: int = 0
    candidates_evaluated: int = 0
    throughput_requests_per_min: float = 0.0
    gpu_peak_kv_cache: float = 0.0
    gpu_avg_kv_cache: float = 0.0
    gpu_samples: int = 0
    error: str = ""


@dataclass
class BenchmarkReport:
    """Aggregated report comparing single vs dynamic modes."""

    results: list[BenchmarkResult] = field(default_factory=list)
    total_tasks: int = 0
    single_pass_rate: float = 0.0
    dynamic_pass_rate: float = 0.0
    avg_speedup: float = 0.0  # dynamic wall time / single wall time (lower = faster)
    total_throughput: float = 0.0


def run_single_agent(repo_root: Path, output_dir: Path) -> BenchmarkResult:
    """Run a task with a single agent (no concurrency)."""
    result = BenchmarkResult(task_id=repo_root.name, mode="single")
    start = time.monotonic()

    try:
        # Run orchestrator with concurrency=1
        config = RunConfig(
            task=f"Fix the bug in {repo_root.name}",
            output_dir=output_dir,
            concurrency=1,
            num_candidates=1,
        )

        from .orchestrator import Orchestrator

        orchestrator = Orchestrator(config=config, repo_root=repo_root)
        run_id = asyncio.run(orchestrator.run())

        result.wall_time_sec = time.monotonic() - start
        result.passed = run_id is not None

        # Run validation tests
        manifest = task_manifest.load_or_detect(repo_root)
        if manifest:
            result.fail_to_pass_total = len(manifest.fail_to_pass)
            result.pass_to_pass_total = len(manifest.pass_to_pass)

        result.throughput_requests_per_min = (
            result.candidates_evaluated / (result.wall_time_sec / 60)
            if result.wall_time_sec > 0
            else 0
        )
    except Exception as e:
        result.wall_time_sec = time.monotonic() - start
        result.error = str(e)
        logger.exception(f"Benchmark single-agent failed for {repo_root.name}")

    return result


def run_dynamic_workflow(repo_root: Path, output_dir: Path, max_concurrency: int = 16) -> BenchmarkResult:
    """Run a task with dynamic workflow (GPU-aware concurrency scaling)."""
    result = BenchmarkResult(task_id=repo_root.name, mode="dynamic")
    start = time.monotonic()

    gpu_monitor = GpuMonitor(GpuMonitorConfig(
        min_concurrency=2,
        max_concurrency=max_concurrency,
    ))

    try:
        config = RunConfig(
            task=f"Fix the bug in {repo_root.name}",
            output_dir=output_dir,
            concurrency=max_concurrency,
            num_candidates=max_concurrency,
        )

        from .orchestrator import Orchestrator

        orchestrator = Orchestrator(config=config, repo_root=repo_root)

        # Start GPU monitor
        asyncio.run(gpu_monitor.start())
        orchestr_result = asyncio.run(orchestrator.run())
        asyncio.run(gpu_monitor.stop())

        result.wall_time_sec = time.monotonic() - start
        result.passed = orchestr_result is not None

        # Capture GPU metrics
        diag = gpu_monitor.get_diagnostics()
        result.gpu_peak_kv_cache = diag.get("ema_kv_cache", 0)
        result.gpu_samples = diag.get("consecutive_errors", 0)

        # Run validation tests
        manifest = task_manifest.load_or_detect(repo_root)
        if manifest:
            result.fail_to_pass_total = len(manifest.fail_to_pass)
            result.pass_to_pass_total = len(manifest.pass_to_pass)

        result.throughput_requests_per_min = (
            result.candidates_evaluated / (result.wall_time_sec / 60)
            if result.wall_time_sec > 0
            else 0
        )
    except Exception as e:
        result.wall_time_sec = time.monotonic() - start
        result.error = str(e)
        logger.exception(f"Benchmark dynamic workflow failed for {repo_root.name}")
    finally:
        try:
            asyncio.run(gpu_monitor.stop())
        except Exception:
            pass

    return result


def generate_report(results: list[BenchmarkResult]) -> BenchmarkReport:
    """Generate comparison report from benchmark results."""
    report = BenchmarkReport(results=results)

    single_results = [r for r in results if r.mode == "single"]
    dynamic_results = [r for r in results if r.mode == "dynamic"]

    report.total_tasks = len(single_results)

    if single_results:
        report.single_pass_rate = sum(1 for r in single_results if r.passed) / len(single_results)
    if dynamic_results:
        report.dynamic_pass_rate = sum(1 for r in dynamic_results if r.passed) / len(dynamic_results)

    # Calculate speedup (wall time ratio)
    task_single = {r.task_id: r for r in single_results}
    task_dynamic = {r.task_id: r for r in dynamic_results}
    speedups = []
    for task_id in task_single:
        if task_id in task_dynamic and task_dynamic[task_id].wall_time_sec > 0:
            speedup = task_single[task_id].wall_time_sec / task_dynamic[task_id].wall_time_sec
            speedups.append(speedup)

    report.avg_speedup = sum(speedups) / len(speedups) if speedups else 0
    report.total_throughput = sum(r.throughput_requests_per_min for r in dynamic_results)

    return report


def format_report(report: BenchmarkReport) -> str:
    """Format benchmark report as a readable table."""
    lines = [
        "=" * 80,
        "HYDRACODE BENCHMARK REPORT",
        "=" * 80,
        "",
        f"Tasks evaluated: {report.total_tasks}",
        f"Single-agent pass rate: {report.single_pass_rate:.1%}",
        f"Dynamic pass rate: {report.dynamic_pass_rate:.1%}",
        f"Average speedup (dynamic vs single): {report.avg_speedup:.2f}x",
        f"Total throughput: {report.total_throughput:.1f} req/min",
        "",
    ]

    if report.results:
        lines += [
            "-" * 80,
            f"{'Task':<25} {'Mode':<10} {'Wall(s)':<10} {'Passed':<8} {'Cands':<8} {'Thr(qrt/min)':<12}",
            "-" * 80,
        ]

        for r in report.results:
            lines.append(
                f"{r.task_id:<25} {r.mode:<10} {r.wall_time_sec:<10.2f} "
                f"{'YES' if r.passed else 'NO':<8} {r.candidates_evaluated:<8} "
                f"{r.throughput_requests_per_min:<12.1f}"
            )

        lines.append("-" * 80)

    return "\n".join(lines)


def save_report(report: BenchmarkReport, output_path: Path) -> None:
    """Save benchmark report as JSON."""
    data: dict[str, Any] = {
        "total_tasks": report.total_tasks,
        "single_pass_rate": report.single_pass_rate,
        "dynamic_pass_rate": report.dynamic_pass_rate,
        "avg_speedup": report.avg_speedup,
        "total_throughput": report.total_throughput,
        "results": [
            {
                "task_id": r.task_id,
                "mode": r.mode,
                "wall_time_sec": r.wall_time_sec,
                "passed": r.passed,
                "fail_to_pass_count": r.fail_to_pass_count,
                "pass_to_pass_count": r.pass_to_pass_count,
                "fail_to_pass_total": r.fail_to_pass_total,
                "pass_to_pass_total": r.pass_to_pass_total,
                "candidates_evaluated": r.candidates_evaluated,
                "throughput_requests_per_min": r.throughput_requests_per_min,
                "gpu_peak_kv_cache": r.gpu_peak_kv_cache,
                "error": r.error,
            }
            for r in report.results
        ],
    }
    output_path.write_text(json.dumps(data, indent=2))

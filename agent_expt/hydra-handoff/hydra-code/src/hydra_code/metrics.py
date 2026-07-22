"""Metrics collection for vLLM and HydraCode pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass
class VLLMMetrics:
    """Parsed vLLM metrics snapshot."""

    timestamp: float = 0.0
    running_requests: int | None = None
    waiting_requests: int | None = None
    kv_cache_usage: float | None = None
    prefix_cache_hits: int | None = None
    prefix_cache_queries: int | None = None
    prompt_tokens_per_sec: float | None = None
    generation_tokens_per_sec: float | None = None
    preemptions: int | None = None
    total_wall_time: float | None = None


class MetricsCollector:
    """Poll and parse vLLM /metrics endpoint."""

    def __init__(self, metrics_url: str = "http://127.0.0.1:8000/metrics") -> None:
        self._url = metrics_url
        self._snapshots: list[VLLMMetrics] = []

    async def collect(self) -> VLLMMetrics | None:
        """Collect one metrics snapshot."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                text = await client.get(self._url)
                return self._parse(text.text)
        except Exception:
            return None

    def _parse(self, prometheus_text: str) -> VLLMMetrics:
        """Parse Prometheus-format metrics text."""
        metrics = VLLMMetrics()

        patterns = {
            "running_requests": re.compile(r"vllm:num_requests_running\s+(\d+)"),
            "waiting_requests": re.compile(r"vllm:num_requests_waiting\s+(\d+)"),
            "kv_cache_usage": re.compile(r"vllm:gpu_cache_usage_perc\s+([\d.]+)"),
            "preemptions": re.compile(r"vllm:num_requests_preempted_total\s+(\d+)"),
        }

        for attr, pattern in patterns.items():
            match = pattern.search(prometheus_text)
            if match:
                value = match.group(1)
                if attr == "kv_cache_usage":
                    setattr(metrics, attr, float(value))
                else:
                    setattr(metrics, attr, int(value))

        # Token throughput from generated/prompt tokens
        for token_type in ("prompt", "iteration"):
            match = re.search(
                rf"vllm:to_{token_type}_tokens_total\s+([\d.]+)",
                prometheus_text,
            )
            if match:
                value = float(match.group(1))
                if token_type == "prompt":
                    metrics.prompt_tokens_per_sec = value
                else:
                    metrics.generation_tokens_per_sec = value

        self._snapshots.append(metrics)
        return metrics

    def get_summary(self) -> dict[str, object]:
        """Get aggregate metrics summary."""
        if not self._snapshots:
            return {"status": "no_data"}

        def _avg(attr: str) -> float | None:
            values = [getattr(s, attr) for s in self._snapshots if getattr(s, attr) is not None]
            return sum(values) / len(values) if values else None

        return {
            "samples": len(self._snapshots),
            "avg_running_requests": _avg("running_requests"),
            "avg_waiting_requests": _avg("waiting_requests"),
            "avg_kv_cache_usage": _avg("kv_cache_usage"),
            "total_preemptions": max(
                (s.preemptions for s in self._snapshots if s.preemptions is not None),
                default=0,
            ),
        }


@dataclass
class PipelineMetrics:
    """Metrics for HydraCode pipeline runs."""

    run_id: str
    mode: str  # "single" or "multi"
    total_candidates: int = 0
    completed_candidates: int = 0
    failed_candidates: int = 0
    successful_candidates: int = 0  #.score > 0.5 and hard_gate_passed
    total_tests: int = 0
    passed_tests: int = 0
    duration_seconds: float = 0.0
    task_id: str | None = None
    winner: str | None = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_candidates == 0:
            return 0.0
        return self.successful_candidates / self.total_candidates

    @property
    def test_pass_rate(self) -> float:
        """Calculate test pass rate."""
        if self.total_tests == 0:
            return 0.0
        return self.passed_tests / self.total_tests

    def to_dict(self) -> dict[str, object]:
        """Serialize to dictionary."""
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "total_candidates": self.total_candidates,
            "completed_candidates": self.completed_candidates,
            "failed_candidates": self.failed_candidates,
            "successful_candidates": self.successful_candidates,
            "success_rate": self.success_rate,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "test_pass_rate": self.test_pass_rate,
            "duration_seconds": self.duration_seconds,
            "task_id": self.task_id,
            "winner": self.winner,
        }


class MetricsRepository:
    """Persists and queries pipeline metrics across runs."""

    def __init__(self, storage_path: str = ".hydra/metrics.json") -> None:
        self._storage_path = Path(storage_path)
        self._snapshots: list[PipelineMetrics] = []

    def store(self, metrics: PipelineMetrics) -> None:
        """Store a metrics snapshot."""
        self._snapshots.append(metrics)
        self._persist()

    def _persist(self) -> None:
        """Persist all snapshots to disk."""
        import json

        data = [m.to_dict() for m in self._snapshots]
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(json.dumps(data, indent=2))

    def get_comparison(self, mode: str | None = None) -> dict[str, float]:
        """Get aggregated metrics by mode."""
        by_mode: dict[str, list[PipelineMetrics]] = {}
        for m in self._snapshots:
            key = mode or m.mode
            if key not in by_mode:
                by_mode[key] = []
            by_mode[key].append(m)

        result: dict[str, float] = {}
        for m_key, metrics_list in by_mode.items():
            if not metrics_list:
                continue
            avg_success = sum(m.success_rate for m in metrics_list) / len(metrics_list)
            avg_tests = sum(m.total_tests for m in metrics_list) / len(metrics_list)
            result[f"{m_key}_avg_success_rate"] = avg_success
            result[f"{m_key}_avg_tests"] = avg_tests
            result[f"{m_key}_total_runs"] = len(metrics_list)

        return result

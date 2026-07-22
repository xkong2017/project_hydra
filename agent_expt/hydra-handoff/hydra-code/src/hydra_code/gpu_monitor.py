"""GPU-aware concurrency controller via vLLM metrics polling."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_METRICS_URL = "http://127.0.0.1:8000/metrics"
POLL_INTERVAL = 2.0  # seconds


@dataclass
class GpuMetricsSnapshot:
    """A single snapshot of vLLM GPU metrics."""

    kv_cache_usage: float = 0.0
    num_requests_running: int = 0
    num_requests_waiting: int = 0
    num_requests_preempted: int = 0
    prefix_cache_hit_rate: float = 0.0
    spec_decode_acceptance_rate: float = 0.0
    gpu_memory_usage: float = 0.0
    e2e_request_latency_p50: float = 0.0
    e2e_request_latency_p95: float = 0.0


@dataclass
class GpuMonitorConfig:
    """Configuration for the GPU monitor."""

    metrics_url: str = DEFAULT_METRICS_URL
    poll_interval: float = POLL_INTERVAL
    min_concurrency: int = 6
    max_concurrency: int = 32
    # Scale-up thresholds
    scale_up_kv_threshold: float = 0.70
    scale_up_wait_threshold: int = 0
    scale_up_delta: int = 2
    # Scale-down thresholds
    scale_down_kv_threshold: float = 0.85
    scale_down_wait_threshold: int = 5
    scale_down_delta: int = 4
    # EMA smoothing to avoid jitter
    ema_alpha: float = 0.3
    # Health check
    max_consecutive_errors: int = 5


class GpuMonitor:
    """Polls vLLM /metrics and adjusts target concurrency adaptively."""

    def __init__(self, config: GpuMonitorConfig | None = None) -> None:
        self.config = config or GpuMonitorConfig()
        self._target_concurrency: int = self.config.min_concurrency
        self._ema_kv_cache: float = 0.0
        self._is_initialized: bool = False
        self._is_running: bool = False
        self._consecutive_errors: int = 0
        self._latest_snapshot: GpuMetricsSnapshot = GpuMetricsSnapshot()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    @property
    def target_concurrency(self) -> int:
        """Current target concurrency level."""
        return self._target_concurrency

    @property
    def latest_snapshot(self) -> GpuMetricsSnapshot:
        """Most recent metrics snapshot."""
        return self._latest_snapshot

    async def start(self) -> None:
        """Start the background polling loop."""
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.ensure_future(self._poll_loop())
        logger.info(
            "GPU monitor started: min=%d, max=%d, target=%d",
            self.config.min_concurrency,
            self.config.max_concurrency,
            self._target_concurrency,
        )

    async def stop(self) -> None:
        """Stop the background polling loop."""
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("GPU monitor stopped")

    async def get_target_concurrency(self) -> int:
        """Get current target concurrency (thread-safe)."""
        async with self._lock:
            return self._target_concurrency

    async def get_metrics_snapshot(self) -> GpuMetricsSnapshot:
        """Get current metrics snapshot (thread-safe)."""
        async with self._lock:
            return GpuMetricsSnapshot(
                kv_cache_usage=self._latest_snapshot.kv_cache_usage,
                num_requests_running=self._latest_snapshot.num_requests_running,
                num_requests_waiting=self._latest_snapshot.num_requests_waiting,
                num_requests_preempted=self._latest_snapshot.num_requests_preempted,
                prefix_cache_hit_rate=self._latest_snapshot.prefix_cache_hit_rate,
                spec_decode_acceptance_rate=self._latest_snapshot.spec_decode_acceptance_rate,
                gpu_memory_usage=self._latest_snapshot.gpu_memory_usage,
                e2e_request_latency_p50=self._latest_snapshot.e2e_request_latency_p50,
                e2e_request_latency_p95=self._latest_snapshot.e2e_request_latency_p95,
            )

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._is_running:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in GPU monitor poll loop")
                await asyncio.sleep(self.config.poll_interval)

    async def _poll_once(self) -> None:
        """Fetch metrics and adjust concurrency."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self.config.metrics_url, timeout=5.0)
                if resp.status_code != 200:
                    self._consecutive_errors += 1
                    await asyncio.sleep(self.config.poll_interval)
                    return
                text = resp.text
        except Exception:
            self._consecutive_errors += 1
            if self._consecutive_errors >= self.config.max_consecutive_errors:
                logger.warning(
                    "GPU monitor: %d consecutive errors, metrics unavailable",
                    self._consecutive_errors,
                )
            await asyncio.sleep(self.config.poll_interval)
            return

        self._consecutive_errors = 0
        snapshot = self._parse_metrics(text)

        async with self._lock:
            self._latest_snapshot = snapshot
            self._adjust_concurrency(snapshot)

        await asyncio.sleep(self.config.poll_interval)

    def _parse_metrics(self, text: str) -> GpuMetricsSnapshot:
        """Parse Prometheus-format metrics from vLLM."""
        snapshot = GpuMetricsSnapshot()

        # Parse gauge metrics
        gauges = self._extract_gauges(text)

        # KV cache usage
        if "vllm:kv_cache_usage_perc" in gauges:
            snapshot.kv_cache_usage = gauges["vllm:kv_cache_usage_perc"]
        elif "vllm:gpu_cache_usage_perc" in gauges:
            snapshot.kv_cache_usage = gauges["vllm:gpu_cache_usage_perc"]

        # Request counts
        if "vllm:num_requests_running" in gauges:
            snapshot.num_requests_running = int(gauges["vllm:num_requests_running"])
        if "vllm:num_requests_waiting" in gauges:
            snapshot.num_requests_waiting = int(gauges["vllm:num_requests_waiting"])

        # Preemption
        if "vllm:num_requests_preempted_total" in gauges:
            snapshot.num_requests_preempted = int(gauges["vllm:num_requests_preempted_total"])

        # Prefix cache hit rate
        hit_rate = self._compute_ratio(
            gauges, "vllm:prefix_cache_hits_total", "vllm:prefix_cache_queries_total"
        )
        if hit_rate is not None:
            snapshot.prefix_cache_hit_rate = hit_rate

        # Speculative decoding acceptance
        if "vllm:spec_decode_draft_acceptance_rate" in gauges:
            snapshot.spec_decode_acceptance_rate = gauges[
                "vllm:spec_decode_draft_acceptance_rate"
            ]

        # GPU memory usage
        if "vllm:gpu_memory_usage_perc" in gauges:
            snapshot.gpu_memory_usage = gauges["vllm:gpu_memory_usage_perc"]

        # E2E latency percentiles (harder to parse from raw Prometheus, approximate)
        if "vllm:e2e_request_latency_seconds_sum" in gauges and "vllm:e2e_request_latency_seconds_count" in gauges:
            e2e_sum = gauges["vllm:e2e_request_latency_seconds_sum"]
            e2e_count = gauges["vllm:e2e_request_latency_seconds_count"]
            if e2e_count > 0:
                snapshot.e2e_request_latency_p50 = e2e_sum / e2e_count

        return snapshot

    @staticmethod
    def _extract_gauges(text: str) -> dict[str, float]:
        """Extract gauge values from Prometheus text format."""
        gauges: dict[str, float] = {}
        for line in text.split("\n"):
            # Skip comments
            if line.startswith("#"):
                continue
            parts = line.strip().split()
            if len(parts) >= 2:
                try:
                    name = parts[0]
                    value = float(parts[1])
                    gauges[name] = value
                except ValueError:
                    continue
        return gauges

    @staticmethod
    def _compute_ratio(
        gauges: dict[str, float], numerator: str, denominator: str
    ) -> float | None:
        """Compute a ratio from two gauge values."""
        if numerator in gauges and denominator in gauges and gauges[denominator] > 0:
            return gauges[numerator] / gauges[denominator]
        return None

    def _adjust_concurrency(self, snapshot: GpuMetricsSnapshot) -> None:
        """Adjust target concurrency based on GPU metrics.

        Algorithm:
        - Scale UP when GPU has headroom (KV cache < 70% and no queued requests)
        - Scale DOWN when GPU is overloaded (KV cache > 85% or many queued requests)
        - Use EMA-smoothed KV cache to avoid jitter
        """
        # Update EMA with latest snapshot
        if not self._is_initialized:
            self._ema_kv_cache = snapshot.kv_cache_usage
            self._is_initialized = True
        else:
            self._ema_kv_cache = (
                self.config.ema_alpha * snapshot.kv_cache_usage
                + (1 - self.config.ema_alpha) * self._ema_kv_cache
            )

        kv = self._ema_kv_cache
        waiting = snapshot.num_requests_waiting

        should_scale_up = (
            kv < self.config.scale_up_kv_threshold
            and waiting <= self.config.scale_up_wait_threshold
        )
        should_scale_down = (
            kv > self.config.scale_down_kv_threshold
            or waiting > self.config.scale_down_wait_threshold
        )

        if should_scale_up and not should_scale_down:
            self._target_concurrency = min(
                self._target_concurrency + self.config.scale_up_delta,
                self.config.max_concurrency,
            )
        elif should_scale_down:
            self._target_concurrency = max(
                self._target_concurrency - self.config.scale_down_delta,
                self.config.min_concurrency,
            )

        # Clamp to bounds
        self._target_concurrency = max(
            self.config.min_concurrency,
            min(self._target_concurrency, self.config.max_concurrency),
        )

    def get_diagnostics(self) -> dict[str, Any]:
        """Get diagnostics for logging/debugging."""
        return {
            "target_concurrency": self._target_concurrency,
            "ema_kv_cache": self._ema_kv_cache,
            "is_initialized": self._is_initialized,
            "is_running": self._is_running,
            "consecutive_errors": self._consecutive_errors,
            "min_concurrency": self.config.min_concurrency,
            "max_concurrency": self.config.max_concurrency,
        }

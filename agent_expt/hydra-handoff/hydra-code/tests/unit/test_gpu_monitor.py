"""Unit tests for GPU monitor concurrency controller."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hydra_code.gpu_monitor import (
    GpuMetricsSnapshot,
    GpuMonitor,
    GpuMonitorConfig,
)


class TestExtractGauges:
    """Test Prometheus metric parsing."""

    def test_basic_gauge(self) -> None:
        text = "# HELP test\nvllm:kv_cache_usage_perc 0.75\n"
        gauges = GpuMonitor._extract_gauges(text)
        assert gauges["vllm:kv_cache_usage_perc"] == 0.75

    def test_multiple_gauges(self) -> None:
        text = (
            "vllm:kv_cache_usage_perc 0.85\n"
            "vllm:num_requests_running 16\n"
            "vllm:num_requests_waiting 3\n"
        )
        gauges = GpuMonitor._extract_gauges(text)
        assert gauges["vllm:kv_cache_usage_perc"] == 0.85
        assert gauges["vllm:num_requests_running"] == 16
        assert gauges["vllm:num_requests_waiting"] == 3

    def test_skips_comments(self) -> None:
        text = "# HELP vllm:kv_cache_usage_perc\n# TYPE gauge\n"
        gauges = GpuMonitor._extract_gauges(text)
        assert len(gauges) == 0

    def test_ignores_invalid_lines(self) -> None:
        text = "invalid line here\nvllm:kv_cache_usage_perc 0.5\n"
        gauges = GpuMonitor._extract_gauges(text)
        assert len(gauges) == 1


class TestParseMetrics:
    """Test vLLM metrics snapshot parsing."""

    def test_full_metrics(self) -> None:
        monitor = GpuMonitor(GpuMonitorConfig())
        text = (
            "vllm:kv_cache_usage_perc 0.78\n"
            "vllm:num_requests_running 12\n"
            "vllm:num_requests_waiting 5\n"
            "vllm:gpu_memory_usage_perc 0.82\n"
        )
        snapshot = monitor._parse_metrics(text)
        assert snapshot.kv_cache_usage == 0.78
        assert snapshot.num_requests_running == 12
        assert snapshot.num_requests_waiting == 5
        assert snapshot.gpu_memory_usage == 0.82

    def test_legacy_gpu_cache_metric(self) -> None:
        monitor = GpuMonitor(GpuMonitorConfig())
        text = "vllm:gpu_cache_usage_perc 0.65\n"
        snapshot = monitor._parse_metrics(text)
        assert snapshot.kv_cache_usage == 0.65

    def test_empty_metrics(self) -> None:
        monitor = GpuMonitor(GpuMonitorConfig())
        snapshot = monitor._parse_metrics("# empty\n")
        assert snapshot.kv_cache_usage == 0.0
        assert snapshot.num_requests_running == 0


class TestAdjustConcurrency:
    """Test the adaptive concurrency algorithm."""

    def test_scale_up_on_headroom(self) -> None:
        config = GpuMonitorConfig(min_concurrency=6, max_concurrency=32)
        monitor = GpuMonitor(config)
        monitor._ema_kv_cache = 0.3
        monitor._is_initialized = True

        snapshot = GpuMetricsSnapshot(kv_cache_usage=0.3, num_requests_waiting=0)
        monitor._adjust_concurrency(snapshot)
        assert monitor.target_concurrency == 8

    def test_scale_down_on_high_usage(self) -> None:
        config = GpuMonitorConfig(min_concurrency=6, max_concurrency=32)
        monitor = GpuMonitor(config)
        monitor._target_concurrency = 20
        monitor._ema_kv_cache = 0.9
        monitor._is_initialized = True

        snapshot = GpuMetricsSnapshot(kv_cache_usage=0.9, num_requests_waiting=10)
        monitor._adjust_concurrency(snapshot)
        assert monitor.target_concurrency == 16

    def test_scale_down_on_waiting(self) -> None:
        config = GpuMonitorConfig(min_concurrency=6, max_concurrency=32)
        monitor = GpuMonitor(config)
        monitor._target_concurrency = 20
        monitor._ema_kv_cache = 0.5
        monitor._is_initialized = True

        snapshot = GpuMetricsSnapshot(kv_cache_usage=0.5, num_requests_waiting=10)
        monitor._adjust_concurrency(snapshot)
        assert monitor.target_concurrency == 16

    def test_clamp_to_min(self) -> None:
        config = GpuMonitorConfig(min_concurrency=6, max_concurrency=32)
        monitor = GpuMonitor(config)
        monitor._target_concurrency = 7
        monitor._ema_kv_cache = 0.95
        monitor._is_initialized = True

        snapshot = GpuMetricsSnapshot(kv_cache_usage=0.95, num_requests_waiting=20)
        monitor._adjust_concurrency(snapshot)
        assert monitor.target_concurrency == 6

    def test_clamp_to_max(self) -> None:
        config = GpuMonitorConfig(min_concurrency=6, max_concurrency=32)
        monitor = GpuMonitor(config)
        monitor._target_concurrency = 31
        monitor._ema_kv_cache = 0.1
        monitor._is_initialized = True

        snapshot = GpuMetricsSnapshot(kv_cache_usage=0.1, num_requests_waiting=0)
        monitor._adjust_concurrency(snapshot)
        assert monitor.target_concurrency == 32

    def test_ema_smoothing(self) -> None:
        config = GpuMonitorConfig(ema_alpha=0.3)
        monitor = GpuMonitor(config)
        monitor._ema_kv_cache = 0.5
        monitor._is_initialized = True

        snapshot = GpuMetricsSnapshot(kv_cache_usage=0.9, num_requests_waiting=0)
        monitor._adjust_concurrency(snapshot)
        assert abs(monitor._ema_kv_cache - 0.62) < 0.01


class TestGpuMonitorDiagnostics:
    """Test GPU monitor diagnostics."""

    def test_initial_diagnostics(self) -> None:
        config = GpuMonitorConfig(min_concurrency=6, max_concurrency=32)
        monitor = GpuMonitor(config)
        diag = monitor.get_diagnostics()
        assert diag["target_concurrency"] == 6
        assert diag["min_concurrency"] == 6
        assert diag["max_concurrency"] == 32
        assert not diag["is_initialized"]


class TestComputeRatio:
    """Test ratio computation for cache hit rates."""

    def test_basic_ratio(self) -> None:
        gauges = {"num": 75.0, "denom": 100.0}
        ratio = GpuMonitor._compute_ratio(gauges, "num", "denom")
        assert ratio == 0.75

    def test_division_by_zero(self) -> None:
        gauges = {"num": 75.0, "denom": 0.0}
        ratio = GpuMonitor._compute_ratio(gauges, "num", "denom")
        assert ratio is None

    def test_missing_keys(self) -> None:
        gauges = {"other": 1.0}
        ratio = GpuMonitor._compute_ratio(gauges, "num", "denom")
        assert ratio is None

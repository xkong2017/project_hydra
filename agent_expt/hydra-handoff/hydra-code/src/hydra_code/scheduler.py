"""Async scheduler with semaphore-based concurrency control and dynamic capacity."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class JobPriority(StrEnum):
    """Job priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


@dataclass(order=True)
class ScheduledJob:
    """A job waiting in the scheduler queue."""

    priority: JobPriority = field(compare=False)
    job_id: str = field(compare=False)
    coroutine: Coroutine[Any, Any, Any] = field(compare=False, repr=False)
    _priority_order: int = field(init=False, compare=True, default=1)

    def __post_init__(self) -> None:
        priority_map = {JobPriority.HIGH: 0, JobPriority.NORMAL: 1, JobPriority.LOW: 2}
        self._priority_order = priority_map.get(self.priority, 1)


class BoundedSemaphore:
    """Semaphore with dynamic resize capability for GPU-aware scaling."""

    def __init__(self, value: int = 6) -> None:
        self._value = value
        self._lock = asyncio.Lock()
        self._waiters: list[asyncio.Future[None]] = []

    @property
    def value(self) -> int:
        return self._value

    def resize(self, new_value: int) -> None:
        """Change the semaphore capacity, waking waiters if increased."""
        if new_value > self._value:
            diff = new_value - self._value
            for _ in range(diff):
                if self._waiters:
                    waiter = self._waiters.pop(0)
                    if not waiter.done():
                        waiter.set_result(None)
        self._value = new_value

    async def acquire(self) -> None:
        async with self._lock:
            if self._value > 0:
                self._value -= 1
                return
            waiter = asyncio.get_event_loop().create_future()
            self._waiters.append(waiter)
        try:
            await waiter
        except asyncio.CancelledError:
            # Clean up from waiters if cancelled
            async with self._lock:
                if waiter in self._waiters:
                    self._waiters.remove(waiter)
            raise

    def release(self) -> None:
        if self._waiters:
            waiter = self._waiters.pop(0)
            if not waiter.done():
                waiter.set_result(None)
        else:
            self._value += 1


class Scheduler:
    """Asyncio-based scheduler with configurable concurrency and dynamic capacity.

    Supports optional dynamic capacity via an async callable that returns
    the current concurrency limit (e.g., from a GPU monitor).
    """

    def __init__(
        self,
        max_concurrent: int = 6,
        dynamic_capacity: Callable[[], Awaitable[int]] | None = None,
    ) -> None:
        self.max_concurrent = max_concurrent
        self._dynamic_capacity = dynamic_capacity
        self._semaphore = BoundedSemaphore(max_concurrent)
        self._active_count = 0
        self._completed: list[str] = []
        self._results: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        """Number of currently running jobs."""
        return self._active_count

    @property
    def completed_count(self) -> int:
        """Number of completed jobs."""
        return len(self._completed)

    async def update_capacity(self, capacity: int) -> None:
        """Update concurrency limit from dynamic capacity source."""
        self._semaphore.resize(capacity)

    def submit(
        self,
        job_id: str,
        coro: Coroutine[Any, Any, Any],
        priority: JobPriority = JobPriority.NORMAL,
    ) -> asyncio.Future[Any]:
        """Submit a job to the scheduler and return a future for the result."""
        job = ScheduledJob(job_id=job_id, coroutine=coro, priority=priority)
        return asyncio.ensure_future(self._run_job(job))

    async def _run_job(self, job: ScheduledJob) -> Any:
        """Execute a job with semaphore control."""
        await self._semaphore.acquire()
        async with self._lock:
            self._active_count += 1
        try:
            result = await job.coroutine
            self._results[job.job_id] = result
            return result
        finally:
            async with self._lock:
                self._active_count -= 1
                self._completed.append(job.job_id)
            self._semaphore.release()

    async def submit_batch(
        self,
        jobs: list[tuple[str, Coroutine[Any, Any, Any], JobPriority]],
    ) -> dict[str, Any]:
        """Submit multiple jobs and wait for all to complete."""
        futures: list[asyncio.Future[Any]] = []
        for job_id, coro, priority in jobs:
            fut = self.submit(job_id, coro, priority)
            futures.append(fut)

        results = await asyncio.gather(*futures, return_exceptions=True)
        return {
            jobs[i][0]: result for i, result in enumerate(results)
        }

    async def wait_all(self, timeout: float | None = None) -> dict[str, Any]:
        """Wait for all submitted jobs to complete."""
        while self._active_count > 0:
            if timeout is not None:
                await asyncio.sleep(min(0.1, timeout))
                timeout -= 0.1
                if timeout <= 0:
                    break
            else:
                await asyncio.sleep(0.1)
        return dict(self._results)

    def get_stats(self) -> dict[str, int]:
        """Get scheduler statistics."""
        return {
            "max_concurrent": self.max_concurrent,
            "active": self._active_count,
            "completed": len(self._completed),
        }

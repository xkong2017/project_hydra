"""Signal handling for graceful shutdown."""

from __future__ import annotations

import asyncio
import signal
import sys
from collections.abc import Callable
from types import FrameType
from typing import Any


class SignalHandler:
    """Handles SIGINT/SIGTERM for graceful shutdown."""

    def __init__(self, on_shutdown: Callable[[], None] | None = None) -> None:
        self._received_signal: int | None = None
        self._old_sigint: Callable[[int, FrameType | None], Any] | int | None = None
        self._old_sigterm: Callable[[int, FrameType | None], Any] | int | None = None
        self._on_shutdown = on_shutdown
        self._children: list[int] = []
        self._async_tasks: list[asyncio.Task[None]] = []

    @property
    def should_stop(self) -> bool:
        """Return True if a shutdown signal was received."""
        return self._received_signal is not None

    @property
    def received_signal(self) -> int | None:
        """The signal that triggered shutdown."""
        return self._received_signal

    def _handle_signal(self, sig: int, frame: FrameType | None) -> None:
        """Signal callback — set flag, defer cleanup to main loop."""
        self._received_signal = sig

    def install(self) -> None:
        """Install signal handlers."""
        self._old_sigint = signal.getsignal(signal.SIGINT)
        self._old_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def uninstall(self) -> None:
        """Restore previous signal handlers."""
        if self._old_sigint is not None:
            signal.signal(signal.SIGINT, self._old_sigint)
        if self._old_sigterm is not None:
            signal.signal(signal.SIGTERM, self._old_sigterm)

    def register_child(self, pid: int) -> None:
        """Track a child process for cleanup."""
        self._children.append(pid)

    def register_async_task(self, task: asyncio.Task[None]) -> None:
        """Track an async task for cleanup on shutdown."""
        self._async_tasks.append(task)

    def shutdown(self) -> None:
        """Run shutdown cleanup."""
        if self._on_shutdown:
            self._on_shutdown()

    async def async_shutdown(self) -> None:
        """Cancel all tracked async tasks and wait for them."""
        for task in self._async_tasks:
            if not task.done():
                task.cancel()
        results = await asyncio.gather(*self._async_tasks, return_exceptions=True)
        # Suppress CancelledError noise
        for result in results:
            if isinstance(result, asyncio.CancelledError):
                pass

    def print_message(self) -> None:
        """Print shutdown message."""
        if self._received_signal:
            sig_name = signal.Signals(self._received_signal).name
            print(f"\nReceived {sig_name}, shutting down gracefully...")
            sys.stdout.flush()

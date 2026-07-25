"""Connection pool manager.

BUGGY: _active_connections is a class variable shared across all instances.
Two different pool instances with max_size=5 will share one pool,
so one pool can fill up the other's slots.
FIX: Move _active_connections to __init__ (instance variable).
"""

from __future__ import annotations


class ConnectionPool:
    """Manages a pool of database connections."""

    _active_connections: list[str] = []  # BUG: class-level, not instance-level

    def __init__(self, name: str, max_size: int = 5):
        self.name = name
        self.max_size = max_size

    def acquire(self, conn_id: str) -> str | None:
        """Acquire a connection. Returns None if pool is full."""
        if len(self._active_connections) >= self.max_size:
            return None
        self._active_connections.append(conn_id)
        return conn_id

    def release(self, conn_id: str) -> bool:
        """Release a connection. Returns True if found."""
        if conn_id in self._active_connections:
            self._active_connections.remove(conn_id)
            return True
        return False

    @property
    def active_count(self) -> int:
        return len(self._active_connections)

    @property
    def available(self) -> int:
        return self.max_size - len(self._active_connections)

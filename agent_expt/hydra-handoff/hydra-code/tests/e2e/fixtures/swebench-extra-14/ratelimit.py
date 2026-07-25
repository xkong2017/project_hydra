import time

class RateLimiter:
    def __init__(self, max_calls=5, window_sec=60):
        self.max_calls = max_calls
        self.window_sec = window_sec
        self._call_count = 0

    def allow(self):
        self._call_count += 1
        return self._call_count <= self.max_calls

    def remaining(self):
        return max(0, self.max_calls - self._call_count)

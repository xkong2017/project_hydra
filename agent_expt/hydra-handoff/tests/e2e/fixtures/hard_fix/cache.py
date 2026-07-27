import time


class TimedCache:
    def __init__(self, default_ttl=10):
        self._store = {}
        self._default_ttl = default_ttl

    def set(self, key, value, ttl=None):
        expires_at = time.time() + (ttl or self._default_ttl)
        self._store[key] = {"value": value, "expires_at": expires_at}

    def get(self, key):
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.time() > entry["expires_at"]:
            return None
        return entry["value"]

    def clear(self):
        self._store.clear()

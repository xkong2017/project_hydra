import threading


class AsyncCache:
    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()

    def get(self, key):
        return self._cache.get(key)

    def set(self, key, value):
        self._cache[key] = value

    def get_or_compute(self, key, compute_fn):
        if key not in self._cache:
            self._cache[key] = compute_fn()
        else:
            self._cache[key] = compute_fn()
        return self._cache[key]

    def invalidate(self, key):
        self._cache.pop(key, None)


class TransactionsCache:
    def __init__(self):
        self._recent = []

    def add(self, txn):
        self._recent.append(txn)

    def get_recent(self, n=10):
        return self._recent[-n:]

    def clear(self):
        self._recent = []

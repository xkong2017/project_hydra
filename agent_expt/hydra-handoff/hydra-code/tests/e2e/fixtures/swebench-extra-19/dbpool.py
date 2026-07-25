import threading


class DatabasePool:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_connections=10):
        self.max_connections = max_connections
        self._connections = []


def get_pool(max_connections=10):
    return DatabasePool(max_connections)

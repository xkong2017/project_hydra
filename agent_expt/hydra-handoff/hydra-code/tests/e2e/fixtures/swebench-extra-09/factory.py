class Connection:
    def __init__(self, host, port):
        self.host = host
        self.port = port

    def __repr__(self):
        return f"Connection({self.host}:{self.port})"


_default_connection = None


def get_connection(host="localhost", port=5432):
    global _default_connection
    if _default_connection is None:
        _default_connection = Connection(host, port)
    return _default_connection


def reset_connection():
    global _default_connection
    _default_connection = None

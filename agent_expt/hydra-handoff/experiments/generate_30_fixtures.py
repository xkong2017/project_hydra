#!/usr/bin/env python3
"""Generate 30 additional buggy fixtures (A1-G5) covering new bug patterns."""

from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures"

# I'll write fixtures in batches via bash heredocs for reliability
# This script writes a manifest file, then bash creates the fixtures
manifest = []

fixtures = {}

# === A1: String slicing off-by-one ===
fixtures["swebench-extra-01"] = {
    "README.md": "# A1: String slicing off-by-one\n\n**Bug**: substring() uses wrong end index.\n",
    "text_util.py": """\
def substring(text, start, length):
    if start < 0 or length < 0:
        return ""
    return text[start:start + length]


def truncate(text, max_len):
    if len(text) <= max_len:
        return text
    return substring(text, 0, max_len)


def highlight(text, start, length):
    part = substring(text, start, length)
    return f"[{part}]"


def find_and_extract(text, pattern, context=5):
    idx = text.find(pattern)
    if idx == -1:
        return None
    return substring(text, max(0, idx - context), len(pattern) + 2 * context)
""",
    "test_text_util.py": """\
from text_util import substring, truncate, highlight


def test_substring_normal():
    assert substring("hello", 0, 3) == "hel"


def test_substring_full():
    assert substring("hello", 0, 5) == "hello"


def test_substring_middle():
    assert substring("hello world", 6, 5) == "world"


def test_substring_negative_start():
    assert substring("hello", -1, 3) == ""


def test_truncate():
    assert truncate("hello world", 5) == "hello"


def test_truncate_shorter():
    assert truncate("hi", 5) == "hi"


def test_highlight():
    assert highlight("hello world", 0, 5) == "[hello]"
""",
}

# === A2: List flatten skips level ===
fixtures["swebench-extra-02"] = {
    "README.md": "# A2: List flatten recursion bug\n\n**Bug**: flatten() only goes one level deep.\n",
    "flatten.py": """\
def flatten(items):
    result = []
    for item in items:
        if isinstance(item, list):
            result.extend(item)
        else:
            result.append(item)
    return result


def flatten_unique(items):
    return list(set(flatten(items)))


def flatten_to_dict(items):
    flat = flatten(items)
    return {str(i): v for i, v in enumerate(flat)}
""",
    "test_flatten.py": """\
from flatten import flatten, flatten_unique


def test_flat_list():
    assert flatten([1, 2, 3]) == [1, 2, 3]


def test_one_level():
    assert flatten([1, [2, 3], 4]) == [1, 2, 3, 4]


def test_two_levels():
    assert flatten([1, [2, [3, 4]], 5]) == [1, 2, 3, 4, 5]


def test_empty():
    assert flatten([]) == []


def test_nested_empty():
    assert flatten([[], [[]]]) == []


def test_flatten_unique():
    result = flatten_unique([[1, 2], [2, 3]])
    assert set(result) == {1, 2, 3}
""",
}

# === A3: Dict merge doesn't handle lists ===
fixtures["swebench-extra-03"] = {
    "README.md": "# A3: Dict merge overwrites list values\n\n**Bug**: deep_merge() overwrites lists instead of concatenating.\n",
    "merger.py": """\
def deep_merge(base, overlay):
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def merge_configs(defaults, user_config):
    return deep_merge(defaults, user_config)


def merge_schemas(schema_a, schema_b):
    return deep_merge(schema_a, schema_b)
""",
    "test_merger.py": """\
from merger import deep_merge, merge_configs


def test_simple_merge():
    result = deep_merge({"a": 1}, {"b": 2})
    assert result == {"a": 1, "b": 2}


def test_nested_merge():
    result = deep_merge({"db": {"host": "a"}}, {"db": {"port": 5432}})
    assert result == {"db": {"host": "a", "port": 5432}}


def test_list_concat():
    result = deep_merge({"tags": [1, 2]}, {"tags": [3, 4]})
    assert result == {"tags": [1, 2, 3, 4]}, f"Got {result}"


def test_list_single():
    result = deep_merge({"items": [1]}, {"items": [2]})
    assert result == {"items": [1, 2]}


def test_config_merge():
    defaults = {"plugins": ["a"], "debug": False}
    user = {"plugins": ["b"], "debug": True}
    result = merge_configs(defaults, user)
    assert result["plugins"] == ["a", "b"]
    assert result["debug"] is True
""",
}

# === A4: CSV parser handles quoted commas ===
fixtures["swebench-extra-04"] = {
    "README.md": "# A4: CSV parser mishandles quoted commas\n\n**Bug**: parse_csv_line() splits on commas inside quotes.\n",
    "csv_util.py": """\
def parse_csv_line(line):
    return line.strip().split(",")


def parse_csv(text):
    lines = text.strip().split("\\n")
    return [parse_csv_line(line) for line in lines]


def to_csv_row(values):
    escaped = []
    for v in values:
        s = str(v)
        if "," in s or '"' in s:
            s = '"' + s.replace('"', '""') + '"'
        escaped.append(s)
    return ",".join(escaped)
""",
    "test_csv_util.py": """\
from csv_util import parse_csv_line, parse_csv, to_csv_row


def test_simple():
    assert parse_csv_line("a,b,c") == ["a", "b", "c"]


def test_quoted():
    assert parse_csv_line('a,"b,c",d') == ["a", "b,c", "d"]


def test_quoted_with_escaped_quote():
    assert parse_csv_line('a,"b""c",d') == ["a", 'b"c', "d"]


def test_empty_field():
    assert parse_csv_line("a,,c") == ["a", "", "c"]


def test_roundtrip():
    original = ["hello", "world"]
    assert parse_csv_line(to_csv_row(original)) == original


def test_roundtrip_with_comma():
    original = ["a", "b,c", "d"]
    assert parse_csv_line(to_csv_row(original)) == original
""",
}

# === B1: Boolean short-circuit skips side effect ===
fixtures["swebench-extra-05"] = {
    "README.md": "# B1: Boolean short-circuit skips side effect\n\n**Bug**: validate_and_log() short-circuits on first failure, skipping logging.\n",
    "validator.py": """\
def check_positive(n):
    return n > 0


def check_even(n):
    return n % 2 == 0


def validate_all(n, checks):
    ok = True
    for check in checks:
        ok = ok and check(n)
    return ok


def validate_and_log(n, checks, log_func):
    for check in checks:
        if not check(n):
            log_func(f"Failed: {check.__name__}({n})")
            return False
    return True
""",
    "test_validator.py": """\
from validator import validate_all, validate_and_log, check_positive, check_even


def test_all_pass():
    assert validate_all(4, [check_positive, check_even])


def test_first_fails_short_circuit():
    log_entries = []
    def log(msg):
        log_entries.append(msg)
    result = validate_and_log(-2, [check_positive, check_even], log)
    assert result is False
    assert len(log_entries) == 1, f"Expected 1 log, got {len(log_entries)}: {log_entries}"
""",
}

# === B3: Loop missing break on found ===
fixtures["swebench-extra-06"] = {
    "README.md": "# B3: find_first() doesn't stop after finding match\n\n**Bug**: Loop continues after finding target.\n",
    "search.py": """\
def find_first(items, predicate):
    for item in items:
        if predicate(item):
            return item
    return None


def find_all(items, predicate):
    return [item for item in items if predicate(item)]


def find_last(items, predicate):
    result = None
    for item in items:
        if predicate(item):
            result = item
    return result


def count_until(items, predicate, limit):
    count = 0
    for item in items:
        if predicate(item):
            count += 1
            if count >= limit:
                return count
    return count
""",
    "test_search.py": """\
from search import find_first, find_all, find_last, count_until


def test_find_first():
    items = [1, 2, 3, 4, 5]
    result = find_first(items, lambda x: x > 3)
    assert result == 4


def test_find_first_none():
    assert find_first([1, 2], lambda x: x > 10) is None


def test_find_all():
    assert find_all([1, 2, 3, 4], lambda x: x % 2 == 0) == [2, 4]


def test_count_until():
    result = count_until([1, 2, 3, 4, 5], lambda x: x > 2, 2)
    assert result == 2
""",
}

# === B4: Filter missing continue ===
fixtures["swebench-extra-07"] = {
    "README.md": "# B4: Filter function missing continue on condition\n\n**Bug**: process_items() doesn't skip None items.\n",
    "pipeline.py": """\
def process_items(items):
    result = []
    for item in items:
        if item is None:
            continue
        result.append(item * 2)
    return result


def filter_and_process(items):
    result = []
    for item in items:
        if item is not None:
            result.append(process_items([item])[0])
    return result


def process_with_skip(items, skip_value):
    result = []
    for item in items:
        if item == skip_value:
            continue
        result.append(item)
    return result
""",
    "test_pipeline.py": """\
from pipeline import process_items, process_with_skip


def test_process_items():
    assert process_items([1, 2, 3]) == [2, 4, 6]


def test_skip_none():
    result = process_items([1, None, 2, None, 3])
    assert result == [2, 4, 6], f"Got {result}"


def test_skip_value():
    result = process_with_skip([1, 2, 3, 2, 4], 2)
    assert result == [1, 3, 4]


def test_all_skip():
    assert process_with_skip([1, 1, 1], 1) == []
""",
}

# === C1: Property setter missing validation ===
fixtures["swebench-extra-08"] = {
    "README.md": "# C1: Property setter doesn't validate\n\n**Bug**: setter allows negative values.\n",
    "account.py": """\
class BankAccount:
    def __init__(self, balance=0):
        self._balance = balance

    @property
    def balance(self):
        return self._balance

    @balance.setter
    def balance(self, value):
        self._balance = value

    def deposit(self, amount):
        if amount <= 0:
            raise ValueError("Amount must be positive")
        self._balance += amount

    def withdraw(self, amount):
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if amount > self._balance:
            raise ValueError("Insufficient funds")
        self._balance -= amount
""",
    "test_account.py": """\
import pytest
from account import BankAccount


def test_deposit():
    acc = BankAccount()
    acc.deposit(100)
    assert acc.balance == 100


def test_withdraw():
    acc = BankAccount(100)
    acc.withdraw(50)
    assert acc.balance == 50


def test_balance_setter_rejects_negative():
    acc = BankAccount(100)
    with pytest.raises(ValueError, match="negative|invalid"):
        acc.balance = -50


def test_balance_setter_allows_zero():
    acc = BankAccount()
    acc.balance = 0
    assert acc.balance == 0
""",
}

# === C3: Factory returns same instance ===
fixtures["swebench-extra-09"] = {
    "README.md": "# C3: Factory returns same instance\n\n**Bug**: Connection factory returns same connection for different configs.\n",
    "factory.py": """\
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
""",
    "test_factory.py": """\
from factory import get_connection, reset_connection


def test_same_config_same_instance():
    reset_connection()
    c1 = get_connection("db1", 5432)
    c2 = get_connection("db1", 5432)
    assert c1 is c2


def test_different_config_different_instance():
    reset_connection()
    c1 = get_connection("db1", 5432)
    c2 = get_connection("db2", 5432)
    assert c1 is not c2, "Different configs should return different instances!"


def test_host_port_preserved():
    reset_connection()
    c = get_connection("myhost", 9999)
    assert c.host == "myhost"
    assert c.port == 9999
""",
}

# === D1: Memory leak (list grows unbounded) ===
fixtures["swebench-extra-10"] = {
    "README.md": "# D1: Memory leak — event history never trimmed\n\n**Bug**: event_history grows unboundedly.\n",
    "events.py": """\
class EventStore:
    def __init__(self, max_events=100):
        self._events = []
        self._max_events = max_events

    def add(self, event):
        self._events.append(event)

    def get_recent(self, count=10):
        return self._events[-count:]

    def count(self):
        return len(self._events)

    def get_by_type(self, event_type):
        return [e for e in self._events if e.get("type") == event_type]


class EventProcessor:
    def __init__(self):
        self._processed = []

    def process(self, event):
        self._processed.append(event)
        if len(self._processed) > 100:
            self._processed.pop(0)
""",
    "test_events.py": """\
from events import EventStore, EventProcessor


def test_add_and_count():
    store = EventStore(max_events=5)
    for i in range(3):
        store.add({"id": i})
    assert store.count() == 3


def test_trim_old_events():
    store = EventStore(max_events=5)
    for i in range(10):
        store.add({"id": i})
    assert store.count() == 5, f"Expected 5 events, got {store.count()}"


def test_get_recent():
    store = EventStore(max_events=20)
    for i in range(10):
        store.add({"id": i, "type": "test"})
    recent = store.get_recent(3)
    assert len(recent) == 3
    assert recent[-1]["id"] == 9


def test_processor_trims():
    proc = EventProcessor()
    for i in range(200):
        proc.process({"id": i})
    assert len(proc._processed) <= 100
""",
}

# === D2: Unnecessary large copy ===
fixtures["swebench-extra-11"] = {
    "README.md": "# D2: Unnecessary copy of large data\n\n**Bug**: process_logs() copies entire list before filtering.\n",
    "logs.py": """\
def process_logs(logs):
    filtered = []
    for log in logs:
        if log["level"] in ("ERROR", "WARNING"):
            filtered.append(log)
    return filtered


def summarize_logs(logs):
    by_level = {}
    for log in logs:
        level = log["level"]
        by_level[level] = by_level.get(level, 0) + 1
    return by_level


def get_errors(logs):
    return [log for log in logs if log["level"] == "ERROR"]


def deduplicate_logs(logs):
    seen = set()
    result = []
    for log in logs:
        msg = log["message"]
        if msg not in seen:
            seen.add(msg)
            result.append(log)
    return result
""",
    "test_logs.py": """\
from logs import process_logs, summarize_logs, get_errors, deduplicate_logs


def test_filter_errors():
    logs = [
        {"level": "INFO", "message": "ok"},
        {"level": "ERROR", "message": "fail"},
        {"level": "WARNING", "message": "warn"},
    ]
    result = process_logs(logs)
    assert len(result) == 2
    assert all(l["level"] in ("ERROR", "WARNING") for l in result)


def test_summarize():
    logs = [{"level": "INFO"}, {"level": "INFO"}, {"level": "ERROR"}]
    s = summarize_logs(logs)
    assert s == {"INFO": 2, "ERROR": 1}
""",
}

# === D3: Slow O(n) instead of O(1) lookup ===
fixtures["swebench-extra-12"] = {
    "README.md": "# D3: Slow linear search instead of dict lookup\n\n**Bug**: find_by_id() uses linear search.\n",
    "registry.py": """\
class Registry:
    def __init__(self):
        self._items = []

    def register(self, item):
        self._items.append(item)

    def find_by_id(self, item_id):
        for item in self._items:
            if item["id"] == item_id:
                return item
        return None

    def find_by_name(self, name):
        return [item for item in self._items if item["name"] == name]

    def all(self):
        return list(self._items)


def batch_register(registry, items):
    for item in items:
        registry.register(item)
    return registry
""",
    "test_registry.py": """\
from registry import Registry, batch_register


def test_register_and_find():
    r = Registry()
    r.register({"id": 1, "name": "alice"})
    r.register({"id": 2, "name": "bob"})
    result = r.find_by_id(2)
    assert result is not None
    assert result["name"] == "bob"


def test_find_nonexistent():
    r = Registry()
    assert r.find_by_id(99) is None


def test_find_by_name():
    r = Registry()
    r.register({"id": 1, "name": "alice"})
    r.register({"id": 2, "name": "alice"})
    result = r.find_by_name("alice")
    assert len(result) == 2


def test_batch_register():
    r = batch_register(Registry(), [
        {"id": 1, "name": "a"},
        {"id": 2, "name": "b"},
    ])
    assert len(r.all()) == 2
""",
}

# === E1: Path traversal bug ===
fixtures["swebench-extra-13"] = {
    "README.md": "# E1: Path traversal — file path not sanitized\n\n**Bug**: read_file() allows path traversal with ../.\n",
    "fileutil.py": """\
import os

BASE_DIR = "/data/files"


def read_file(filename):
    path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read()


def list_files():
    return os.listdir(BASE_DIR)


def file_exists(filename):
    path = os.path.join(BASE_DIR, filename)
    return os.path.exists(path)
""",
    "test_fileutil.py": """\
from fileutil import read_file, file_exists


def test_read_existing():
    result = read_file("test.txt")
    assert result is not None


def test_path_traversal_blocked():
    result = read_file("../../../etc/passwd")
    assert result is None, "Path traversal should be blocked!"


def test_file_exists_normal():
    assert file_exists("test.txt") is True


def test_file_exists_traversal():
    assert file_exists("../../../etc") is False, "Path traversal should not exist in sandbox!"
""",
}

# === E5: Rate limiter resets on every call ===
fixtures["swebench-extra-14"] = {
    "README.md": "# E5: Rate limiter resets window every call\n\n**Bug**: Sliding window resets on each request instead of tracking.\n",
    "ratelimit.py": """\
import time


class RateLimiter:
    def __init__(self, max_calls=5, window_sec=60):
        self.max_calls = max_calls
        self.window_sec = window_sec
        self._calls = []

    def allow(self):
        now = time.time()
        cutoff = now - self.window_sec
        self._calls = [t for t in self._calls if t > cutoff]
        self._calls.append(now)
        return len(self._calls) <= self.max_calls

    def remaining(self):
        now = time.time()
        cutoff = now - self.window_sec
        recent = [t for t in self._calls if t > cutoff]
        return max(0, self.max_calls - len(recent))
""",
    "test_ratelimit.py": """\
import time
from ratelimit import RateLimiter


def test_allow_under_limit():
    limiter = RateLimiter(max_calls=3, window_sec=60)
    for _ in range(3):
        assert limiter.allow() is True


def test_reject_over_limit():
    limiter = RateLimiter(max_calls=3, window_sec=60)
    for _ in range(3):
        limiter.allow()
    assert limiter.allow() is False


def test_remaining():
    limiter = RateLimiter(max_calls=5, window_sec=60)
    assert limiter.remaining() == 5
    limiter.allow()
    assert limiter.remaining() == 4
""",
}

# === F2: Race counter without atomic increment ===
fixtures["swebench-extra-15"] = {
    "README.md": "# F2: Race condition — shared counter without lock\n\n**Bug**: increment() is not thread-safe.\n",
    "counter.py": """\
import threading


class Counter:
    def __init__(self):
        self.value = 0

    def increment(self):
        current = self.value
        self.value = current + 1

    def decrement(self):
        current = self.value
        self.value = current - 1

    def reset(self):
        self.value = 0


def run_threads(counter, num_threads=10, increments_per_thread=100):
    threads = []
    for _ in range(num_threads):
        t = threading.Thread(
            target=lambda: [counter.increment() for _ in range(increments_per_thread)]
        )
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    return counter.value
""",
    "test_counter.py": """\
from counter import Counter, run_threads


def test_single_increment():
    c = Counter()
    c.increment()
    assert c.value == 1


def test_sequential():
    c = Counter()
    for _ in range(100):
        c.increment()
    assert c.value == 100


def test_threaded():
    c = Counter()
    result = run_threads(c, num_threads=10, increments_per_thread=100)
    assert result == 1000, f"Expected 1000, got {result}"


def test_decrement():
    c = Counter()
    c.value = 10
    c.decrement()
    assert c.value == 9
""",
}

# === F3: Singleton not thread-safe ===
fixtures["swebench-extra-16"] = {
    "README.md": "# F3: Singleton not thread-safe\n\n**Bug**: Singleton can create multiple instances under concurrent access.\n",
    "singleton.py": """\
import threading


class ConfigManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config = {}
        return cls._instance

    def get(self, key, default=None):
        return self._config.get(key, default)

    def set(self, key, value):
        self._config[key] = value


def get_instance():
    return ConfigManager()
""",
    "test_singleton.py": """\
from singleton import ConfigManager, get_instance


def test_same_instance():
    a = get_instance()
    b = get_instance()
    assert a is b


def test_config_persists():
    a = get_instance()
    a.set("key", "value")
    b = get_instance()
    assert b.get("key") == "value"
""",
}

# === G1: HTTP GET with body ===
fixtures["swebench-extra-17"] = {
    "README.md": "# G1: GET request with body\n\n**Bug**: Client sends body on GET requests (RFC violation).\n",
    "http_client.py": """\
class Request:
    def __init__(self, method, url, body=None):
        self.method = method.upper()
        self.url = url
        self.body = body


def build_request(method, url, data=None, params=None):
    if params:
        import urllib.parse
        url = url + "?" + urllib.parse.urlencode(params)
    return Request(method, url, body=data)


def send_request(request):
    if request.method == "GET" and request.body is not None:
        raise ValueError("GET request must not have body")
    return f"{request.method} {request.url}"
""",
    "test_http_client.py": """\
import pytest
from http_client import build_request, send_request


def test_get_without_body():
    r = build_request("GET", "http://example.com")
    assert send_request(r) == "GET http://example.com"


def test_get_with_params():
    r = build_request("GET", "http://example.com", params={"q": "test"})
    result = send_request(r)
    assert "q=test" in result


def test_get_with_body_raises():
    r = build_request("GET", "http://example.com", data="payload")
    with pytest.raises(ValueError, match="body"):
        send_request(r)


def test_post_with_body():
    r = build_request("POST", "http://example.com", data="payload")
    assert send_request(r) == "POST http://example.com"
""",
}

# === B5: Early return before cleanup ===
fixtures["swebench-extra-18"] = {
    "README.md": "# B5: Early return skips cleanup\n\n**Bug**: process_file() returns early, leaving file open.\n",
    "file_processor.py": """\
def read_file_safe(path):
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return None


def process_lines(text, predicate):
    result = []
    for i, line in enumerate(text.split("\\n")):
        if predicate(line):
            result.append((i, line))
    return result


def first_matching_line(text, predicate):
    for line in text.split("\\n"):
        if predicate(line):
            return line
    return None
""",
    "test_file_processor.py": """\
from file_processor import process_lines, first_matching_line


def test_process_lines():
    text = "a\\nb\\nc"
    result = process_lines(text, lambda x: x in ("a", "c"))
    assert result == [(0, "a"), (2, "c")]


def test_first_matching():
    text = "x\\ny\\nz"
    result = first_matching_line(text, lambda x: x > "x")
    assert result == "y"


def test_first_matching_none():
    text = "a\\nb"
    assert first_matching_line(text, lambda x: x == "z") is None
""",
}

# === C4: Singleton init race ===
fixtures["swebench-extra-19"] = {
    "README.md": "# C4: Double-checked locking bug in singleton\n\n**Bug**: Singleton __init__ runs multiple times.\n",
    "dbpool.py": """\
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
""",
    "test_dbpool.py": """\
from dbpool import DatabasePool, get_pool


def test_same_instance():
    a = get_pool()
    b = get_pool()
    assert a is b


def test_init_called_once():
    pool = get_pool(max_connections=5)
    assert pool.max_connections == 5
    pool2 = get_pool(max_connections=20)
    assert pool2.max_connections == 5, "Should not re-init with 20!"
""",
}

# === A5: Custom JSON encoder misses None ===
fixtures["swebench-extra-20"] = {
    "README.md": "# A5: JSON encoder skips None values\n\n**Bug**: Custom serializer drops None instead of keeping null.\n",
    "serializer.py": """\
def serialize(obj):
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, (int, float)):
        return str(obj)
    if isinstance(obj, str):
        return '"' + obj.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(obj, (list, tuple)):
        items = ", ".join(serialize(item) for item in obj)
        return "[" + items + "]"
    if isinstance(obj, dict):
        items = ", ".join(
            serialize(k) + ": " + serialize(v) for k, v in obj.items()
        )
        return "{" + items + "}"
    return serialize(str(obj))


def serialize_pretty(obj, indent=0):
    pad = "  " * indent
    if obj is None:
        return "null"
    if isinstance(obj, (int, float, bool)):
        return str(obj).lower()
    if isinstance(obj, str):
        return '"' + obj + '"'
    if isinstance(obj, list):
        if not obj: return "[]"
        items = ",\\n".join(serialize_pretty(item, indent + 1) for item in obj)
        return "[\\n" + items + "\\n" + pad + "]"
    if isinstance(obj, dict):
        if not obj: return "{}"
        items = ",\\n".join(
            pad + "  " + serialize_pretty(k, 0) + ": " + serialize_pretty(v, indent + 1)
            for k, v in obj.items()
        )
        return "{\\n" + items + "\\n" + pad + "}"
    return str(obj)
""",
    "test_serializer.py": """\
from serializer import serialize


def test_null():
    assert serialize(None) == "null"


def test_int():
    assert serialize(42) == "42"


def test_string():
    assert serialize("hello") == '"hello"'


def test_list():
    assert serialize([1, 2, 3]) == "[1, 2, 3]"


def test_dict_with_null():
    result = serialize({"a": None, "b": 1})
    assert '"a": null' in result, f"Missing null in {result}"
    assert '"b": 1' in result


def test_nested():
    result = serialize({"x": {"y": [1, None]}})
    assert "null" in result
""",
}

# === A6: Date format wrong order ===
fixtures["swebench-extra-21"] = {
    "README.md": "# A6: Date format wrong month/day order\n\n**Bug**: Dates formatted as MM/DD instead of DD/MM or ISO.\n",
    "date_util.py": """\
def format_date(year, month, day):
    return f"{year}-{month:02d}-{day:02d}"


def parse_date(text):
    parts = text.split("-")
    return int(parts[0]), int(parts[1]), int(parts[2])


def days_between(d1, d2):
    from datetime import date
    a = date(*d1)
    b = date(*d2)
    return abs((b - a).days)


def is_weekend(year, month, day):
    from datetime import date
    return date(year, month, day).weekday() >= 5
""",
    "test_date_util.py": """\
from date_util import format_date, parse_date, days_between, is_weekend


def test_format():
    assert format_date(2024, 3, 5) == "2024-03-05"


def test_parse():
    assert parse_date("2024-03-05") == (2024, 3, 5)


def test_days_between():
    assert days_between((2024, 1, 1), (2024, 1, 10)) == 9


def test_is_weekend_saturday():
    assert is_weekend(2024, 3, 30) is True  # Saturday


def test_is_weekend_monday():
    assert is_weekend(2024, 4, 1) is False  # Monday
""",
}

# === A7: Inconsistent rounding ===
fixtures["swebench-extra-22"] = {
    "README.md": "# A7: Inconsistent rounding (banker's rounding)\n\n**Bug**: round_half_up uses banker's rounding for .5.\n",
    "math_util.py": """\
def round_half_up(value, decimals=0):
    factor = 10 ** decimals
    return int(value * factor + 0.5) / factor


def round_half_down(value, decimals=0):
    factor = 10 ** decimals
    return int(value * factor) / factor


def round_to_nearest(value, nearest=0.05):
    return round(value / nearest) * nearest


def calculate_tax(amount, rate=0.07):
    return round_half_up(amount * rate, 2)
""",
    "test_math_util.py": """\
from math_util import round_half_up, calculate_tax


def test_round_half_up_basic():
    assert round_half_up(2.5) == 3.0


def test_round_half_up_negative():
    assert round_half_up(-2.5) == -2.0, f"Got {round_half_up(-2.5)}"


def test_round_half_up_two_decimals():
    assert round_half_up(3.141, 2) == 3.14


def test_round_half_up_2dp():
    assert round_half_up(2.675, 2) == 2.68


def test_calculate_tax():
    result = calculate_tax(10.00)
    assert result == 0.70
""",
}

# === B2: Loop off-by-one ===
fixtures["swebench-extra-23"] = {
    "README.md": "# B2: Loop off-by-one in inclusive range\n\n**Bug**: generate_range() includes upper bound incorrectly.\n",
    "range_util.py": """\
def generate_range(start, end):
    result = []
    current = start
    while current < end:
        result.append(current)
        current += 1
    return result


def generate_range_step(start, end, step=1):
    result = []
    current = start
    while current < end:
        result.append(current)
        current += step
    return result


def sum_range(start, end):
    return sum(generate_range(start, end))


def contains_duplicates(items):
    return len(items) != len(set(items))
""",
    "test_range_util.py": """\
from range_util import generate_range, generate_range_step, sum_range


def test_range_1_to_3():
    assert generate_range(1, 3) == [1, 2, 3], f"Got {generate_range(1, 3)}"


def test_range_1_to_1():
    assert generate_range(1, 1) == [1], f"Got {generate_range(1, 1)}"


def test_range_0_to_0():
    assert generate_range(0, 0) == [0]


def test_range_step():
    assert generate_range_step(0, 5, 2) == [0, 2, 4]
""",
}

# === E2: Command injection ===
fixtures["swebench-extra-24"] = {
    "README.md": "# E2: Command injection — shell command not escaped\n\n**Bug**: run_command() uses shell=True without escaping.\n",
    "shell_util.py": """\
import subprocess
import shlex


def run_command(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, shell=True)


def run_ls(path):
    return run_command(["ls", "-la", path])


def run_grep(pattern, filename):
    return run_command(f"grep '{pattern}' {filename}")
""",
    "test_shell_util.py": """\
from shell_util import run_ls


def test_run_ls():
    result = run_ls(".")
    assert result.returncode == 0


def test_run_ls_injection():
    result = run_ls(".; rm -rf /")
    assert result.returncode != 0, "Shell injection should be blocked!"
""",
}

# === D4: Repeated computation ===
fixtures["swebench-extra-25"] = {
    "README.md": "# D4: Repeated computation without caching\n\n**Bug**: fibonacci() recalculates same values.\n",
    "fib.py": """\
def fibonacci(n):
    if n <= 0:
        return 0
    if n == 1:
        return 1
    return fibonacci(n - 1) + fibonacci(n - 2)


def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)


def memoize(func):
    cache = {}
    def wrapper(n):
        if n not in cache:
            cache[n] = func(n)
        return cache[n]
    return wrapper
""",
    "test_fib.py": """\
from fib import fibonacci, factorial, memoize


def test_fib_0():
    assert fibonacci(0) == 0


def test_fib_1():
    assert fibonacci(1) == 1


def test_fib_10():
    assert fibonacci(10) == 55


def test_fib_20():
    # Without memoization, this would be very slow
    # We're testing correctness, not speed here
    result = fibonacci(20)
    assert result == 6765


def test_factorial():
    assert factorial(5) == 120
""",
}

# === E3: SQL injection ===
fixtures["swebench-extra-26"] = {
    "README.md": "# E3: SQL injection via f-string\n\n**Bug**: SQL query built with string formatting.\n",
    "db.py": """\
import sqlite3


def query_users(name):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INT, name TEXT)")
    cursor = conn.execute(f"SELECT * FROM users WHERE name = '{name}'")
    return cursor.fetchall()


def query_users_safe(name):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INT, name TEXT)")
    cursor = conn.execute("SELECT * FROM users WHERE name = ?", (name,))
    return cursor.fetchall()


def insert_user(user_id, name):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INT, name TEXT)")
    conn.execute("INSERT INTO users VALUES (?, ?)", (user_id, name))
    conn.commit()
""",
    "test_db.py": """\
import pytest
from db import insert_user, query_users_safe


def test_insert_and_query():
    insert_user(1, "alice")
    result = query_users_safe("alice")
    assert len(result) > 0


def test_sql_injection_prevented():
    insert_user(1, "alice")
    result = query_users_safe("' OR '1'='1")
    assert len(result) == 0, "SQL injection should not return all rows!"
""",
}

# === C2: Inheritance MRO ===
fixtures["swebench-extra-27"] = {
    "README.md": "# C2: Incorrect MRO in diamond inheritance\n\n**Bug**: Method resolution order skips intermediate parent.\n",
    "shapes.py": """\
class Shape:
    def area(self):
        return 0

    def describe(self):
        return f"Shape at origin"


class ColoredShape(Shape):
    def __init__(self, color):
        self.color = color

    def describe(self):
        return f"Colored {self.color} Shape"


class SizedShape(Shape):
    def __init__(self, size):
        self.size = size

    def describe(self):
        return f"Sized {self.size} Shape"


class ColoredSizedShape(ColoredShape, SizedShape):
    def __init__(self, color, size):
        ColoredShape.__init__(self, color)
        SizedShape.__init__(self, size)
""",
    "test_shapes.py": """\
from shapes import ColoredSizedShape


def test_mro():
    obj = ColoredSizedShape("red", 10)
    assert obj.color == "red"
    assert obj.size == 10


def test_describe_includes_color():
    obj = ColoredSizedShape("blue", 20)
    result = obj.describe()
    assert "blue" in result, f"describe() should mention color: {result}"
    assert "20" in result, f"describe() should mention size: {result}"
""",
}

# === F1: Deadlock lock ordering ===
fixtures["swebench-extra-28"] = {
    "README.md": "# F1: Deadlock from inconsistent lock ordering\n\n**Bug**: Lock acquired in wrong order, causing deadlock.\n",
    "bank.py": """\
import threading


class Account:
    def __init__(self, name, balance=0):
        self.name = name
        self.balance = balance
        self.lock = threading.Lock()

    def transfer(self, target, amount):
        with self.lock:
            with target.lock:
                if self.balance >= amount:
                    self.balance -= amount
                    target.balance += amount
                    return True
                return False

    def get_balance(self):
        return self.balance
""",
    "test_bank.py": """\
from bank import Account


def test_transfer():
    a = Account("A", 100)
    b = Account("B", 0)
    result = a.transfer(b, 50)
    assert result is True
    assert a.get_balance() == 50
    assert b.get_balance() == 50


def test_insufficient():
    a = Account("A", 10)
    b = Account("B", 0)
    result = a.transfer(b, 20)
    assert result is False


def test_deadlock_free():
    a = Account("A", 100)
    b = Account("B", 100)
    import threading
    t1 = threading.Thread(target=a.transfer, args=(b, 50))
    t2 = threading.Thread(target=b.transfer, args=(a, 30))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert t1.is_alive() is False, "Deadlock detected!"
    assert t2.is_alive() is False, "Deadlock detected!"
""",
}

# === F4: Async cache returns stale data ===
fixtures["swebench-extra-29"] = {
    "README.md": "# F4: Async cache race — returns stale data\n\n**Bug**: Cache returns stale value when concurrent writes happen.\n",
    "async_cache.py": """\
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
""",
    "test_async_cache.py": """\
from async_cache import AsyncCache


def test_get_set():
    c = AsyncCache()
    c.set("key", 42)
    assert c.get("key") == 42


def test_get_or_compute():
    c = AsyncCache()
    called = []
    def compute():
        called.append(1)
        return 99
    result = c.get_or_compute("x", compute)
    assert result == 99
    assert len(called) == 1
    result2 = c.get_or_compute("x", compute)
    assert result2 == 99
    assert len(called) == 1, "compute should not be called again"


def test_invalidate():
    c = AsyncCache()
    c.set("k", 1)
    c.invalidate("k")
    assert c.get("k") is None
""",
}

# === G3: Redirect drops auth headers ===
fixtures["swebench-extra-30"] = {
    "README.md": "# G3: Redirect drops auth — security bug\n\n**Bug**: Redirect handler strips Authorization header.\n",
    "redirect.py": """\
class HttpResponse:
    def __init__(self, status, headers, body=""):
        self.status = status
        self.headers = headers
        self.body = body


def handle_redirect(response, auth_header):
    if 300 <= response.status < 400:
        new_headers = dict(response.headers)
        if "Authorization" not in new_headers and "authorization" not in new_headers:
            if auth_header is not None:
                new_headers["Authorization"] = auth_header
        return HttpResponse(response.status, new_headers, response.body)
    return response


def follow_redirects(client, url, auth_header, max_redirects=5):
    for _ in range(max_redirects):
        response = client.get(url, headers={"Authorization": auth_header})
        if 300 <= response.status < 400:
            url = response.headers.get("Location")
            if not url:
                return response
        else:
            return response
    return response
""",
    "test_redirect.py": """\
from redirect import handle_redirect, HttpResponse


def test_no_redirect():
    response = HttpResponse(200, {"Content-Type": "text/html"})
    result = handle_redirect(response, "Bearer token123")
    assert result.status == 200


def test_redirect_preserves_auth():
    response = HttpResponse(302, {"Location": "/new-path"})
    result = handle_redirect(response, "Bearer mytoken")
    assert result.headers.get("Authorization") == "Bearer mytoken", \
        "Auth header should be preserved on redirect!"


def test_redirect_without_auth():
    response = HttpResponse(302, {"Location": "/new-path"})
    result = handle_redirect(response, None)
    assert "Authorization" not in result.headers
""",
}


def main():
    for dirname, files in fixtures.items():
        d = BASE / dirname
        d.mkdir(parents=True, exist_ok=True)
        for fname, content in files.items():
            (d / fname).write_text(content.lstrip("\n"))
        print(f"  Created {dirname} ({len(files)} files)")

    print(f"\nTotal: {len(fixtures)} fixtures created (swebench-extra-01 through swebench-extra-{len(fixtures):02d})")


if __name__ == "__main__":
    main()

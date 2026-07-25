#!/usr/bin/env python3
"""Generate 10 additional buggy SWE-bench fixtures (N11-N20)."""

from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures"


FIXTURES = {
    "swebench-n-11": {
        "README.md": "# N11: Encoding Mismatch\n\n**Bug**: Function compares bytes to str directly, which always fails in Python 3.\n\n**Fix**: Decode bytes before comparison, or use isinstance checks.\n",
        "encoder.py": """\
def normalize_header(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return value.strip().lower()


def match_header(expected, actual):
    return normalize_header(expected) == normalize_header(actual)


def has_header(headers, target):
    for key in headers:
        if match_header(key, target):
            return True
    return False
""",
        "test_encoder.py": """\
from encoder import match_header, has_header


def test_match_str_str():
    assert match_header("Content-Type", "content-type")


def test_match_bytes_str():
    assert match_header(b"Content-Type", "content-type")


def test_match_str_bytes():
    assert match_header("Content-Type", b"content-type")


def test_match_bytes_bytes():
    assert match_header(b"Content-Type", b"content-type")


def test_has_header_mixed():
    headers = {b"Content-Type": "application/json"}
    assert has_header(headers, "Content-Type")


def test_has_header_missing():
    headers = {"Accept": "text/html"}
    assert not has_header(headers, "Content-Type")


def test_normalize_strips_whitespace():
    from encoder import normalize_header
    assert normalize_header("  Content-Type  ") == "content-type"
""",
    },
    "swebench-n-12": {
        "README.md": "# N12: Mutable Default Argument\n\n**Bug**: Function uses `[]` as default argument, accumulating state across calls.\n\n**Fix**: Use `None` and create a new list each call.\n",
        "cache.py": """\
class ItemCache:
    def __init__(self):
        self._store = {}

    def add(self, item):
        if item.category not in self._store:
            self._store[item.category] = []
        self._store[item.category].append(item)

    def get_items(self, category, seen=None):
        if seen is None:
            seen = []
        result = []
        for item in self._store.get(category, []):
            if item.id not in seen:
                seen.append(item.id)
                result.append(item)
        return result


class Item:
    def __init__(self, id, category, name):
        self.id = id
        self.category = category
        self.name = name
""",
        "test_cache.py": """\
from cache import Item, ItemCache


def test_get_items_once():
    c = ItemCache()
    c.add(Item(1, "a", "x"))
    c.add(Item(2, "a", "y"))
    assert len(c.get_items("a")) == 2


def test_get_items_twice_is_idempotent():
    c = ItemCache()
    c.add(Item(1, "a", "x"))
    c.get_items("a")
    second = c.get_items("a")
    assert len(second) == 0


def test_get_items_different_categories():
    c = ItemCache()
    c.add(Item(1, "a", "x"))
    c.add(Item(2, "b", "y"))
    assert len(c.get_items("a")) == 1
    assert len(c.get_items("b")) == 1


def test_get_items_independent_calls():
    c = ItemCache()
    c.add(Item(1, "a", "x"))
    c.add(Item(2, "a", "y"))
    first = c.get_items("a")
    second = c.get_items("a")
    # Each call should return only unseen items
    assert len(first) == 2
    assert len(second) == 0
""",
    },
    "swebench-n-13": {
        "README.md": "# N13: Incorrect Exception Chaining\n\n**Bug**: A retry wrapper catches all exceptions and raises a new generic error, losing the original traceback.\n\n**Fix**: Use `raise RetryError(msg) from original_exception`.\n",
        "retry.py": """\
import time


class RetryError(Exception):
    pass


def retry(operation, max_attempts=3, delay=0.1):
    for attempt in range(max_attempts):
        try:
            return operation()
        except Exception:
            if attempt == max_attempts - 1:
                raise RetryError(f"failed after {max_attempts} attempts")
            time.sleep(delay)


def parse_int(s):
    return int(s)


def divide(a, b):
    return a / b
""",
        "test_retry.py": """\
import pytest
from retry import retry, RetryError, parse_int, divide


def test_retry_succeeds():
    calls = []
    def op():
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("not yet")
        return "ok"
    assert retry(op) == "ok"


def test_retry_exhausted():
    def fail():
        raise ValueError("always fails")
    with pytest.raises(RetryError):
        retry(fail)


def test_retry_raises_original_error_type():
    def fail():
        raise ValueError("original")
    with pytest.raises(RetryError) as exc_info:
        retry(fail)
    # The original exception should be chained
    assert isinstance(exc_info.value.__cause__, ValueError), \
        f"Expected ValueError as cause, got {exc_info.value.__cause__}"


def test_retry_preserves_original_message():
    def fail():
        raise ValueError("secret message")
    with pytest.raises(RetryError):
        retry(fail)
""",
    },
    "swebench-n-14": {
        "README.md": "# N14: Decimal Precision Loss\n\n**Bug**: Financial calculation performs division before multiplication, losing precision.\n\n**Fix**: Multiply before dividing, or use Decimal.\n",
        "finance.py": """\
def compute_annual_return(start, end, years):
    return ((end - start) / start) / years


def compute_total_return(monthly_contributions):
    return sum(monthly_contributions)


def compute_growth_rate(values):
    if len(values) < 2:
        return 0.0
    start = values[0]
    end = values[-1]
    return compute_annual_return(start, end, len(values) - 1)
""",
        "test_finance.py": """\
from finance import compute_annual_return, compute_growth_rate


def test_no_growth():
    result = compute_annual_return(100, 100, 1)
    assert result == 0.0


def test_double_in_one_year():
    result = compute_annual_return(100, 200, 1)
    assert result == 1.0


def test_compound_large_numbers():
    result = compute_annual_return(10000, 11000, 1)
    assert result == 0.1


def test_growth_rate():
    result = compute_growth_rate([1000, 1100, 1210])
    assert abs(result - 0.1) < 0.01, f"Expected ~0.1, got {result}"


def test_precision():
    result = compute_annual_return(1, 2, 3)
    expected = 1.0 / 3.0
    assert abs(result - expected) < 0.0001, f"Expected {expected}, got {result}"
""",
    },
    "swebench-n-15": {
        "README.md": "# N15: Config Override Bug\n\n**Bug**: Config defaults are not properly overridden by user-provided values.\n\n**Fix**: Use dict.update or **kwargs merging.\n",
        "config.py": """\
CONFIG_DEFAULTS = {
    "host": "localhost",
    "port": 8080,
    "debug": False,
    "timeout": 30,
}


def build_config(overrides=None):
    config = dict(CONFIG_DEFAULTS)
    if overrides:
        for key in overrides:
            config[key] = overrides[key]
    return config


def merge_configs(base, overlay):
    result = {}
    for key in base:
        result[key] = base[key]
    for key in overlay:
        result[key] = overlay[key]
    return result


class AppConfig:
    def __init__(self, **kwargs):
        self.settings = CONFIG_DEFAULTS.copy()
        if kwargs:
            self.settings.update(kwargs)
""",
        "test_config.py": """\
from config import build_config, merge_configs, AppConfig, CONFIG_DEFAULTS


def test_defaults():
    cfg = build_config()
    assert cfg["host"] == "localhost"
    assert cfg["port"] == 8080


def test_override_port():
    cfg = build_config({"port": 9090})
    assert cfg["port"] == 9090
    assert cfg["host"] == "localhost"


def test_override_debug():
    cfg = build_config({"debug": True, "timeout": 60})
    assert cfg["debug"] is True
    assert cfg["timeout"] == 60


def test_merge_configs():
    base = {"a": 1, "b": 2}
    overlay = {"b": 3, "c": 4}
    result = merge_configs(base, overlay)
    assert result == {"a": 1, "b": 3, "c": 4}


def test_appconfig_override():
    cfg = AppConfig(port=3000, debug=True)
    assert cfg.settings["port"] == 3000
    assert cfg.settings["debug"] is True
    assert cfg.settings["host"] == "localhost"
""",
    },
    "swebench-n-16": {
        "README.md": "# N16: Recursive Depth Limit\n\n**Bug**: Recursive tree traversal has no depth limit, causing stack overflow on deep trees.\n\n**Fix**: Add max_depth parameter with default.\n",
        "tree.py": """\
class TreeNode:
    def __init__(self, value, children=None):
        self.value = value
        self.children = children or []

    def add_child(self, child):
        self.children.append(child)


def find_node(root, target):
    if root.value == target:
        return root
    for child in root.children:
        result = find_node(child, target)
        if result is not None:
            return result
    return None


def tree_depth(root):
    if not root.children:
        return 0
    return 1 + max(tree_depth(child) for child in root.children)


def count_nodes(root):
    count = 1
    for child in root.children:
        count += count_nodes(child)
    return count
""",
        "test_tree.py": """\
from tree import TreeNode, find_node, tree_depth, count_nodes


def test_find_root():
    root = TreeNode("a")
    assert find_node(root, "a") is root


def test_find_child():
    root = TreeNode("a")
    child = TreeNode("b")
    root.add_child(child)
    assert find_node(root, "b") is child


def test_find_nonexistent():
    root = TreeNode("a")
    assert find_node(root, "z") is None


def test_tree_depth():
    root = TreeNode("a")
    root.add_child(TreeNode("b"))
    root.children[0].add_child(TreeNode("c"))
    assert tree_depth(root) == 2


def test_deep_tree():
    root = TreeNode("a")
    current = root
    for i in range(500):
        new = TreeNode(str(i))
        current.add_child(new)
        current = new
    result = find_node(root, "250")
    assert result is not None
    assert result.value == "250"
""",
    },
    "swebench-n-17": {
        "README.md": "# N17: String Escape Bug\n\n**Bug**: HTML escaping only handles `<` and `>` but misses `&`, `\"`, and `'`.\n\n**Fix**: Escape all five HTML special characters.\n",
        "html_util.py": """\
def escape_html(text):
    text = str(text)
    result = ""
    for ch in text:
        if ch == "<":
            result += "&lt;"
        elif ch == ">":
            result += "&gt;"
        else:
            result += ch
    return result


def escape_attribute(text):
    return escape_html(text).replace('"', "&quot;")


def strip_tags(text):
    result = ""
    in_tag = False
    for ch in text:
        if ch == "<":
            in_tag = True
        elif ch == ">":
            in_tag = False
        elif not in_tag:
            result += ch
    return result
""",
        "test_html_util.py": """\
from html_util import escape_html, escape_attribute, strip_tags


def test_escape_lt():
    assert escape_html("<hello>") == "&lt;hello&gt;"


def test_escape_ampersand():
    assert escape_html("a & b") == "a &amp; b"


def test_escape_quotes_in_attribute():
    result = escape_attribute('say "hello"')
    assert "&quot;" in result, f"Expected &quot; in {result}"


def test_escape_single_quote():
    result = escape_attribute("it's")
    assert "&#x27;" in result or "&apos;" in result or "'" not in result.split("&quot;")[0], \
        f"Single quote not escaped in {result}"


def test_strip_tags():
    assert strip_tags("<b>bold</b>") == "bold"


def test_escape_twice_is_idempotent():
    once = escape_html("<>&")
    twice = escape_html(once)
    assert once == twice, f"Escaping twice changed output: {once} -> {twice}"
""",
    },
    "swebench-n-18": {
        "README.md": "# N18: Incomplete Input Validation\n\n**Bug**: Email validator checks for `@` but doesn't validate domain format.\n\n**Fix**: Add domain format validation (at least one dot, no spaces).\n",
        "validator.py": """\
import re


def validate_email(email):
    if "@" not in email:
        return False
    local, domain = email.split("@", 1)
    if not local or not domain:
        return False
    return True


def validate_username(name):
    if len(name) < 3:
        return False
    if not name.isalnum():
        return False
    return True


def validate_password(password):
    if len(password) < 8:
        return False
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not has_upper or not has_digit:
        return False
    return True
""",
        "test_validator.py": """\
from validator import validate_email, validate_username, validate_password


def test_valid_email():
    assert validate_email("user@example.com")


def test_email_no_at():
    assert not validate_email("userexample.com")


def test_email_no_domain():
    assert not validate_email("user@.com")


def test_email_no_tld():
    assert not validate_email("user@example"), "Email without TLD should be invalid"


def test_email_with_dot_in_local():
    assert validate_email("first.last@example.com")


def test_email_space_in_domain():
    assert not validate_email("user@exa mple.com"), "Domain with spaces should be invalid"


def test_email_no_local():
    assert not validate_email("@example.com")


def test_username_valid():
    assert validate_username("alice")


def test_username_too_short():
    assert not validate_username("ab")


def test_password_valid():
    assert validate_password("Secure1pass")
""",
    },
    "swebench-n-19": {
        "README.md": "# N19: Incorrect Operator Precedence\n\n**Bug**: Boolean expression `a and b or c` is evaluated as `(a and b) or c` but intended as `a and (b or c)`.\n\n**Fix**: Add explicit parentheses.\n",
        "access.py": """\
def can_access(user, resource, action):
    is_admin = user.get("role") == "admin"
    is_owner = resource.get("owner") == user.get("id")
    is_public = resource.get("public", False)
    permissions = user.get("permissions", [])

    if is_admin or is_owner and action in permissions:
        return True
    if is_public and action == "read":
        return True
    return False


def can_edit(user, resource):
    return can_access(user, resource, "write")


def can_delete(user, resource):
    return can_access(user, resource, "delete")
""",
        "test_access.py": """\
from access import can_access, can_edit, can_delete


def test_admin_can_anything():
    user = {"role": "admin", "id": 1, "permissions": []}
    resource = {"owner": 2, "public": False}
    assert can_access(user, resource, "read")
    assert can_access(user, resource, "write")


def test_owner_with_permission():
    user = {"role": "user", "id": 1, "permissions": ["write"]}
    resource = {"owner": 1, "public": False}
    assert can_edit(user, resource)


def test_owner_without_permission():
    user = {"role": "user", "id": 1, "permissions": []}
    resource = {"owner": 1, "public": False}
    assert not can_edit(user, resource), "Owner without write permission should not edit"


def test_non_owner_with_permission():
    user = {"role": "user", "id": 2, "permissions": ["write"]}
    resource = {"owner": 1, "public": False}
    assert not can_edit(user, resource), "Non-owner should not edit even with permission"


def test_public_read():
    user = {"role": "user", "id": 2, "permissions": []}
    resource = {"owner": 1, "public": True}
    assert can_access(user, resource, "read")


def test_public_write_denied():
    user = {"role": "user", "id": 2, "permissions": []}
    resource = {"owner": 1, "public": True}
    assert not can_access(user, resource, "write")
""",
    },
    "swebench-n-20": {
        "README.md": "# N20: Incomplete Copy (Shallow Copy Bug)\n\n**Bug**: Nested dict is copied with a shallow copy, so modifying nested values affects the original.\n\n**Fix**: Use `copy.deepcopy()`.\n",
        "document.py": """\
import copy


class Document:
    def __init__(self, data):
        self.data = data

    def clone(self):
        return Document(dict(self.data))

    def set_metadata(self, key, value):
        self.data["metadata"] = self.data.get("metadata", {})
        self.data["metadata"][key] = value

    def get_metadata(self, key):
        meta = self.data.get("metadata", {})
        return meta.get(key)


def merge_documents(doc1, doc2):
    merged = {}
    for k, v in doc1.data.items():
        merged[k] = v
    for k, v in doc2.data.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k].update(v)
        else:
            merged[k] = v
    return Document(merged)
""",
        "test_document.py": """\
from document import Document, merge_documents


def test_clone_preserves_values():
    doc = Document({"title": "Hello", "version": 1})
    cloned = doc.clone()
    assert cloned.data["title"] == "Hello"


def test_clone_isolation():
    doc = Document({"items": [1, 2, 3], "meta": {"views": 10}})
    cloned = doc.clone()
    cloned.data["meta"]["views"] = 99
    assert doc.data["meta"]["views"] == 10, \
        f"Expected original views=10, got {doc.data['meta']['views']}"


def test_clone_list_isolation():
    doc = Document({"items": [1, 2, 3]})
    cloned = doc.clone()
    cloned.data["items"].append(4)
    assert len(doc.data["items"]) == 3, \
        f"Original list should have 3 items, has {len(doc.data['items'])}"


def test_set_metadata():
    doc = Document({})
    doc.set_metadata("author", "Alice")
    assert doc.get_metadata("author") == "Alice"


def test_merge_documents():
    doc1 = Document({"config": {"theme": "dark"}})
    doc2 = Document({"config": {"font": "large"}})
    merged = merge_documents(doc1, doc2)
    assert merged.data["config"]["theme"] == "dark"
    assert merged.data["config"]["font"] == "large"
""",
    },
}


def main():
    for dirname, files in FIXTURES.items():
        d = BASE / dirname
        d.mkdir(parents=True, exist_ok=True)
        for fname, content in files.items():
            (d / fname).write_text(content)
        print(f"  Created {dirname}")

    print("\nDone. 10 fixtures created (N11-N20).")


if __name__ == "__main__":
    main()

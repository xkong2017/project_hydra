"""Anti-pattern library: learned failure patterns from previous runs.

Injected into refinement prompts when similar bug patterns are detected.
The library grows over time as the pipeline sees more tasks.
"""

ANTI_PATTERNS = {
    "mutable_default": {
        "symptoms": ["def f(x=[])", "def f(x={})", "def f(x=set())"],
        "fix": "Change to `def f(x=None)` and add `if x is None: x = []` inside the function.",
        "reason": "Mutable default arguments are evaluated once at function definition, not each call.",
    },
    "exception_chaining": {
        "symptoms": ["except.*: raise Exception(", "except.*: raise ValueError("],
        "fix": "Use `raise NewException(msg) from original_exception` to preserve the traceback.",
        "reason": "Bare raise inside except loses the original exception context and traceback.",
    },
    "broad_except": {
        "symptoms": ["except Exception:", "except:", "try:\n    ...\nexcept:\n    pass"],
        "fix": "Catch specific exceptions only. Use `except SpecificError:` not `except Exception:`.",
        "reason": "Broad except clauses silently swallow errors that should propagate.",
    },
    "shallow_copy": {
        "symptoms": ["dict(other)", "dict(source)", "{**data}"],
        "fix": "Use `copy.deepcopy()` for nested structures. `dict()` only does a shallow copy.",
        "reason": "Shallow copies share references to nested objects; mutations affect the original.",
    },
    "non_atomic_counter": {
        "symptoms": ["self.value += 1"],
        "fix": "Use `threading.Lock` or `queue.Queue` for thread-safe operations.",
        "reason": "`self.value += 1` is a read-modify-write that is not atomic under threading.",
    },
    "string_not_escaped": {
        "symptoms": ["return f'\"{text}\"'"],
        "fix": "Escape special characters: `text.replace('\"', '\\\\\"').replace('\\\\', '\\\\\\\\')`",
        "reason": "Unescaped special characters in strings cause injection or parsing errors.",
    },
    "sql_injection": {
        "symptoms": ["f\"SELECT * FROM {table}\"", "f\"WHERE name = '{name}'\""],
        "fix": "Use parameterized queries: `cursor.execute('SELECT * FROM users WHERE name = ?', (name,))`",
        "reason": "String interpolation in SQL allows injection attacks.",
    },
    "off_by_one": {
        "symptoms": ["range(1, n)", "items[:n-1]", "start = page * per_page"],
        "fix": "Check inclusive vs exclusive bounds. For 0-indexed: `items[start:start+length]`.",
        "reason": "Off-by-one errors are the most common bug pattern in programming.",
    },
    "class_variable_sharing": {
        "symptoms": ["_active = []  # class level", "_cache = {}  # class level"],
        "fix": "Move mutable state to `__init__` as `self._active = []`.",
        "reason": "Class-level mutable variables are shared across all instances.",
    },
    "timezone_naive": {
        "symptoms": ["datetime.now()", "datetime.utcnow()"],
        "fix": "Use `datetime.now(timezone.utc)` for timezone-aware datetimes.",
        "reason": "Naive datetimes cannot be safely compared with aware datetimes.",
    },
}


def detect_anti_patterns(source_code: str, test_failures: str = "") -> list[dict]:
    """Detect which anti-patterns match the current task.

    Returns list of anti-pattern dicts ordered by relevance score.
    """
    import re
    matches = []
    source_lower = source_code.lower()
    failures_lower = test_failures.lower()

    for name, pattern in ANTI_PATTERNS.items():
        score = 0
        for symptom in pattern["symptoms"]:
            if symptom.lower() in source_lower:
                score += 2
        for token in pattern["reason"].lower().split()[:5]:
            if token in failures_lower:
                score += 1
        if score > 0:
            matches.append((score, name, pattern))

    matches.sort(key=lambda x: -x[0])
    return [{"name": m[1], "fix": m[2]["fix"], "reason": m[2]["reason"]} for m in matches]


def format_anti_pattern_hints(source_code: str, test_failures: str = "") -> str:
    """Format matching anti-patterns as prompt additions."""
    matches = detect_anti_patterns(source_code, test_failures)
    if not matches:
        return ""

    hints = "\n## Known Anti-Patterns to Watch For\n"
    for m in matches[:3]:
        hints += f"- {m['name']}: {m['reason']}\n  Fix: {m['fix']}\n"
    return hints

#!/usr/bin/env python3
"""Fake Claude Code CLI for E2E testing.

Detects the scenario from files present in CWD, applies the fix,
commits to git, and outputs trajectory JSON to stdout.

Also supports legacy FAKE_CLAUDE_SCENARIO env var for backward compat.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

# Ensure project root is in sys.path for legacy scenario imports
_script_root = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_script_root))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def git_commit(message: str) -> None:
    """Stage all changes and commit."""
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", message], check=True)


def fix_pagination() -> int:
    """Fix off-by-one pagination error."""
    path = "paginator.py"
    if not os.path.isfile(path):
        return -1
    content = open(path).read()
    content = content.replace(
        "start = page * per_page",
        "start = (page - 1) * per_page",
    )
    open(path, "w").write(content)
    git_commit("fix: correct page offset calculation")
    return 0


def fix_cache_isolation() -> int:
    """Fix cache key collision by adding tenant_id."""
    path = "cache.py"
    if not os.path.isfile(path):
        return -1
    content = open(path).read()
    content = '''"""Simple in-memory cache with tenant isolation."""


class TenantCache:
    """Cache that should isolate data by tenant."""

    def __init__(self):
        self._store = {}

    def get(self, tenant_id, resource_id):
        """Get a cached value for a tenant and resource."""
        key = self._get_cache_key(tenant_id, resource_id)
        return self._store.get(key)

    def set(self, tenant_id, resource_id, value):
        """Set a cached value for a tenant and resource."""
        key = self._get_cache_key(tenant_id, resource_id)
        self._store[key] = value

    def delete(self, tenant_id, resource_id):
        """Delete a cached value."""
        key = self._get_cache_key(tenant_id, resource_id)
        self._store.pop(key, None)

    def _get_cache_key(self, tenant_id, resource_id):
        """Generate cache key."""
        return f"cache:{tenant_id}:{resource_id}"

    def clear(self):
        """Clear all cached data."""
        self._store.clear()

    def size(self):
        """Return number of cached entries."""
        return len(self._store)
'''
    open(path, "w").write(content)
    git_commit("fix: add tenant_id to cache keys for isolation")
    return 0


def fix_async_race() -> int:
    """Fix fire-and-forget asyncio cleanup."""
    path = "resource_pool.py"
    if not os.path.isfile(path):
        return -1
    content = open(path).read()
    content = content.replace(
        ("        for res in self._resources:\n"
         "            asyncio.create_task(res.close())  "
         "# noqa: RUF006  # BUG: fire and forget\n"
         "        self._resources.clear()"),
        ("        tasks = [res.close() for res in self._resources]\n"
         "        await asyncio.gather(*tasks)\n"
         "        self._resources.clear()"),
    )
    open(path, "w").write(content)
    git_commit("fix: await all cleanup tasks instead of fire-and-forget")
    return 0


def fix_parser_coercion() -> int:
    """Fix parser type coercion to always return float."""
    path = "parser.py"
    if not os.path.isfile(path):
        return -1
    content = open(path).read()
    content = content.replace(
        "        return value  # Should be: return float(value)\n",
        "        return float(value)\n",
    )
    content = content.replace(
        "        return num  # BUG: same problem — int stays int\n",
        "        return float(num)  # Always return float\n",
    )
    open(path, "w").write(content)
    git_commit("fix: always return float from parse_amount")
    return 0


def fix_discount_tier() -> int:
    """Fix missing premium discount tier."""
    path = "discount.py"
    if not os.path.isfile(path):
        return -1
    content = open(path).read()
    content = content.replace(
        ('        "standard": 0.1,\n'
         '        # BUG: "premium" is missing — falls through to None\n'
         '        "enterprise": 0.3,'),
        ('        "standard": 0.1,\n'
         '        "premium": 0.2,\n'
         '        "enterprise": 0.3,'),
    )
    open(path, "w").write(content)
    git_commit("fix: add missing premium discount tier")
    return 0


# Mapping from filename to fix function (legacy toy scenarios)
SCENARIO_DETECTORS = [
    ("paginator.py", fix_pagination),
    ("cache.py", fix_cache_isolation),
    ("resource_pool.py", fix_async_race),
    ("parser.py", fix_parser_coercion),
    ("discount.py", fix_discount_tier),
]


def detect_and_fix() -> int:
    """Detect scenario from CWD files and apply the fix."""
    # Try legacy toy scenarios first
    for filename, fix_fn in SCENARIO_DETECTORS:
        if os.path.isfile(filename):
            return fix_fn()

    # Try SWE-bench verified tasks
    from tests.fake_claude.swe_tasks import detect_and_fix_swe

    return detect_and_fix_swe()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Fake Claude Code CLI for testing")
    parser.add_argument("--scenario", type=str, default=None, help="Scenario name override")
    args = parser.parse_args()

    # CLI --scenario flag takes highest priority
    # Legacy env var next, then file-based detection
    scenario_name = args.scenario or os.environ.get("FAKE_CLAUDE_SCENARIO", "")

    if scenario_name:
        from tests.fake_claude.scenarios import SCENARIOS

        scenario = SCENARIOS.get(scenario_name)
        if scenario is None:
            sys.stderr.write(f"Unknown scenario: {scenario_name}\n")
            return 1
        if scenario.stdout:
            sys.stdout.write(scenario.stdout + "\n")
        if scenario.stderr:
            sys.stderr.write(scenario.stderr + "\n")
        return scenario.exit_code

    # File-based detection mode (for real orchestrator integration)
    exit_code = detect_and_fix()
    if exit_code != 0:
        # No scenario files found: default to success trajectory
        # (mimics a successful Claude run when called standalone)
        pass

    # Output trajectory JSON (matches Claude Code --output-format json)
    trajectory = {
        "status": "completed",
        "trajectory": {
            "candidate_id": "fake-claude-worker",
            "completion_status": "done",
        },
    }
    sys.stdout.write(json.dumps(trajectory) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

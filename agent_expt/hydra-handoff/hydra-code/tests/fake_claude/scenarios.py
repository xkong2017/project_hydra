"""Scenario definitions for fake Claude responses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Scenario:
    """A predefined scenario for fake Claude responses."""

    name: str
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    files_to_create: dict[str, str] = field(default_factory=dict)
    files_to_edit: dict[str, str] = field(default_factory=dict)


# F1: Pagination bug fix
SCENARIO_F1 = Scenario(
    name="f1-pagination-fix",
    exit_code=0,
    stdout='{"status": "completed", "trajectory": {"candidate_id": "f1-worker", "completion_status": "done"}}',
)

# F2: Cache isolation fix
SCENARIO_F2 = Scenario(
    name="f2-cache-fix",
    exit_code=0,
    stdout='{"status": "completed", "trajectory": {"candidate_id": "f2-worker", "completion_status": "done"}}',
)

# F3: Async race condition fix
SCENARIO_F3 = Scenario(
    name="f3-async-race-fix",
    exit_code=0,
    stdout='{"status": "completed", "trajectory": {"candidate_id": "f3-worker", "completion_status": "done"}}',
)

# F4: Parser compatibility fix
SCENARIO_F4 = Scenario(
    name="f4-parser-fix",
    exit_code=0,
    stdout='{"status": "completed", "trajectory": {"candidate_id": "f4-worker", "completion_status": "done"}}',
)

# F5: Misleading test fix
SCENARIO_F5 = Scenario(
    name="f5-misleading-fix",
    exit_code=0,
    stdout='{"status": "completed", "trajectory": {"candidate_id": "f5-worker", "completion_status": "done"}}',
)

# F6: Multi-file API fix
SCENARIO_F6 = Scenario(
    name="f6-multifile-fix",
    exit_code=0,
    stdout='{"status": "completed", "trajectory": {"candidate_id": "f6-worker", "completion_status": "done"}}',
)

# Failure scenario
SCENARIO_FAILURE = Scenario(
    name="failure",
    exit_code=1,
    stderr="Error: test failed",
)

# Timeout scenario
SCENARIO_TIMEOUT = Scenario(
    name="timeout",
    exit_code=124,
    stderr="timeout exceeded",
)

SCENARIOS: dict[str, Scenario] = {
    "f1": SCENARIO_F1,
    "f2": SCENARIO_F2,
    "f3": SCENARIO_F3,
    "f4": SCENARIO_F4,
    "f5": SCENARIO_F5,
    "f6": SCENARIO_F6,
    "failure": SCENARIO_FAILURE,
    "timeout": SCENARIO_TIMEOUT,
}

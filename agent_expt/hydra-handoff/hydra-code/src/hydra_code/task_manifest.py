"""SWE-bench task manifest parsing for HydraCode.

Supports `.hydra/task.yaml` format with FAIL_TO_PASS / PASS_TO_PASS
test case definitions compatible with SWE-bench JSON manifests.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TestCaseEntry:
    """A single test case from a task manifest."""
    file: str
    name: str
    method: str | None = None


# Backward compat alias (avoid breaking imports)
TestCase = TestCaseEntry


@dataclass(frozen=True)
class TaskManifest:
    """Parsed task manifest with test commands and validation cases."""
    # Test commands to run (e.g., ["pytest -q"])
    test_commands: list[str]
    # Full pytest/test invocations for validation
    validation_commands: list[str]
    # FAIL_TO_PASS: tests that should start passing after the fix
    fail_to_pass: list[TestCaseEntry]
    # PASS_TO_PASS: tests that should continue passing (regression guard)
    pass_to_pass: list[TestCaseEntry]


TASK_YAML_DIR = Path(".hydra")


def parse_task_manifest(repo_root: Path) -> TaskManifest | None:
    """Parse .hydra/task.yaml if it exists, otherwise None."""
    task_yaml = repo_root / TASK_YAML_DIR / "task.yaml"
    if not task_yaml.exists():
        return None

    import importlib

    try:
        yaml = importlib.import_module("yaml")
    except ImportError:
        # Fallback: basic YAML parsing without PyYAML
        return _parse_yaml_fallback(task_yaml)

    data: dict[str, Any] = yaml.safe_load(task_yaml.read_text()) or {}
    return _build_manifest_from_dict(data, repo_root)


def _parse_yaml_fallback(path: Path) -> TaskManifest | None:
    """Minimal YAML fallback for simple task.yaml files without PyYAML."""
    if not path.exists():
        return None
    text = path.read_text()
    test_commands: list[str] = []
    fail_to_pass: list[TestCase] = []
    pass_to_pass: list[TestCase] = []

    current_section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped == "test_commands:":
            current_section = "test_commands"
            continue
        if stripped == "fail_to_pass:":
            current_section = "fail_to_pass"
            continue
        if stripped == "pass_to_pass:":
            current_section = "pass_to_pass"
            continue

        if stripped.startswith("- "):
            value = stripped[2:].strip()
            if current_section == "test_commands":
                test_commands.append(value)
            elif current_section in ("fail_to_pass", "pass_to_pass"):
                # Simple format: "file.py::test_name" or "file.py::TestClass::method"
                parts = value.split("::")
                tc = TestCase(
                    file=parts[0],
                    name=value,
                    method=parts[-1] if len(parts) > 1 else None,
                )
                if current_section == "fail_to_pass":
                    fail_to_pass.append(tc)
                else:
                    pass_to_pass.append(tc)

    validation = _build_pytest_commands(fail_to_pass + pass_to_pass)
    return TaskManifest(
        test_commands=test_commands or ["pytest -q"],
        validation_commands=validation or test_commands or ["pytest -q"],
        fail_to_pass=fail_to_pass,
        pass_to_pass=pass_to_pass,
    )


def _build_manifest_from_dict(data: dict[str, Any], repo_root: Path) -> TaskManifest:
    """Build TaskManifest from parsed YAML dict."""
    test_commands = data.get("test_commands", ["pytest -q"])
    if isinstance(test_commands, str):
        test_commands = [test_commands]

    fail_to_pass = _parse_test_cases(data.get("fail_to_pass", []))
    pass_to_pass = _parse_test_cases(data.get("pass_to_pass", []))

    # Build validation commands from specific test cases
    validation = _build_pytest_commands(fail_to_pass + pass_to_pass)

    return TaskManifest(
        test_commands=test_commands,
        validation_commands=validation or test_commands,
        fail_to_pass=fail_to_pass,
        pass_to_pass=pass_to_pass,
    )


def _parse_test_cases(raw: list[Any]) -> list[TestCaseEntry]:
    """Parse test case entries from manifest dict."""
    cases: list[TestCaseEntry] = []
    for item in raw:
        if isinstance(item, str):
            parts = item.split("::")
            cases.append(
                TestCaseEntry(
                    file=parts[0],
                    name=item,
                    method=parts[-1] if len(parts) > 1 else None,
                )
            )
        elif isinstance(item, dict):
            cases.append(
                TestCase(
                    file=str(item.get("file", "")),
                    name=str(item.get("name", item.get("file", ""))),
                    method=item.get("method"),
                )
            )
    return cases


def _build_pytest_commands(cases: list[TestCase]) -> list[str]:
    """Build pytest commands from test cases."""
    if not cases:
        return []

    # Group by file for efficiency
    files: dict[str, list[str]] = {}
    for tc in cases:
        files.setdefault(tc.file, []).append(tc.name)

    commands: list[str] = []
    for file_path, names in files.items():
        if len(names) == 1 and names[0] == file_path:
            commands.append(f"pytest {file_path} -v")
        else:
            selectors = " ".join(f"{file_path}::{n}" for n in names)
            commands.append(f"pytest {selectors} -v")
    return commands


def load_or_detect(repo_root: Path | None) -> TaskManifest:
    """Load task manifest if available, otherwise detect default test commands."""
    if repo_root is None:
        return TaskManifest(
            test_commands=["pytest -q"],
            validation_commands=["pytest -q"],
            fail_to_pass=[],
            pass_to_pass=[],
        )
    manifest = parse_task_manifest(repo_root)
    if manifest is not None:
        return manifest

    commands = _detect_test_commands(repo_root)
    return TaskManifest(
        test_commands=commands,
        validation_commands=commands,
        fail_to_pass=[],
        pass_to_pass=[],
    )


def _detect_test_commands(repo_root: Path) -> list[str]:
    """Auto-detect test commands from repo structure."""
    if (repo_root / "pyproject.toml").exists():
        return ["pytest -q"]
    if (repo_root / "setup.py").exists():
        return ["pytest -q"]
    if (repo_root / "package.json").exists():
        return ["npm test"]
    if (repo_root / "Makefile").exists():
        return ["make test"]
    if (repo_root / "Cargo.toml").exists():
        return ["cargo test --quiet"]
    return []

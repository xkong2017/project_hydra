"""Unit tests for SWE-bench task manifest parsing."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from hydra_code import task_manifest
from hydra_code.task_manifest import TaskManifest, TestCase


class TestParseTestCase:
    """Test case parsing from manifest entries."""

    def test_simple_string(self) -> None:
        cases = task_manifest._parse_test_cases(["tests/test_foo.py::test_bar"])
        assert len(cases) == 1
        assert cases[0].file == "tests/test_foo.py"
        assert cases[0].name == "tests/test_foo.py::test_bar"

    def test_class_method(self) -> None:
        cases = task_manifest._parse_test_cases(
            ["tests/test_foo.py::TestClass::test_method"]
        )
        assert len(cases) == 1
        assert cases[0].method == "test_method"

    def test_dict_entry(self) -> None:
        cases = task_manifest._parse_test_cases(
            [{"file": "tests/test_foo.py", "name": "test_bar", "method": "test_bar"}]
        )
        assert len(cases) == 1
        assert cases[0].file == "tests/test_foo.py"
        assert cases[0].method == "test_bar"

    def test_empty_list(self) -> None:
        cases = task_manifest._parse_test_cases([])
        assert len(cases) == 0


class TestBuildPytestCommands:
    """Build pytest commands from test cases."""

    def test_single_file(self) -> None:
        cases = [TestCase(file="tests/test_foo.py", name="tests/test_foo.py")]
        cmds = task_manifest._build_pytest_commands(cases)
        assert len(cmds) == 1
        assert cmds[0] == "pytest tests/test_foo.py -v"

    def test_multiple_files(self) -> None:
        cases = [
            TestCase(file="tests/test_a.py", name="tests/test_a.py::test_1"),
            TestCase(file="tests/test_b.py", name="tests/test_b.py::test_2"),
        ]
        cmds = task_manifest._build_pytest_commands(cases)
        assert len(cmds) == 2

    def test_empty_cases(self) -> None:
        cmds = task_manifest._build_pytest_commands([])
        assert cmds == []

    def test_same_file_multiple_tests(self) -> None:
        cases = [
            TestCase(file="tests/test_foo.py", name="tests/test_foo.py::test_1"),
            TestCase(file="tests/test_foo.py", name="tests/test_foo.py::test_2"),
        ]
        cmds = task_manifest._build_pytest_commands(cases)
        assert len(cmds) == 1
        assert "test_1" in cmds[0]
        assert "test_2" in cmds[0]


class TestParseYamlFallback:
    """Test the YAML fallback parser (no PyYAML)."""

    def test_basic_yaml(self, tmp_path: Path) -> None:
        task_yaml = tmp_path / ".hydra" / "task.yaml"
        task_yaml.parent.mkdir()
        task_yaml.write_text(
            "test_commands:\n"
            "  - pytest tests/ -v\n"
            "fail_to_pass:\n"
            "  - tests/test_foo.py::test_bar\n"
            "pass_to_pass:\n"
            "  - tests/test_other.py::test_baz\n"
        )
        manifest = task_manifest._parse_yaml_fallback(task_yaml)
        assert manifest is not None
        assert manifest.test_commands == ["pytest tests/ -v"]
        assert len(manifest.fail_to_pass) == 1
        assert len(manifest.pass_to_pass) == 1

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        result = task_manifest._parse_yaml_fallback(tmp_path / "nonexistent.yaml")
        assert result is None

    def test_empty_yaml(self, tmp_path: Path) -> None:
        task_yaml = tmp_path / ".hydra" / "task.yaml"
        task_yaml.parent.mkdir()
        task_yaml.write_text("# empty\n")
        manifest = task_manifest._parse_yaml_fallback(task_yaml)
        assert manifest is not None
        assert manifest.test_commands == ["pytest -q"]


class TestLoadOrDetect:
    """Test manifest loading with auto-detection fallback."""

    def test_detect_pytest_from_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
        manifest_obj = task_manifest.load_or_detect(tmp_path)
        assert "pytest" in " ".join(manifest_obj.test_commands)

    def test_detect_npm_from_package_json(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(json.dumps({"name": "test"}))
        manifest_obj = task_manifest.load_or_detect(tmp_path)
        assert "npm test" in manifest_obj.test_commands

    def test_detect_makefile(self, tmp_path: Path) -> None:
        (tmp_path / "Makefile").write_text("test:\n\techo ok\n")
        manifest_obj = task_manifest.load_or_detect(tmp_path)
        assert "make test" in manifest_obj.test_commands

    def test_detect_nothing(self, tmp_path: Path) -> None:
        manifest_obj = task_manifest.load_or_detect(tmp_path)
        assert manifest_obj.test_commands == []

    def test_manifest_yaml_takes_precedence(self, tmp_path: Path) -> None:
        # Create a task.yaml
        task_yaml = tmp_path / ".hydra" / "task.yaml"
        task_yaml.parent.mkdir()
        task_yaml.write_text(
            "test_commands:\n"
            "  - pytest tests/custom.py -v\n"
        )
        manifest_obj = task_manifest.load_or_detect(tmp_path)
        assert "tests/custom.py" in " ".join(manifest_obj.test_commands)


class TaskManifestDataclass:
    """Verify TaskManifest dataclass behavior."""

    def test_create_manifest(self) -> None:
        m = TaskManifest(
            test_commands=["pytest -q"],
            validation_commands=["pytest tests/ -v"],
            fail_to_pass=[],
            pass_to_pass=[],
        )
        assert m.test_commands == ["pytest -q"]
        assert m.validation_commands == ["pytest tests/ -v"]

    def test_frozen(self) -> None:
        m = TaskManifest(
            test_commands=["pytest -q"],
            validation_commands=[],
            fail_to_pass=[],
            pass_to_pass=[],
        )
        with pytest.raises(Exception):
            m.test_commands = []  # Should fail on frozen dataclass

    def test_with_cases(self) -> None:
        fail_cases = [TestCase(file="tests/test_a.py", name="test_a")]
        m = TaskManifest(
            test_commands=["pytest -q"],
            validation_commands=["pytest tests/test_a.py -v"],
            fail_to_pass=fail_cases,
            pass_to_pass=[],
        )
        assert len(m.fail_to_pass) == 1
        assert m.fail_to_pass[0].file == "tests/test_a.py"
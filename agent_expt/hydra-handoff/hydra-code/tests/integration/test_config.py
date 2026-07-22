"""Integration tests for configuration management."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.mark.integration
def test_build_run_config_defaults() -> None:
    """Build run config with defaults."""
    from hydra_code.config import build_run_config
    from hydra_code.models import RefineMode, RunMode

    config = build_run_config(task="Fix the bug")
    assert config.task == "Fix the bug"
    assert config.mode == RunMode.STANDARD
    assert config.concurrency == 6
    assert config.base_ref == "HEAD"
    assert config.max_turns == 25
    assert config.agent_timeout_seconds == 600
    assert config.refine_mode == RefineMode.STANDARD


@pytest.mark.integration
def test_build_run_config_custom() -> None:
    """Build run config with custom values."""
    from hydra_code.config import build_run_config
    from hydra_code.models import RefineMode, RunMode

    config = build_run_config(
        task="Custom task",
        mode="fast",
        concurrency=3,
        max_turns=10,
        agent_timeout=300,
        keep_worktrees=True,
        dry_run=True,
        no_refine=True,
        refine_mode="deep",
    )
    assert config.task == "Custom task"
    assert config.mode == RunMode.FAST
    assert config.concurrency == 3
    assert config.max_turns == 10
    assert config.agent_timeout_seconds == 300
    assert config.keep_worktrees is True
    assert config.dry_run is True
    assert config.no_refine is True
    assert config.refine_mode == RefineMode.DEEP


@pytest.mark.integration
def test_build_run_config_output_dir() -> None:
    """Output dir is converted to Path."""
    from hydra_code.config import build_run_config

    config = build_run_config(task="test", output_dir="/tmp/output")
    assert config.output_dir == Path("/tmp/output")

    config_none = build_run_config(task="test")
    assert config_none.output_dir is None


@pytest.mark.integration
def test_config_manager_load_save(temp_workdir: Path) -> None:
    """ConfigManager load and save."""
    from hydra_code.config import ConfigManager

    config_path = temp_workdir / "config.json"
    manager = ConfigManager(config_path=config_path, defaults={"key": "default"})

    # Load when file doesn't exist
    loaded = manager.load()
    assert loaded["key"] == "default"

    # Save and reload
    manager.save({"key": "saved", "new_key": "value"})
    manager2 = ConfigManager(config_path=config_path)
    loaded2 = manager2.load()
    assert loaded2["key"] == "saved"
    assert loaded2["new_key"] == "value"


@pytest.mark.integration
def test_config_manager_get() -> None:
    """ConfigManager get with default."""
    from hydra_code.config import ConfigManager

    manager = ConfigManager()
    manager.load()
    assert manager.get("nonexistent", "fallback") == "fallback"


@pytest.mark.integration
def test_config_manager_merge_defaults(temp_workdir: Path) -> None:
    """Defaults are merged with loaded config."""
    from hydra_code.config import ConfigManager

    config_path = temp_workdir / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"override": "value", "shared": "from_file"}))

    manager = ConfigManager(
        config_path=config_path,
        defaults={"shared": "from_default", "only_default": "yes"},
    )
    loaded = manager.load()
    assert loaded["override"] == "value"
    assert loaded["shared"] == "from_file"  # File overrides default
    assert loaded["only_default"] == "yes"


@pytest.mark.integration
def test_run_config_from_task_file(temp_workdir: Path) -> None:
    """RunConfig from task file."""
    from hydra_code.models import RunConfig

    task_file = temp_workdir / "task.md"
    task_file.write_text("Fix the authentication bug")
    config = RunConfig.from_task_file(task_file)
    assert config.task == "Fix the authentication bug"
    assert config.task_file == task_file

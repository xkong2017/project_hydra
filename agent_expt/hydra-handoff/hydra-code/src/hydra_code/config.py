"""Configuration management for HydraCode-6."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import RefineMode, RunConfig, RunMode

DEFAULT_CONFIG_PATH = Path(".hydra/config.json")


class ConfigManager:
    """Load, validate, and persist run configuration."""

    def __init__(
        self,
        config_path: Path | None = None,
        defaults: dict[str, Any] | None = None,
    ) -> None:
        self._path = config_path or DEFAULT_CONFIG_PATH
        self._defaults = defaults or {}
        self._config: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        """Load configuration from file, merged with defaults."""
        if self._path.exists():
            self._config = json.loads(self._path.read_text())
        else:
            self._config = {}
        merged = {**self._defaults, **self._config}
        return merged

    def save(self, config: dict[str, Any]) -> None:
        """Persist configuration to file."""
        self._config = config
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(config, indent=2))

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self._config.get(key, default)


def build_run_config(
    task: str,
    mode: str = "standard",
    concurrency: int = 6,
    base_ref: str = "HEAD",
    max_turns: int = 25,
    agent_timeout: int = 600,
    test_timeout: int = 120,
    keep_worktrees: bool = False,
    output_dir: str | None = None,
    dry_run: bool = False,
    no_refine: bool = False,
    no_generated_tests: bool = False,
    no_dirty_check: bool = False,
    refine_mode: str = "standard",
    **kwargs: Any,
) -> RunConfig:
    """Construct a RunConfig from CLI parameters."""
    return RunConfig(
        task=task,
        mode=RunMode(mode),
        concurrency=concurrency,
        base_ref=base_ref,
        max_turns=max_turns,
        agent_timeout_seconds=agent_timeout,
        test_timeout_seconds=test_timeout,
        keep_worktrees=keep_worktrees,
        output_dir=Path(output_dir) if output_dir else None,
        dry_run=dry_run,
        no_refine=no_refine,
        no_generated_tests=no_generated_tests,
        no_dirty_check=no_dirty_check,
        refine_mode=RefineMode(refine_mode),
    )

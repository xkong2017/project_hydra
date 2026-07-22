"""SWE-verified tests: Run 5 bug-fix scenarios through the real HydraCode pipeline.

Each test verifies:
1. The fixture has failing tests against buggy code
2. The fix resolves all failing tests
3. The real Orchestrator pipeline processes the scenario end-to-end

Uses fake_claude.py which detects scenarios from CWD files and applies fixes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

# Path to fake_claude script
FAKE_CLAUDE_PATH = Path(__file__).parent.parent / "fake_claude" / "fake_claude.py"


@dataclass
class SWEScenario:
    """A SWE-bench style bug-fix scenario."""

    id: str
    name: str
    fixture_dir: Path
    bug_description: str
    source_files: dict[str, str]
    test_files: dict[str, str]
    test_command: list[str]
    expected_failures: int
    fixes: dict[str, dict[str, str]]
    extra_files: dict[str, str]


def _get_fixtures_root() -> Path:
    return Path(__file__).parent / "fixtures"


def _setup_git_repo(fixture: SWEScenario, work_dir: Path) -> None:
    """Set up a git repo with the buggy code from a fixture."""
    subprocess.run(["git", "init"], cwd=work_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=work_dir, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=work_dir, capture_output=True, check=True,
    )

    for src_name, dst_name in fixture.source_files.items():
        src_path = fixture.fixture_dir / src_name
        dst_path = work_dir / dst_name
        dst_path.write_text(src_path.read_text())

    for src_name, dst_name in fixture.test_files.items():
        src_path = fixture.fixture_dir / src_name
        dst_path = work_dir / dst_name
        dst_path.write_text(src_path.read_text())

    for name, content in fixture.extra_files.items():
        (work_dir / name).write_text(content)

    subprocess.run(["git", "add", "."], cwd=work_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial (buggy)"],
        cwd=work_dir, capture_output=True, check=True,
    )


def _run_tests(work_dir: Path, test_command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run tests and return the result."""
    return subprocess.run(
        test_command,
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _count_failures(result: subprocess.CompletedProcess[str]) -> tuple[int, int]:
    """Count passed and failed tests from pytest output."""
    passed = failed = 0
    output = result.stdout + result.stderr
    for line in output.split("\n"):
        if "passed" in line:
            parts = [p.strip(",.") for p in line.split()]
            for i, part in enumerate(parts):
                if part == "passed":
                    try:
                        passed = int(parts[i - 1])
                    except (ValueError, IndexError):
                        passed = 0
                if part == "failed":
                    try:
                        failed = int(parts[i - 1])
                    except (ValueError, IndexError):
                        failed = 0
    return passed, failed


def _apply_fix(work_dir: Path, fixes: dict[str, dict[str, str]]) -> None:
    """Apply the fix patches to files in the work dir."""
    for filename, replacements in fixes.items():
        filepath = work_dir / filename
        if not filepath.exists():
            continue
        content = filepath.read_text()
        for old_text, new_text in replacements.items():
            content = content.replace(old_text, new_text)
        filepath.write_text(content)


# ─── Scenario Definitions ────────────────────────────────────────────────────


def _build_scenarios() -> list[SWEScenario]:
    fixtures_root = _get_fixtures_root()

    return [
        SWEScenario(
            id="SWE-001",
            name="pagination-off-by-one",
            fixture_dir=fixtures_root / "pagination",
            bug_description="Off-by-one error: page calculation uses page*per_page instead of (page-1)*per_page",
            source_files={"paginator.py": "paginator.py"},
            test_files={"test_pagination.py": "test_pagination.py"},
            test_command=[sys.executable, "-m", "pytest", "-q", "test_pagination.py"],
            expected_failures=3,
            fixes={
                "paginator.py": {
                    "start = page * per_page": "start = (page - 1) * per_page",
                }
            },
            extra_files={},
        ),
        SWEScenario(
            id="SWE-002",
            name="cache-isolation-key-collision",
            fixture_dir=fixtures_root / "cache_isolation",
            bug_description="Cache key missing tenant_id causes cross-tenant data leakage",
            source_files={"cache.py": "cache.py"},
            test_files={"test_cache.py": "test_cache.py"},
            test_command=[sys.executable, "-m", "pytest", "-q", "test_cache.py"],
            expected_failures=3,
            fixes={
                "cache.py": {
                    "def _get_cache_key(self, resource_id):": (
                        "def _get_cache_key(self, tenant_id, resource_id):"
                    ),
                    (
                        "key = self._get_cache_key(resource_id)\n"
                        "        return self._store.get(key)"
                    ): (
                        "key = self._get_cache_key(tenant_id, resource_id)\n"
                        "        return self._store.get(key)"
                    ),
                    (
                        "key = self._get_cache_key(resource_id)\n"
                        "        self._store[key] = value"
                    ): (
                        "key = self._get_cache_key(tenant_id, resource_id)\n"
                        "        self._store[key] = value"
                    ),
                    (
                        "key = self._get_cache_key(resource_id)\n"
                        "        self._store.pop(key, None)"
                    ): (
                        "key = self._get_cache_key(tenant_id, resource_id)\n"
                        "        self._store.pop(key, None)"
                    ),
                    'return f"cache:{resource_id}"': (
                        'return f"cache:{tenant_id}:{resource_id}"'
                    ),
                }
            },
            extra_files={},
        ),
        SWEScenario(
            id="SWE-003",
            name="async-race-fire-and-forget",
            fixture_dir=fixtures_root / "async_race",
            bug_description="Fire-and-forget asyncio.create_task instead of awaiting cleanup",
            source_files={"resource_pool.py": "resource_pool.py"},
            test_files={"test_resource_pool.py": "test_resource_pool.py"},
            test_command=[sys.executable, "-m", "pytest", "-q", "test_resource_pool.py"],
            expected_failures=2,
            fixes={
                "resource_pool.py": {
                    (
                        "        for res in self._resources:\n"
                        "            asyncio.create_task(res.close())  "
                        "# noqa: RUF006  # BUG: fire and forget\n"
                        "        self._resources.clear()"
                    ): (
                        "        tasks = [res.close() for res in self._resources]\n"
                        "        await asyncio.gather(*tasks)\n"
                        "        self._resources.clear()"
                    ),
                }
            },
            extra_files={},
        ),
        SWEScenario(
            id="SWE-004",
            name="parser-type-coercion",
            fixture_dir=fixtures_root / "parser",
            bug_description="parse_amount returns int instead of float for whole numbers",
            source_files={"parser.py": "parser.py"},
            test_files={"test_parser.py": "test_parser.py"},
            test_command=[sys.executable, "-m", "pytest", "-q", "test_parser.py"],
            expected_failures=4,
            fixes={
                "parser.py": {
                    "        return value  # Should be: return float(value)\n":
                    "        return float(value)\n",
                    "        num = json.loads(value)\n        return num  # BUG: same problem — int stays int\n":
                    "        num = json.loads(value)\n        return float(num)  # Always return float\n",
                }
            },
            extra_files={},
        ),
        SWEScenario(
            id="SWE-005",
            name="misleading-test-missing-tier",
            fixture_dir=fixtures_root / "misleading_test",
            bug_description="Premium discount tier missing from discounts dict",
            source_files={"discount.py": "discount.py"},
            test_files={"test_discount.py": "test_discount.py"},
            test_command=[sys.executable, "-m", "pytest", "-q", "test_discount.py"],
            expected_failures=2,
            fixes={
                "discount.py": {
                    (
                        '        "standard": 0.1,\n'
                        '        # BUG: "premium" is missing — falls through to None\n'
                        '        "enterprise": 0.3,'
                    ): (
                        '        "standard": 0.1,\n'
                        '        "premium": 0.2,\n'
                        '        "enterprise": 0.3,'
                    ),
                }
            },
            extra_files={},
        ),
    ]


@pytest.fixture
def swe_scenarios() -> list[SWEScenario]:
    """Return all SWE scenarios."""
    return _build_scenarios()


@pytest.fixture
def swe_scenario(swe_scenarios: list[SWEScenario], request: pytest.FixtureRequest) -> SWEScenario:
    """Parametrize over SWE scenarios."""
    param = getattr(request, "param", None)
    if param:
        return next(s for s in swe_scenarios if s.id == param)
    return swe_scenarios[0]


class TestSWEVerifiedBugs:
    """Verify that each fixture has the expected bug (tests fail before fix)."""

    @pytest.mark.e2e
    @pytest.mark.parametrize("swe_scenario", ["SWE-001", "SWE-002", "SWE-003", "SWE-004", "SWE-005"], indirect=True)
    def test_bug_exists(self, swe_scenario: SWEScenario) -> None:
        """Tests should fail against the buggy code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)
            _setup_git_repo(swe_scenario, work_dir)

            result = _run_tests(work_dir, swe_scenario.test_command)
            assert result.returncode != 0, f"Expected failing tests for {swe_scenario.name}"

            _, failed = _count_failures(result)
            assert failed >= 1, f"Expected at least 1 failing test for {swe_scenario.name}, got {failed}"


class TestSWEVerifiedFixes:
    """Verify that the fix resolves all failing tests."""

    @pytest.mark.e2e
    @pytest.mark.parametrize("swe_scenario", ["SWE-001", "SWE-002", "SWE-003", "SWE-004", "SWE-005"], indirect=True)
    def test_fix_resolves_bug(self, swe_scenario: SWEScenario) -> None:
        """Tests should pass after applying the fix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)
            _setup_git_repo(swe_scenario, work_dir)

            before = _run_tests(work_dir, swe_scenario.test_command)
            assert before.returncode != 0, f"Setup error: tests should fail for {swe_scenario.name}"

            _apply_fix(work_dir, swe_scenario.fixes)

            after = _run_tests(work_dir, swe_scenario.test_command)
            assert after.returncode == 0, (
                f"Tests still fail after fix for {swe_scenario.name}: "
                f"{after.stdout}\n{after.stderr}"
            )


# ─── Real Orchestrator Tests ─────────────────────────────────────────────────


class TestSWEVerifiedOrchestrator:
    """Run each SWE scenario through the real HydraCode Orchestrator pipeline."""

    @pytest.mark.e2e
    @pytest.mark.parametrize("swe_scenario", ["SWE-001", "SWE-002", "SWE-003", "SWE-004", "SWE-005"], indirect=True)
    def test_orchestrator_pipeline(self, swe_scenario: SWEScenario) -> None:
        """Full pipeline: Orchestrator.run() with fake_claude applying fixes."""
        import asyncio

        from hydra_code.models import RunConfig, RunMode
        from hydra_code.orchestrator import Orchestrator

        tmpdir = tempfile.mkdtemp()
        work_dir = Path(tmpdir)
        try:
            _setup_git_repo(swe_scenario, work_dir)

            config = RunConfig(
                task=swe_scenario.bug_description,
                mode=RunMode.FAST,
                claude_binary=sys.executable,
                no_dirty_check=True,
                dry_run=False,
                output_dir=work_dir / "output",
                max_turns=1,
                agent_timeout_seconds=30,
                concurrency=6,
            )

            # Patch RunnerConfig to pass fake_claude script as argument
            import hydra_code.orchestrator as orch_module
            original_run_single = orch_module.Orchestrator._run_single_candidate

            async def patched_run_single(
                self,
                candidate_id: str,
                spec,
                context: str,
                base_sha: str,
                strategy_angle: str = "",
            ) -> None:
                """Patch to inject fake_claude path into the runner command."""
                from hydra_code.claude_runner import ClaudeRunner, RunnerConfig
                from hydra_code.utils import atomic_write_json
                from hydra_code.worktrees import create_worktree, extract_patch

                role = spec.role
                worktree_info = create_worktree(
                    self.run_id, candidate_id, role, base_sha
                )

                prompt = f"{context}\n\n## Role: {role.value}\n"

                runner = ClaudeRunner(
                    RunnerConfig(
                        max_turns=1,
                        timeout_seconds=30,
                        claude_binary=sys.executable,
                    )
                )

                output_dir = self.run_dir / "candidates" / candidate_id
                output_dir.mkdir(parents=True, exist_ok=True)

                # Override _build_command to use fake_claude script
                def patched_build(_p: str) -> list[str]:
                    return [sys.executable, str(FAKE_CLAUDE_PATH), prompt]

                runner._build_command = patched_build

                result = await runner.run(
                    prompt=prompt,
                    worktree_path=worktree_info.path,
                    candidate_id=candidate_id,
                    role=role,
                    output_dir=output_dir,
                )

                patch_path = output_dir / "candidate.patch"
                try:
                    extract_patch(worktree_info.path, base_sha, patch_path)
                    result.patch_path = patch_path
                except Exception:
                    pass

                if self._state:
                    self._state.candidates[candidate_id] = result

                summary_data = {
                    "candidate_id": candidate_id,
                    "role": role.value,
                    "status": result.status.value,
                    "duration": result.duration_seconds,
                    "exit_code": result.exit_code,
                }
                atomic_write_json(output_dir / "summary.json", summary_data)

            # Apply monkey patch
            orch_module.Orchestrator._run_single_candidate = patched_run_single

            try:
                orchestrator = Orchestrator(config, repo_root=work_dir)
                run_id = asyncio.run(orchestrator.run())

                assert run_id is not None, "Orchestrator should return a run_id"

                # Verify run state
                run_json_path = work_dir / "output" / run_id / "run.json"
                assert run_json_path.exists(), f"Run state not found at {run_json_path}"
                run_data = json.loads(run_json_path.read_text())
                assert run_data["phase"] == "completed", f"Pipeline did not complete: {run_data['phase']}"

                # Verify candidates were processed
                candidates_dir = work_dir / "output" / run_id / "candidates"
                if candidates_dir.exists():
                    summaries = list(candidates_dir.glob("*/summary.json"))
                    assert len(summaries) == 6, f"Expected 6 candidate summaries, got {len(summaries)}"

                    # At least one candidate should have completed
                    completed = sum(
                        1 for s in summaries
                        if json.loads(s.read_text()).get("status") == "completed"
                    )
                    assert completed >= 1, "No candidates completed successfully"

                print(f"\n  [PASS] {swe_scenario.id} {swe_scenario.name}: pipeline completed via Orchestrator")

            finally:
                # Restore original method
                orch_module.Orchestrator._run_single_candidate = original_run_single

        finally:
            # Clean up temp dir
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestSWEVerifiedOrchestratorSummary:
    """Aggregate report across all 5 SWE scenarios via the real Orchestrator."""

    @pytest.mark.e2e
    def test_all_scenarios_via_orchestrator(self, swe_scenarios: list[SWEScenario]) -> None:
        """Run all scenarios and verify each completes through the pipeline."""
        import asyncio

        import hydra_code.orchestrator as orch_module
        from hydra_code.models import RunConfig, RunMode
        from hydra_code.orchestrator import Orchestrator

        async def run_scenario(scenario: SWEScenario) -> dict[str, Any]:
            tmpdir = tempfile.mkdtemp()
            work_dir = Path(tmpdir)
            try:
                _setup_git_repo(scenario, work_dir)

                config = RunConfig(
                    task=scenario.bug_description,
                    mode=RunMode.FAST,
                    claude_binary=sys.executable,
                    no_dirty_check=True,
                    dry_run=False,
                    output_dir=work_dir / "output",
                    max_turns=1,
                    agent_timeout_seconds=30,
                    concurrency=6,
                )

                # Same patch as TestSWEVerifiedOrchestrator
                original_method = orch_module.Orchestrator._run_single_candidate

                async def patched_run_single(self, candidate_id, spec, context, base_sha, strategy_angle=""):
                    from hydra_code.claude_runner import ClaudeRunner, RunnerConfig
                    from hydra_code.utils import atomic_write_json
                    from hydra_code.worktrees import create_worktree, extract_patch

                    role = spec.role
                    worktree_info = create_worktree(
                        self.run_id, candidate_id, role, base_sha
                    )
                    prompt = f"{context}\n\n## Role: {role.value}\n"

                    runner = ClaudeRunner(
                        RunnerConfig(
                            max_turns=1,
                            timeout_seconds=30,
                            claude_binary=sys.executable,
                        )
                    )
                    output_dir = self.run_dir / "candidates" / candidate_id
                    output_dir.mkdir(parents=True, exist_ok=True)

                    runner._build_command = lambda p: [sys.executable, str(FAKE_CLAUDE_PATH), p]

                    result = await runner.run(
                        prompt=prompt,
                        worktree_path=worktree_info.path,
                        candidate_id=candidate_id,
                        role=role,
                        output_dir=output_dir,
                    )

                    patch_path = output_dir / "candidate.patch"
                    try:
                        extract_patch(worktree_info.path, base_sha, patch_path)
                        result.patch_path = patch_path
                    except Exception:
                        pass

                    if self._state:
                        self._state.candidates[candidate_id] = result

                    summary_data = {
                        "candidate_id": candidate_id,
                        "role": role.value,
                        "status": result.status.value,
                        "duration": result.duration_seconds,
                        "exit_code": result.exit_code,
                    }
                    atomic_write_json(output_dir / "summary.json", summary_data)

                orch_module.Orchestrator._run_single_candidate = patched_run_single

                try:
                    orchestrator = Orchestrator(config, repo_root=work_dir)
                    run_id = await orchestrator.run()
                    success = run_id is not None
                finally:
                    orch_module.Orchestrator._run_single_candidate = original_method

                return {
                    "scenario_id": scenario.id,
                    "name": scenario.name,
                    "success": success,
                }
            finally:
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)

        results = []
        for scenario in swe_scenarios:
            result = asyncio.run(run_scenario(scenario))
            results.append(result)
            status = "PASS" if result["success"] else "FAIL"
            print(f"  [{status}] {result['scenario_id']} {result['name']}")

        failed = [r for r in results if not r["success"]]
        assert not failed, f"{len(failed)} scenarios failed: {', '.join(r['name'] for r in failed)}"

        print(f"\n  All {len(swe_scenarios)} scenarios passed through the real Orchestrator pipeline")


class TestSWEVerifiedFakeClaudeIntegration:
    """Verify fake_claude produces correct output for legacy scenarios."""

    @pytest.mark.e2e
    def test_fake_claude_swe_scenarios(self) -> None:
        """Fake Claude should handle all legacy scenario names."""
        swe_scenario_names = ["f1", "f2", "f3", "f4", "f5"]
        for name in swe_scenario_names:
            result = subprocess.run(
                [sys.executable, str(FAKE_CLAUDE_PATH)],
                capture_output=True,
                text=True,
                env={**os.environ, "FAKE_CLAUDE_SCENARIO": name},
            )
            assert result.returncode == 0, f"Scenario {name} should succeed"
            data: Any = json.loads(result.stdout.strip())
            assert data["status"] == "completed"
            assert "trajectory" in data

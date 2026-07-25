"""Core data models for HydraCode-6."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class CandidateRole(StrEnum):
    """The six candidate strategies."""

    MINIMAL = "minimal"
    ROOT_CAUSE = "root-cause"
    TEST_DRIVEN = "test-driven"
    ARCHITECTURE = "architecture"
    ADVERSARIAL = "adversarial"
    ALTERNATIVE = "alternative"


class CandidateStatus(StrEnum):
    """Lifecycle status of a candidate."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    REJECTED = "rejected"
    SELECTED = "selected"


class RunPhase(StrEnum):
    """Orchestrator pipeline phase."""

    PREFLIGHT = "preflight"
    CONTEXT_PACKET = "context_packet"
    CANDIDATE_GENERATION = "candidate_generation"
    TRAJECTORY_SUMMARY = "trajectory_summary"
    TEST_HARVEST = "test_harvest"
    TEST_MATRIX = "test_matrix"
    EVALUATION = "evaluation"
    TOURNAMENT = "tournament"
    REFINEMENT = "refinement"
    FINAL_VALIDATION = "final_validation"
    REPORTING = "reporting"
    COMPLETED = "completed"
    FAILED = "failed"


class TestVerdict(StrEnum):
    """Result of a single test execution."""

    PASS = "pass"
    FAIL = "fail"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    FLAKY = "flaky"


class RefineMode(StrEnum):
    """Refinement strategy."""

    NONE = "none"
    STANDARD = "standard"
    DEEP = "deep"


class RunMode(StrEnum):
    """Overall run mode."""

    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"


@dataclass
class ScoreWeights:
    """Configurable weights for deterministic evidence scoring."""

    issue_specific_tests: float = 0.35
    regression_tests: float = 0.25
    build_lint_type: float = 0.15
    generated_edge_tests: float = 0.10
    scope_minimality: float = 0.10
    static_risk: float = 0.05

    def __post_init__(self) -> None:
        total = (
            self.issue_specific_tests
            + self.regression_tests
            + self.build_lint_type
            + self.generated_edge_tests
            + self.scope_minimality
            + self.static_risk
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Score weights must sum to 1.0, got {total}")


@dataclass
class CandidateSpec:
    """Specification for a single candidate (role + replica index)."""

    role: CandidateRole
    replica_index: int

    @property
    def id(self) -> str:
        """Unique identifier, e.g. 'minimal-0', 'root_cause-2'."""
        role_key = self.role.value.replace("-", "_")
        if self.replica_index == 0:
            return role_key
        return f"{role_key}_{self.replica_index}"


STRATEGY_ANGLES = [
    "Focus on the minimal data-flow changes required.",
    "Start from the failing test and trace back to root cause.",
    "Consider the broader architectural impact before editing.",
    "Look for edge cases and assumptions other approaches might miss.",
    "Explore an alternative solution strategy rather than the obvious fix.",
]


@dataclass
class RunConfig:
    """Configuration for a HydraCode run."""

    task: str
    task_file: Path | None = None
    mode: RunMode = RunMode.STANDARD
    concurrency: int = 6
    num_candidates: int = 6
    single_agent: bool = False
    base_ref: str = "HEAD"
    max_turns: int = 25
    agent_timeout_seconds: int = 600
    test_timeout_seconds: int = 120
    keep_worktrees: bool = False
    output_dir: Path | None = None
    dry_run: bool = False
    no_refine: bool = False
    no_generated_tests: bool = False
    no_dirty_check: bool = False
    claude_binary: str | None = None
    score_weights: ScoreWeights = field(default_factory=ScoreWeights)
    refine_mode: RefineMode = RefineMode.STANDARD
    max_retries: int = 3
    retry_base_delay: float = 2.0
    retry_max_delay: float = 60.0
    gpu_monitor_url: str = "http://127.0.0.1:8000/metrics"
    enable_gpu_scaling: bool = True
    use_local_api: bool = False
    max_tokens: int = 8192

    @classmethod
    def from_task_file(cls, task_file: Path, **kwargs: Any) -> RunConfig:
        """Load task from a file and create config."""
        return cls(task=task_file.read_text(), task_file=task_file, **kwargs)


@dataclass
class TrajectorySummary:
    """Structured summary returned by each candidate worker."""

    candidate_id: str
    completion_status: str
    task_interpretation: str
    root_cause_hypotheses: list[str] = field(default_factory=list)
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    relevant_files: list[str] = field(default_factory=list)
    relevant_symbols: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    commands_executed: list[str] = field(default_factory=list)
    tests_run: list[str] = field(default_factory=list)
    test_results: list[str] = field(default_factory=list)
    remaining_failures: list[str] = field(default_factory=list)
    generated_tests: list[str] = field(default_factory=list)
    diff_stats: dict[str, int] = field(default_factory=dict)
    known_risks: list[str] = field(default_factory=list)
    useful_discoveries: list[str] = field(default_factory=list)
    failed_approaches: list[str] = field(default_factory=list)
    recommended_next_step: str = ""
    self_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "candidate_id": self.candidate_id,
            "completion_status": self.completion_status,
            "task_interpretation": self.task_interpretation,
            "root_cause_hypotheses": self.root_cause_hypotheses,
            "evidence_for": self.evidence_for,
            "evidence_against": self.evidence_against,
            "relevant_files": self.relevant_files,
            "relevant_symbols": self.relevant_symbols,
            "changes": self.changes,
            "commands_executed": self.commands_executed,
            "tests_run": self.tests_run,
            "test_results": self.test_results,
            "remaining_failures": self.remaining_failures,
            "generated_tests": self.generated_tests,
            "diff_stats": self.diff_stats,
            "known_risks": self.known_risks,
            "useful_discoveries": self.useful_discoveries,
            "failed_approaches": self.failed_approaches,
            "recommended_next_step": self.recommended_next_step,
            "self_confidence": self.self_confidence,
        }


@dataclass
class CandidateResult:
    """Result of running one candidate worker."""

    candidate_id: str
    role: CandidateRole
    status: CandidateStatus
    worktree_path: Path
    duration_seconds: float = 0.0
    exit_code: int | None = None
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    trajectory: TrajectorySummary | None = None
    patch_path: Path | None = None
    error: str | None = None


@dataclass
class TestResult:
    """Result of running one test against one candidate."""

    candidate_id: str
    test_id: str
    command: str
    exit_code: int
    duration_seconds: float
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    verdict: TestVerdict = TestVerdict.PASS

    @property
    def passed(self) -> bool:
        """Whether the test passed."""
        return self.verdict == TestVerdict.PASS


@dataclass
class TestMatrixEntry:
    """One cell in the candidate-test matrix."""

    candidate_id: str
    test_id: str
    results: list[TestResult] = field(default_factory=list)
    verdict: TestVerdict = TestVerdict.FAIL


@dataclass
class TestMatrix:
    """Full candidate-test evaluation matrix."""

    candidates: dict[str, str] = field(default_factory=dict)
    tests: dict[str, str] = field(default_factory=dict)
    results: list[TestMatrixEntry] = field(default_factory=list)


@dataclass
class HardGateResult:
    """Result of hard gate checks for a candidate."""

    candidate_id: str
    passed: bool
    rejection_reasons: list[str] = field(default_factory=list)


@dataclass
class CandidateScore:
    """Evidence-based score for a candidate."""

    candidate_id: str
    total_score: float = 0.0
    issue_specific_score: float = 0.0
    regression_score: float = 0.0
    build_lint_score: float = 0.0
    edge_test_score: float = 0.0
    minimality_score: float = 0.0
    static_risk_score: float = 0.0
    hard_gate_passed: bool = True
    hard_gate_reasons: list[str] = field(default_factory=list)


@dataclass
class JudgeResult:
    """Structured result from a tournament judge."""

    judge_id: str
    ranking: list[str] = field(default_factory=list)
    winner: str = ""
    acceptance_criteria_assessment: dict[str, str] = field(default_factory=dict)
    critical_risks: list[str] = field(default_factory=list)
    decisive_evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    status: str = "verdict"

    @property
    def is_insufficient(self) -> bool:
        """Whether the judge found insufficient evidence."""
        return self.status == "insufficient_evidence"


@dataclass
class TournamentResult:
    """Result of tournament voting for a group."""

    group_id: str
    candidates: list[str]
    judge_results: list[JudgeResult] = field(default_factory=list)
    winner: str = ""
    vote_counts: dict[str, int] = field(default_factory=dict)
    is_tie: bool = False
    needs_distinguishing_test: bool = False
    tie_breaker: str = ""
    distinguishing_test: str = ""


@dataclass
class RefinementPacket:
    """Distilled packet sent to refiner candidates."""

    parent_candidate_id: str
    useful_discoveries: list[str] = field(default_factory=list)
    failed_approaches: list[str] = field(default_factory=list)
    test_matrix_summary: dict[str, str] = field(default_factory=dict)
    tournament_feedback: list[str] = field(default_factory=list)
    remaining_uncertainty: list[str] = field(default_factory=list)
    relevant_summaries: list[str] = field(default_factory=list)


@dataclass
class RunState:
    """Persistent state for a HydraCode run."""

    run_id: str
    phase: RunPhase
    config: RunConfig
    repo_root: Path
    base_sha: str
    branch: str
    candidates: dict[str, CandidateResult] = field(default_factory=dict)
    test_matrix: TestMatrix | None = None
    scores: dict[str, CandidateScore] = field(default_factory=dict)
    hard_gates: dict[str, HardGateResult] = field(default_factory=dict)
    tournament_results: list[TournamentResult] = field(default_factory=list)
    final_candidate: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None

# Build HydraCode-6: Parallel Test-Time Scaling for Claude Code

You are implementing a production-ready local agentic-coding orchestrator called **HydraCode-6**.

The system must use multiple concurrent Claude Code sessions backed by my existing locally served Qwen model.

## Existing environment

* LLM server: vLLM
* OpenAI-compatible endpoint: `http://127.0.0.1:8000/v1`
* Served model ID: `qwen`
* Effective model-call concurrency: 6
* Claude Code is already configured to use this local model through my existing bridge or proxy.
* Do not replace or redesign the vLLM server configuration.
* Use the existing `claude` CLI configuration when spawning Claude Code sessions.
* Target operating system: Linux.
* Target runtime: Python 3.11 or newer.
* The implementation must work inside an arbitrary Git repository.

## Goal

Build a reusable system that improves a local 27B coding model through:

1. Six independent coding-agent rollouts.
2. Isolated Git worktrees.
3. Structured trajectory summaries.
4. Candidate-independent generated tests.
5. Deterministic candidate evaluation.
6. Recursive Tournament Voting.
7. Parallel-Distill-Refine.
8. Final regression verification.
9. Detailed metrics and an auditable report.

The system must be invocable from Claude Code as:

```text
/hydra-code <task>
```

It must also be invocable directly:

```bash
hydra-code run "<task>"
```

## Non-negotiable constraints

* Never let candidate agents edit the main checkout.
* Every editing agent must operate in a separate Git worktree.
* Run at most six primary Claude Code sessions concurrently by default.
* Do not select candidates using self-reported confidence.
* Deterministic test failures override LLM judgments.
* Do not allow agents to disable or weaken existing tests.
* Preserve all candidate diffs, summaries, logs and test outputs.
* Never automatically merge a candidate that fails required validation.
* Use structured JSON Schema output wherever Claude Code supports it.
* Add timeouts, retries and clear error reporting.
* Keep the implementation modular and fully type annotated.
* Add unit and integration tests for the orchestrator.
* Do not ask me implementation questions unless an unavoidable external dependency is missing. Inspect the environment and make reasonable choices.

## Recommended project structure

Create:

```text
hydra-code/
├── pyproject.toml
├── README.md
├── src/
│   └── hydra_code/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── models.py
│       ├── orchestrator.py
│       ├── scheduler.py
│       ├── claude_runner.py
│       ├── worktrees.py
│       ├── context_packet.py
│       ├── trajectory.py
│       ├── test_harvester.py
│       ├── evaluator.py
│       ├── tournament.py
│       ├── refinement.py
│       ├── metrics.py
│       ├── reporting.py
│       └── utils.py
├── prompts/
│   ├── candidate_minimal.md
│   ├── candidate_root_cause.md
│   ├── candidate_test_driven.md
│   ├── candidate_architecture.md
│   ├── candidate_adversarial.md
│   ├── candidate_alternative.md
│   ├── summarize_trajectory.md
│   ├── generate_tests.md
│   ├── tournament_judge.md
│   ├── refine_candidate.md
│   └── final_review.md
├── schemas/
│   ├── trajectory_summary.json
│   ├── generated_test.json
│   ├── judge_result.json
│   └── final_report.json
├── tests/
│   ├── test_scheduler.py
│   ├── test_worktrees.py
│   ├── test_trajectory_schema.py
│   ├── test_evaluator.py
│   ├── test_tournament.py
│   └── integration/
└── .claude/
    └── skills/
        └── hydra-code/
            └── SKILL.md
```

Adjust the structure only when there is a concrete technical reason.

## CLI requirements

Implement:

```bash
hydra-code run "<task>"
hydra-code run --task-file task.md
hydra-code resume <run-id>
hydra-code status <run-id>
hydra-code report <run-id>
hydra-code clean <run-id>
hydra-code benchmark benchmark.yaml
```

Important options:

```text
--mode fast|standard|deep
--concurrency 6
--base-ref HEAD
--max-turns
--agent-timeout-seconds
--test-timeout-seconds
--keep-worktrees
--output-dir
--dry-run
--no-refine
--no-generated-tests
```

## Run directory

Store every run under:

```text
.hydra/runs/<timestamp>-<short-id>/
```

Include:

```text
run.json
task.md
context-packet.md
baseline/
candidates/<candidate-id>/
summaries/
tests/
test-matrix.json
tournament/
refinement/
metrics/
final/
report.md
```

Use atomic writes for state files so interrupted runs remain resumable.

## Preflight

Implement a preflight stage that:

1. Confirms `git` and `claude` exist.
2. Confirms the current directory is in a Git repository.
3. Records repository root, current SHA and branch.
4. Detects dirty files.
5. Refuses to lose uncommitted changes.
6. Detects likely test, lint, format and type-check commands.
7. Reads repository instructions such as `CLAUDE.md`.
8. Executes a configurable lightweight baseline test.
9. Records the output and exit status.
10. Creates the run manifest.

Support dirty repositories by either:

* Refusing with a clear message, or
* Creating a temporary snapshot commit only when the user explicitly enables it.

Do not silently stash or discard work.

## Context packet

Create one deterministic context packet shared by all workers.

It must contain:

* User task exactly as supplied.
* Derived acceptance criteria.
* Repository root and base SHA.
* Repository structure summary.
* Detected language and build tools.
* Test commands.
* Relevant repository instructions.
* Baseline results.
* Explicit constraints.
* Expected worker output contract.

Keep the common packet identical and place it before role-specific instructions to improve vLLM prefix-cache reuse.

## Worktrees

Create worktrees under:

```text
.hydra/worktrees/<run-id>/<candidate-id>/
```

Create branches similar to:

```text
hydra/<run-id>/<candidate-id>
```

Implement safe creation, locking, inspection and cleanup.

A worktree with changes must not be deleted unless:

* Its patch has been persisted, and
* The user requested cleanup, or
* The final report confirms it is safe.

## Claude Code runner

Use `asyncio.create_subprocess_exec` to launch `claude -p`.

Prefer a command shaped like:

```bash
claude -p \
  --output-format json \
  --permission-mode acceptEdits \
  --max-turns <configured-value> \
  --no-session-persistence \
  "<prompt>"
```

Where supported, use `--json-schema` for structured final results.

Requirements:

* Run each process with its candidate worktree as `cwd`.
* Inherit the existing environment so the current local-model bridge continues to work.
* Capture stdout and stderr separately.
* Stream logs to disk.
* Enforce per-agent timeouts.
* Terminate the process group safely on timeout.
* Retry only retryable transport or server failures.
* Do not retry deterministic coding failures from scratch without recording them.
* Record exit code, duration and output.
* Redact likely secrets from reports.

Implement a concurrency scheduler with an `asyncio.Semaphore`.

Default:

```python
MAX_CONCURRENT_CLAUDE_SESSIONS = 6
```

## Initial candidates

Launch these six candidates concurrently:

1. `minimal`

   * Prefer the smallest correct patch.
   * Avoid unrelated refactoring.
   * Trace only enough code to justify the fix.

2. `root-cause`

   * Trace data flow, control flow and relevant dependencies.
   * Establish a clear root cause before editing.

3. `test-driven`

   * Reproduce the failure first.
   * Write or identify a failing test before the production change.

4. `architecture`

   * Examine public APIs, module boundaries and compatibility.
   * Consider cross-module implications.

5. `adversarial`

   * Search for edge cases, hidden regressions, concurrency issues and invalid assumptions.
   * Attempt to falsify the obvious fix.

6. `alternative`

   * Deliberately challenge the most obvious localization.
   * Explore a meaningfully different solution strategy.

All six must receive the same context packet followed by their role-specific instructions.

Each candidate must:

* Investigate the repository.
* Implement a candidate fix.
* Add useful tests when appropriate.
* Run targeted validation.
* Leave changes in its own worktree.
* Return a structured trajectory summary.
* Never inspect another candidate worktree.

## Trajectory summary

Implement and validate this information:

```text
candidate ID
completion status
task interpretation
root-cause hypotheses
evidence for and against each hypothesis
relevant files and symbols
changes and purpose
commands executed
tests and results
remaining failures
generated tests
diff statistics
known risks
useful discoveries
failed approaches to avoid
recommended next step
self-confidence
```

Self-confidence is for diagnostics only and must not be used as the main ranking score.

If a worker returns invalid JSON:

1. Preserve its raw output.
2. Attempt one schema-repair call.
3. Mark fields unknown when they cannot be recovered.
4. Do not invent missing evidence.

## Test harvesting

Collect:

* Existing tests run by workers.
* Worker-created reproduction tests.
* Worker-created edge tests.
* Build commands.
* Lint and type-check commands.

Validate generated reproduction tests against the base revision.

A bug-reproduction test should normally:

```text
fail on base
pass on a correct candidate
```

Reject tests that are:

* Candidate-specific.
* Nondeterministic.
* Unrelated to the task.
* Passing on base when claimed as reproduction tests.
* Dependent on weakened assertions.
* Modifying production code as part of test setup.

Deduplicate semantically equivalent tests.

## Candidate test matrix

Run each accepted test against each surviving candidate.

Store:

```json
{
  "candidates": {},
  "tests": {},
  "results": []
}
```

Every result should include:

```text
candidate ID
test ID
command
exit code
duration
stdout path
stderr path
pass/fail/timeout
```

Limit CPU-heavy test concurrency separately from model concurrency.

Do not launch six full repository test suites simultaneously unless explicitly configured.

## Hard rejection gates

Reject a candidate when:

* Its patch cannot be extracted or applied.
* Required build fails.
* The issue reproduction remains failing.
* It breaks previously passing targeted regression tests.
* It modifies forbidden files.
* It disables, deletes or weakens tests without justification.
* It contains obvious test-specific hard coding.
* It leaves the repository in an invalid state.

Record the exact rejection reason.

## Deterministic scoring

Implement a configurable evidence score.

Default weights:

```text
issue-specific tests: 0.35
regression tests:     0.25
build/lint/type:      0.15
generated edge tests: 0.10
scope/minimality:     0.10
static risk:          0.05
```

Do not allow a weighted score to bypass hard gates.

## Recursive Tournament Voting

Implement small-group tournament selection.

For six candidates:

```text
group A = candidates 1–3
group B = candidates 4–6
```

Run three independent judge calls per group.

Each judge receives:

* Task.
* Acceptance criteria.
* Structured summaries.
* Candidate diffs.
* Test matrix.
* Important logs.
* Known risks.

Each judge must return structured JSON containing:

```text
ranking
winner
acceptance-criterion assessment
critical risks
decisive evidence
confidence
```

Choose each group winner by majority vote.

Compare the two group winners with three final judges.

Rules:

* Tests override rhetoric.
* Judges must cite evidence from supplied artifacts.
* A judge may return `insufficient_evidence`.
* When the vote is tied or uncertain, generate a distinguishing test instead of adding unlimited generic judges.

## Refinement

In standard mode:

* Refine the selected winner once.

In deep mode:

* Keep the top two candidates.
* Create two refinement branches from each candidate.
* Launch:

  * Two independent refiners for candidate A.
  * Two independent refiners for candidate B.
  * One adversarial test generator.
  * One compatibility and regression reviewer.

Provide refiners with a distilled packet containing:

* Useful discoveries from all initial candidates.
* Failed approaches to avoid.
* Test matrix.
* Tournament feedback.
* Remaining uncertainty.
* Relevant summaries.

Do not expose irrelevant raw transcripts.

Re-run the evaluation pipeline on refined candidates.

## Adaptive escalation

Implement an uncertainty score based on:

* Judge disagreement.
* Root-cause disagreement.
* Relevant-file disagreement.
* Test-result disagreement.
* Small score gap between top candidates.
* Missing issue-specific tests.
* Unresolved acceptance criteria.

Use the uncertainty score to decide whether to:

* Stop after deterministic selection.
* Run one refinement.
* Run full top-two refinement.
* Generate distinguishing tests.

Make thresholds configurable and record the decision.

## Final validation

The final candidate must pass:

* Required issue-specific tests.
* Accepted generated tests.
* Relevant regression tests.
* Build.
* Lint and type checks when configured.
* Final diff review.

Perform a final static inspection for:

* Disabled tests.
* Debug statements.
* Temporary files.
* Secrets.
* Unrelated changes.
* Formatting churn.
* Hard-coded visible-test answers.

Persist:

```text
final.patch
final.diff
final-summary.json
validation.json
report.md
```

Do not automatically change the main checkout by default.

Provide an explicit command for applying the final result:

```bash
git apply <path-to-final.patch>
```

Optionally support:

```bash
hydra-code apply <run-id>
```

The apply command must verify that the current repository still matches the expected base or that the patch applies cleanly.

## Claude Code skill

Create:

```text
.claude/skills/hydra-code/SKILL.md
```

Use frontmatter similar to:

```yaml
---
name: hydra-code
description: Runs a parallel, test-time-scaled coding workflow using isolated Claude Code sessions, generated tests, tournament selection and refinement.
argument-hint: "<coding task>"
disable-model-invocation: true
allowed-tools: Bash
---
```

The skill should:

1. Validate that arguments were supplied.
2. Invoke the installed `hydra-code` CLI with `$ARGUMENTS`.
3. Stream meaningful progress.
4. Present the final report path.
5. Never implement the requested code directly in the main session when the Hydra workflow is active.

## Metrics

Poll the local vLLM `/metrics` endpoint when available.

Capture:

* Running requests.
* Waiting requests.
* KV-cache usage.
* Prefix-cache queries and hits.
* Prompt-token throughput.
* Generation-token throughput.
* Preemptions.
* Total wall time.
* Per-agent duration.
* Claude Code process failures.

The metrics parser must tolerate missing or version-specific metrics.

Also calculate:

* Oracle pass@k.
* Final selected pass@1.
* Selector regret.
* Candidate file-overlap similarity.
* Candidate diff similarity.
* Root-cause hypothesis similarity.
* Generated-test validity rate.
* Time spent in generation versus testing when observable.

## Benchmark support

Create a YAML benchmark format supporting multiple local tasks:

```yaml
tasks:
  - id: task-001
    repo: /path/to/repo
    task: |
      Fix ...
    base_ref: abc123
    verification:
      - pytest tests/test_x.py
```

Support running these configurations:

```text
single
parallel-test-only
parallel-plus-generated-tests
parallel-plus-rtv
parallel-plus-rtv-plus-refinement
adaptive
```

Generate CSV and Markdown comparisons.

## Testing requirements

Unit-test:

* Semaphore concurrency.
* Timeouts.
* Retry classification.
* Worktree lifecycle.
* Dirty-repository protection.
* JSON Schema validation.
* Test harvesting and rejection.
* Hard candidate gates.
* Evidence scoring.
* Tournament majority voting.
* Ties and insufficient evidence.
* Run-state persistence and resume.
* Metrics parsing.
* Secret redaction.

Integration-test with a small fixture repository containing:

* A known bug.
* A failing reproduction test.
* Two plausible patches, only one of which handles an edge case.
* A regression test that catches the incorrect patch.

The integration test must prove that the selector chooses the correct patch.

Mock the Claude CLI for normal automated tests. Make real Claude Code integration tests opt-in.

## Operational quality

* Use `ruff` and `mypy`.
* Use `pytest`.
* Use structured logging.
* Include useful docstrings.
* Avoid global mutable state.
* Use dataclasses or Pydantic models for persistent records.
* Use atomic JSON writes.
* Make interrupted runs resumable.
* Include graceful SIGINT and SIGTERM handling.
* Do not leave orphan Claude processes.
* Do not delete worktrees containing unpersisted changes.
* Include actionable error messages.

## README

Document:

* Architecture.
* Prerequisites.
* Installation.
* Claude Code skill installation.
* Configuration.
* Commands.
* Run lifecycle.
* Safety properties.
* How candidate selection works.
* How to inspect all candidate worktrees.
* How to resume interrupted runs.
* How to apply the final patch.
* How to benchmark.
* How to interpret selector regret and diversity metrics.
* Known limitations of homogeneous same-model agents.

## Implementation sequence

Implement in this order:

1. Project scaffold and typed data models.
2. CLI and run-state persistence.
3. Git worktree management.
4. Claude Code subprocess runner.
5. Six-worker asynchronous scheduler.
6. Context packet and prompt loading.
7. Trajectory summary validation.
8. Patch and test harvesting.
9. Candidate test matrix.
10. Hard gates and deterministic scoring.
11. Tournament selection.
12. Refinement.
13. Metrics.
14. Claude Code skill.
15. Unit and integration tests.
16. Documentation.
17. End-to-end fixture demonstration.

After every major stage:

* Run tests.
* Fix failures before continuing.
* Commit the working stage with a descriptive Git commit.

## Final acceptance criteria

The project is complete only when:

* `/hydra-code <task>` starts the workflow.
* Six isolated Claude Code sessions can run concurrently.
* No candidate edits the main checkout.
* Candidate results survive process interruption.
* Summaries conform to schemas.
* Generated tests are validated against the base revision.
* Every candidate is evaluated against a common test matrix.
* Hard failures cannot be overridden by an LLM judge.
* Tournament selection is evidence grounded.
* Deep mode performs top-two refinement.
* A final patch and auditable report are produced.
* The fixture integration test selects the correct candidate.
* The full unit-test suite, lint and type checking pass.

Begin by inspecting the current environment and repository. Then create an implementation plan in `IMPLEMENTATION_PLAN.md` and immediately execute it. Do not stop after writing the plan.


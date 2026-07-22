# Execution Inputs and Non-Negotiable Delivery Protocol

Before implementing HydraCode-6, inspect the complete `hydra-handoff/` directory.

Do not infer environment capabilities from documentation alone. Run the supplied compatibility probes and record the actual results.

## Sources of truth, in order

1. `REQUIREMENTS.md`
2. `DECISIONS.md`
3. `ACCEPTANCE_CRITERIA.md`
4. Compatibility-probe results
5. Fixture verification files
6. Existing implementation and tests
7. This prompt

When two instructions conflict, follow the higher source and record the conflict in `KNOWN_ISSUES.md`.

## Mandatory initial actions

1. Read every top-level handoff document.
2. Inspect the environment evidence.
3. Run all compatibility probes.
4. Confirm the installed Claude Code flags against `claude-help.txt`.
5. Confirm the local model ID is `qwen`.
6. Confirm the server is reachable at `http://127.0.0.1:8000/v1`.
7. Confirm one Claude Code editing smoke test works.
8. Confirm six concurrent read-only Claude Code sessions work.
9. Record results in `COMPATIBILITY_REPORT.md`.
10. Stop implementation and report a blocker only when a mandatory capability truly fails.

Do not begin orchestration implementation while required compatibility probes are failing.

## Frozen architecture

Implement a Python external orchestrator invoked through a manually triggered Claude Code `/hydra-code` skill.

Claude Code sessions are editing workers. The orchestrator owns:

* Concurrency.
* Worktrees.
* Persistent state.
* Test execution.
* Candidate evaluation.
* Tournament selection.
* Refinement.
* Metrics.
* Reporting.

Do not replace this architecture with native agent teams, MCP orchestration, Qwen-Agent, a web application, a distributed queue, or a different coding harness during version 1.

Native Claude Code features may be added later behind adapters after the required version-1 workflow passes all acceptance tests.

## Exact-base requirement

Record the repository base SHA before the run.

Every candidate worktree must be created explicitly from that SHA.

Never assume the default branch equals the requested base revision.

Never allow candidate workers to edit the main checkout.

## Development method

Implement one milestone at a time.

For every milestone:

1. Write or update tests first where practical.
2. Implement the smallest complete behavior.
3. Run the milestone tests.
4. Run all prior tests.
5. Run Ruff and mypy.
6. Inspect the Git diff.
7. Update `CURRENT_STATUS.md`.
8. Update `TEST_RESULTS.md`.
9. Update `NEXT_ACTION.md`.
10. Create a descriptive checkpoint commit.

Do not continue with known unexplained failures.

Do not disable, skip, weaken or delete tests to make a milestone pass.

## Completion discipline

Do not stop after:

* Writing a plan.
* Creating interfaces without implementations.
* Adding TODO placeholders.
* Building only the happy path.
* Passing only mocked tests.
* Running one candidate.
* Producing a candidate without selection.
* Producing selection without trusted verification.
* Producing the final patch without a report.

The implementation is complete only when all mandatory deterministic tests, fixture tests, failure-injection tests, and required real-Qwen tests pass.

## Handling context loss

At the beginning of every continuation or resumed session, read:

1. `REQUIREMENTS.md`
2. `DECISIONS.md`
3. `ACCEPTANCE_CRITERIA.md`
4. `CURRENT_STATUS.md`
5. `TEST_RESULTS.md`
6. `KNOWN_ISSUES.md`
7. `NEXT_ACTION.md`
8. `git status`
9. `git log -10 --oneline`

Resume from `NEXT_ACTION.md`.

Do not recreate completed components unless current tests prove they are defective.

## Handling uncertainty

When uncertain about an implementation detail:

1. Inspect the installed CLI help and existing code.
2. Write a minimal isolated probe.
3. Execute the probe.
4. Record the result.
5. Make the smallest evidence-based decision.
6. Update `DECISIONS.md` when the decision affects architecture or compatibility.

Do not resolve uncertainty through speculative redesign.

## Reporting blockers

A blocker report must contain:

* Exact failing command.
* Exit code.
* Relevant redacted output.
* Expected behavior.
* Actual behavior.
* Files involved.
* What was attempted.
* Whether other milestones can continue safely.
* Smallest action needed from the user.

Do not use “cannot proceed” when a safe independent milestone remains implementable.

## Final deliverables

Produce all of the following:

* Installable Python package.
* `hydra-code` executable.
* Claude Code `/hydra-code` skill.
* Typed configuration.
* Six-worker asynchronous scheduler.
* Exact-SHA Git worktrees.
* Persistent resumable run state.
* Candidate summaries.
* Common candidate-test matrix.
* Hard rejection gates.
* Recursive tournament selection.
* Refinement workflow.
* vLLM metrics collection.
* Unit tests.
* Mocked integration tests.
* Deterministic fixture repositories.
* Failure-injection tests.
* Real local-Qwen smoke and concurrency tests.
* Ablation benchmark.
* Final validation report.
* Installation and operations documentation.

At completion, run the complete validation suite and provide:

```text
git status
git log --oneline --decorate -20
pytest summary
coverage summary
ruff result
mypy result
fixture results
real-Qwen test results
single-versus-six throughput results
selector regret
known limitations
exact command to run /hydra-code
```

Do not apply a generated candidate patch to the main checkout automatically.


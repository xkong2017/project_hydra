# Testing and Validation Plan for HydraCode-6

The workflow is not complete until it passes a layered validation suite covering:

1. Orchestrator correctness.
2. Git and worktree safety.
3. Agent-process reliability.
4. Candidate diversity.
5. Generated-test quality.
6. Candidate-selection accuracy.
7. Refinement effectiveness.
8. Recovery from failures.
9. GPU utilization and concurrency.
10. Measurable improvement over a single Claude Code session.

Do not rely only on mocked unit tests. Implement four validation levels:

```text
Level 1: Unit tests with no LLM
Level 2: Deterministic integration tests with mocked agents
Level 3: End-to-end tests with a fake or stub LLM server
Level 4: Real end-to-end tests using Qwen on port 8000
```

---

## 1. Test infrastructure

Create:

```text
tests/
├── unit/
│   ├── test_scheduler.py
│   ├── test_agent_runner.py
│   ├── test_worktrees.py
│   ├── test_run_state.py
│   ├── test_context_packet.py
│   ├── test_schema_validation.py
│   ├── test_test_harvester.py
│   ├── test_candidate_gates.py
│   ├── test_scoring.py
│   ├── test_tournament.py
│   ├── test_refinement.py
│   ├── test_metrics.py
│   └── test_redaction.py
├── integration/
│   ├── test_parallel_rollouts.py
│   ├── test_candidate_test_matrix.py
│   ├── test_selector_accuracy.py
│   ├── test_resume.py
│   ├── test_failure_recovery.py
│   ├── test_worktree_isolation.py
│   └── test_full_mocked_workflow.py
├── e2e/
│   ├── test_real_qwen_smoke.py
│   ├── test_real_qwen_six_workers.py
│   ├── test_real_qwen_refinement.py
│   └── test_real_qwen_gpu_utilization.py
├── fixtures/
│   ├── pagination_bug/
│   ├── cache_isolation_bug/
│   ├── async_race_bug/
│   ├── parser_compatibility_bug/
│   ├── misleading_test_bug/
│   └── multi_file_api_bug/
└── fake_claude/
    ├── fake_claude.py
    ├── scenarios/
    └── fake_vllm_server.py
```

Use test markers:

```ini
[pytest]
markers =
    unit: no external processes or LLM calls
    integration: local subprocess and Git integration tests
    e2e: real Claude Code and local Qwen tests
    gpu: tests requiring the local vLLM server
    slow: tests that may take several minutes
    chaos: injected failure and recovery tests
```

Default continuous integration should run:

```bash
pytest -m "unit or integration"
```

Real local-model validation should run explicitly:

```bash
pytest -m "e2e and gpu" --run-real-llm
```

---

# 2. Unit tests

## TC-U01: Concurrency never exceeds configured limit

**Purpose:** Verify that the scheduler never runs more than six model-facing agent processes simultaneously.

**Setup:**

* Create 20 mock agent jobs.
* Each job records its start and completion times.
* Each job sleeps briefly to create overlap.
* Configure concurrency to six.

**Assertions:**

* Maximum simultaneous agents is exactly six.
* No seventh agent starts before a running slot is released.
* All 20 jobs eventually complete.
* No job is lost or executed twice.

---

## TC-U02: Scheduler keeps slots occupied

**Purpose:** Ensure work-conserving scheduling.

**Setup:**

* Submit six long jobs and six short jobs.
* Complete jobs in different orders.

**Assertions:**

* A waiting job starts immediately when a slot becomes available.
* The scheduler does not wait for the entire original wave to finish.
* Average idle time between jobs is below a small configured threshold.

This validates asynchronous scheduling instead of fixed synchronous batches.

---

## TC-U03: Priority handling

**Purpose:** Ensure critical final-verification work can be prioritized over optional exploration.

**Setup:**

* Fill the queue with low-priority candidate-generation jobs.
* Add a high-priority distinguishing-test job.

**Assertions:**

* The high-priority job runs in the next available slot.
* Already running jobs are not interrupted.
* Queue ordering remains deterministic.

---

## TC-U04: Process timeout handling

**Setup:**

* Run a mock Claude process that never exits.
* Configure a short timeout.

**Assertions:**

* The process receives a graceful termination signal.
* It is force-killed after the configured grace period if necessary.
* Child processes are also terminated.
* The candidate is marked `timeout`.
* Logs and partial output remain available.
* The scheduler slot is released.

---

## TC-U05: Retry classification

Test these failures:

| Failure                         |                   Retry |
| ------------------------------- | ----------------------: |
| HTTP 429 or capacity error      |                     Yes |
| Temporary connection reset      |                     Yes |
| vLLM HTTP 500 transport failure |       Yes, within limit |
| Invalid agent JSON              |      One repair attempt |
| Test failure in candidate code  |                      No |
| Git conflict                    | No automatic full retry |
| Permission denied               |                      No |
| Missing executable              |                      No |

Verify exponential backoff with jitter and a maximum retry limit.

---

## TC-U06: Atomic run-state persistence

**Setup:**

* Interrupt a state-file write halfway through.
* Simulate a process crash.

**Assertions:**

* The prior valid state file remains readable.
* No partially written JSON becomes the active run state.
* Restarting the run reconstructs the last valid phase.

---

## TC-U07: Schema validation and repair

Test:

* Valid trajectory JSON.
* Missing required field.
* Wrong field type.
* Extra prose before JSON.
* Truncated JSON.
* Markdown-fenced JSON.
* Hallucinated file paths.

**Assertions:**

* Valid JSON passes unchanged.
* Recoverable formatting is repaired.
* One schema-repair attempt is allowed.
* Missing evidence is marked `unknown`.
* The system never fabricates test results or file paths.

---

## TC-U08: Hard gates override scores

Create a candidate with:

* Excellent judge score.
* High self-confidence.
* Elegant implementation.
* One failing required reproduction test.

**Assertion:**

* Candidate is rejected regardless of its weighted or LLM score.

---

## TC-U09: Test weakening detection

Create diffs that:

* Delete an existing test.
* Replace a precise assertion with `assert True`.
* Increase an error tolerance unreasonably.
* Add `skip`, `xfail`, or test filtering.
* Mock away the behavior being tested.

**Assertions:**

* Suspicious changes are flagged.
* The candidate cannot pass a hard gate without explicit justification.
* The report includes the exact weakened test.

---

## TC-U10: Deterministic evidence scoring

Provide a fixed candidate-test matrix.

Verify:

* Scores match the configured formula.
* Hard-gate failures are represented separately.
* Missing tests do not count as passes.
* Timeout is not treated as pass.
* Weight configuration is validated to sum to one.

---

## TC-U11: Tournament majority voting

Test:

* Clear 3–0 winner.
* 2–1 winner.
* 1–1–1 tie.
* One invalid judge response.
* One `insufficient_evidence` response.
* Judges ranking candidates differently but selecting the same winner.

**Assertions:**

* A 2–1 winner advances.
* A 1–1–1 result triggers uncertainty handling.
* Invalid responses do not silently become votes.
* The original judge outputs remain auditable.

---

## TC-U12: Distinguishing-test escalation

Create two candidates that:

* Pass all existing tests.
* Have substantially different implementations.
* Receive tied tournament votes.

**Assertion:**

* The system requests a targeted distinguishing test.
* It does not choose based on diff size or confidence alone.
* After the test executes, selection is rerun with the new evidence.

---

## TC-U13: Secret redaction

Place fake secrets in:

* Environment variables.
* Agent stderr.
* Git diff.
* Test output.
* vLLM server response.

Use recognizable formats such as:

```text
sk-test-secret
ghp_fake_token
AWS_SECRET_ACCESS_KEY=fake
```

**Assertions:**

* Secrets are redacted in reports and console output.
* Raw protected logs are handled according to configuration.
* Redaction does not corrupt ordinary code strings.

---

# 3. Git and worktree safety tests

## TC-G01: Main checkout isolation

**Setup:**

* Record the main checkout status and file hashes.
* Run six editing candidates.

**Assertions:**

* Main checkout file hashes remain unchanged.
* All candidate changes appear only in their own worktrees.
* Candidate branches are distinct.
* No candidate can access another candidate’s uncommitted changes.

---

## TC-G02: Dirty repository protection

Test repositories with:

* Modified tracked files.
* Untracked files.
* Staged changes.
* An in-progress merge or rebase.

**Assertions:**

* The workflow refuses unsafe startup by default.
* No changes are silently stashed, reset, committed, or deleted.
* The user receives a precise error.

---

## TC-G03: Patch persistence before cleanup

**Setup:**

* Create a candidate with uncommitted changes.
* Request cleanup.

**Assertions:**

* Patch and diff are persisted before worktree removal.
* Cleanup fails safely if patch persistence fails.
* The candidate can be reconstructed from stored artifacts.

---

## TC-G04: Base revision drift

**Setup:**

* Complete a Hydra run.
* Change the main repository before applying the result.

**Assertions:**

* `hydra-code apply` detects base-SHA mismatch.
* It tests whether the patch still applies cleanly.
* It never force-applies a conflicting patch.
* It gives an actionable conflict report.

---

# 4. Deterministic integration fixture repositories

Each fixture must be small enough to test quickly but realistic enough to require reasoning.

---

## Fixture F1: Pagination boundary bug

### Repository behavior

A Python pagination function incorrectly drops the final item when the item count is exactly divisible by the page size.

Incorrect implementation:

```python
def page_count(total: int, page_size: int) -> int:
    return total // page_size + 1
```

Or use a related off-by-one defect in page slicing.

### Existing tests

* Non-divisible case passes.
* Empty input passes.
* Exact-boundary case is missing.

### Candidate possibilities

* Correct mathematical fix.
* Hard-coded special case for the visible example.
* Fix that breaks zero items.
* Broad unnecessary refactor.

### Required workflow behavior

* At least one worker should create the missing exact-boundary test.
* Generated test should fail on base and pass on the correct patch.
* Hard-coded patches should be rejected by additional parameterized tests.
* The smallest general patch should win.

### Acceptance criteria

```bash
pytest -q
ruff check .
mypy src
```

All must pass.

---

## Fixture F2: Multi-tenant cache isolation bug

### Repository behavior

A cache key uses only `document_id`:

```python
cache_key = document_id
```

It should also include `tenant_id`.

### Hidden danger

A visible test checks caching but not cross-tenant isolation.

### Candidate possibilities

* Clear the cache before each request.
* Disable caching.
* Include tenant ID correctly.
* Include user ID but still omit tenant.
* Add test-specific conditions.

### Required workflow behavior

* The adversarial worker should identify the data-isolation risk.
* A generated cross-tenant test should fail on base.
* A patch that disables caching should be penalized or rejected because it violates performance requirements.
* The correct composite key should win.

### Acceptance criteria

* No data is shared between tenants.
* Cache hits still occur within one tenant.
* Existing cache-performance test passes.

This fixture validates whether parallel agents discover a hidden correctness and security dimension.

---

## Fixture F3: Async race condition

### Repository behavior

An asynchronous in-memory counter performs:

```python
current = state[key]
await asyncio.sleep(0)
state[key] = current + 1
```

Concurrent calls lose updates.

### Candidate possibilities

* Add one global lock.
* Add a per-key lock.
* Remove the `await`.
* Retry writes.
* Serialize the entire service.

### Required workflow behavior

* Test-driven or adversarial workers should generate a concurrent reproduction test.
* The selector should distinguish correctness from unnecessarily poor concurrency.
* A per-key lock should be preferred when requirements specify independent keys should proceed concurrently.

### Required tests

1. Same-key concurrent increments produce the correct count.
2. Different keys can execute concurrently.
3. No deadlock occurs.
4. Cancellation does not leave the lock permanently held.

This fixture validates reasoning about both correctness and performance.

---

## Fixture F4: Parser backward-compatibility bug

### Repository behavior

A configuration parser accepts:

```json
{"timeout": 30}
```

A new version introduces:

```json
{"request_timeout_seconds": 30}
```

but accidentally breaks old configurations.

### Candidate possibilities

* Support both keys with precedence rules.
* Rename the key without compatibility.
* Silently ignore the old key.
* Support old key but produce incorrect serialization.

### Required workflow behavior

* Architecture worker should identify public-contract compatibility.
* Generated tests should cover:

  * Old key only.
  * New key only.
  * Both keys.
  * Invalid type.
  * Round-trip serialization.
* Selector should choose the candidate with explicit compatibility behavior.

---

## Fixture F5: Misleading visible test

### Repository behavior

A string-normalization function should remove surrounding whitespace and normalize repeated internal spaces.

Visible test:

```python
assert normalize("  hello  ") == "hello"
```

The intentionally incorrect candidate uses only `.strip()`.

Correct behavior also requires:

```python
normalize("hello     world") == "hello world"
```

### Required workflow behavior

* Multiple candidates should initially appear valid.
* Generated edge tests should distinguish `.strip()` from complete normalization.
* The selector must not choose based only on visible-test success.

This fixture directly validates candidate-independent test generation.

---

## Fixture F6: Multi-file API consistency bug

### Repository behavior

A function parameter is renamed in the implementation but not in:

* Interface definition.
* Mock implementation.
* CLI adapter.
* Documentation example.
* Serialization layer.

### Candidate possibilities

* Change only the implementation.
* Update all callers.
* Add a compatibility adapter.
* Perform an excessive repository-wide rename.

### Required workflow behavior

* Root-cause and architecture agents should discover the full dependency path.
* Partial fixes should fail integration tests.
* The selector should prefer the complete compatible patch.
* Diff minimality must not favor an incomplete one-file patch.

---

# 5. End-to-end workflow scenarios

## TC-E01: All agents converge

Use a simple fixture where all six workers are likely to produce semantically equivalent fixes.

**Expected behavior:**

* Candidate similarity is high.
* Tests pass for several candidates.
* Tournament agreement is high.
* The workflow stops without a full refinement wave.
* Wall-clock cost remains near one parallel wave.

This validates adaptive early stopping.

---

## TC-E02: One correct candidate among six

Configure mocked agents so that:

* Five candidates are plausible but wrong.
* One candidate is correct.
* All six provide polished explanations.
* Only the correct candidate passes an edge test.

**Expected behavior:**

* Oracle pass@6 is one.
* Selected pass@1 is one.
* Selector regret is zero.
* LLM rhetoric does not override execution evidence.

---

## TC-E03: Correct candidate is not the smallest patch

Create:

* Candidate A: one-line patch that passes visible tests but breaks compatibility.
* Candidate B: five-line patch that passes all tests.
* Candidate C: large unnecessary refactor.

**Expected behavior:**

* Candidate B wins.
* Minimality is used only after correctness.
* Candidate A is rejected through compatibility tests.

---

## TC-E04: No initial candidate is correct

Configure all six candidates to fail at least one required test.

**Expected behavior:**

* No candidate is declared successful.
* The workflow enters refinement.
* Refinement receives the failure evidence.
* A refined candidate can fix the remaining defect.
* If refinement also fails, the run ends honestly as unresolved.

The system must never report success only because one candidate is “best among failures.”

---

## TC-E05: Judge makes an incorrect choice

Mock tournament judges to prefer a candidate that fails a deterministic test.

**Expected behavior:**

* The failing candidate remains rejected.
* Judge results are retained for auditing.
* Deterministic gates dominate selection.

---

## TC-E06: Ambiguous candidates require distinguishing test

Create two candidates that pass existing tests:

* Candidate A handles Unicode correctly.
* Candidate B handles large inputs efficiently.
* Task requirements imply both are important.

**Expected behavior:**

* Judges identify unresolved dimensions.
* The workflow generates targeted Unicode and large-input tests.
* Final selection is based on the new results.

---

## TC-E07: Refinement improves a candidate

Initial candidate:

* Correct root cause.
* Incomplete edge-case handling.

Refinement packet includes:

* Another worker’s discovered edge case.
* Test matrix failure.
* Tournament criticism.

**Expected behavior:**

* Refiner incorporates the useful discovery.
* The refined patch passes tests the parent candidate failed.
* Candidate lineage is preserved.
* The final report explains the improvement.

---

## TC-E08: Refinement causes regression

Create a refinement that fixes one edge case but introduces another failure.

**Expected behavior:**

* Refined candidates are evaluated from scratch.
* The parent is not automatically discarded.
* The system may select the original parent if it remains stronger.
* “Newer” does not automatically mean “better.”

---

# 6. Failure-injection and chaos tests

## TC-C01: One Claude process crashes

**Expected behavior:**

* Other five workers continue.
* Failed candidate is recorded.
* Slot is released.
* Workflow proceeds when enough valid candidates remain.
* Report clearly shows reduced candidate count.

---

## TC-C02: Three Claude processes crash

**Expected behavior:**

* Retry only when failure is classified as transient.
* Workflow may continue with surviving candidates when configured.
* High uncertainty triggers either replacement workers or a warning.
* The system does not pretend six complete trajectories exist.

---

## TC-C03: vLLM temporarily returns 429

Use a fake server that returns:

```text
429, 429, success
```

**Assertions:**

* Retry uses bounded exponential backoff.
* Agent logs contain retry metadata.
* No duplicate candidate worktrees are created.
* The final candidate is associated with one logical worker ID.

---

## TC-C04: vLLM returns persistent 500 errors

**Assertions:**

* Retry stops at the configured limit.
* Run state is preserved.
* `hydra-code resume` can continue later.
* No process retry loop runs indefinitely.

---

## TC-C05: Invalid structured output

One worker returns valid code changes but malformed summary JSON.

**Expected behavior:**

* Worktree and patch are preserved.
* One summary-repair attempt occurs.
* Deterministic test evaluation still runs.
* Candidate is not discarded solely because narrative formatting failed.

---

## TC-C06: Test hangs

Create a test that never terminates.

**Assertions:**

* Test timeout occurs.
* Process group is terminated.
* Result is recorded as timeout, not pass or ordinary fail.
* Remaining candidate tests continue.
* CPU test semaphore is released.

---

## TC-C07: Flaky test

Create a test that fails randomly.

**Expected behavior:**

* Test can be rerun a configurable number of times.
* Test is marked flaky when results disagree.
* Flaky tests do not become sole hard rejection evidence by default.
* Report displays all attempts.

---

## TC-C08: Disk space or write failure

Simulate artifact-write failure.

**Assertions:**

* Main checkout remains unchanged.
* Worktrees are not prematurely deleted.
* Run fails with an actionable message.
* Already persisted evidence remains readable.

---

## TC-C09: Orchestrator killed mid-run

Terminate the orchestrator during:

1. Candidate generation.
2. Test-matrix execution.
3. Tournament judging.
4. Refinement.
5. Final report generation.

For each phase:

* Restart using `hydra-code resume <run-id>`.
* Completed work must not be repeated unnecessarily.
* Incomplete subprocesses must be recognized.
* Run state must continue from a valid checkpoint.
* Final artifacts must not contain duplicated candidate IDs.

---

# 7. Generated-test validation cases

## TC-T01: Valid reproduction test

* Fails on base.
* Passes on correct patch.
* Fails on incorrect patches.

Result: accept.

---

## TC-T02: Test already passes on base

Result:

* Reject as a bug-reproduction test.
* It may still be retained as a regression test when relevant.

---

## TC-T03: Candidate-coupled test

Example:

```python
assert "_new_internal_helper" in source_code
```

Result: reject unless the task explicitly requires that API.

---

## TC-T04: Test weakens behavior

Example:

```python
assert response.status_code in {200, 500}
```

Result: reject.

---

## TC-T05: Test asserts an unsupported interpretation

The task is ambiguous and a generated test assumes behavior not present in requirements or repository conventions.

Result:

* Mark as disputed.
* Do not use as a hard gate.
* Present it to judges as uncertainty.

---

## TC-T06: Duplicate tests

Two agents create semantically equivalent tests with different names.

Result:

* Deduplicate or group them.
* Preserve provenance.
* Avoid overweighting one behavior merely because multiple workers wrote the same test.

---

## TC-T07: Cross-candidate test execution

A test written by candidate A must execute against:

* Base revision.
* Candidate A.
* Candidate B.
* Candidate C.
* Every surviving candidate.

This test verifies that generated tests are candidate independent.

---

# 8. Candidate diversity tests

Parallel rollouts provide little benefit when all candidates are nearly identical.

Measure diversity using:

* Changed-file Jaccard distance.
* Changed-symbol overlap.
* Normalized diff similarity.
* Root-cause hypothesis similarity.
* Test-strategy overlap.
* Command-sequence similarity.

## TC-D01: Identical role prompts

Run six workers with the same prompt and deterministic mocked outputs.

Expected:

* Diversity metrics are near zero.
* Workflow emits a diversity warning.

## TC-D02: Role-diversified prompts

Run workers using the six defined roles.

Expected:

* More distinct hypotheses, tests or files are explored.
* Diversity is greater than the identical-prompt baseline.

## TC-D03: Superficial diversity

Create six candidates with different explanations but identical patches.

Expected:

* Diff diversity remains near zero.
* Narrative differences do not falsely count as meaningful exploration.

## TC-D04: Excessive low-quality diversity

Create six unrelated or speculative patches.

Expected:

* Diversity is high.
* Test success is low.
* System does not interpret diversity itself as quality.

---

# 9. Real Qwen end-to-end tests

These tests must use:

```text
http://127.0.0.1:8000/v1
model ID: qwen
```

The Claude Code bridge must use the existing local configuration.

---

## TC-R01: Single real-agent smoke test

Run one worker against Fixture F1.

Validate:

* Claude Code launches successfully.
* It edits only its worktree.
* It returns or can be converted into a trajectory summary.
* Test results are captured.
* A patch artifact is produced.

---

## TC-R02: Six concurrent real workers

Run six workers against Fixture F2 or F5.

Capture timestamps for all vLLM requests.

Validate:

* At least several model calls overlap.
* Maximum configured process concurrency is six.
* All workers receive unique worktrees.
* Aggregate generation throughput exceeds the single-worker run.
* The workflow completes without worktree corruption.

Do not require exactly six requests to remain active continuously because agents alternate between model inference and tool execution.

---

## TC-R03: Real tournament selection

Run a fixture where at least two Qwen candidates produce different patches.

Validate:

* Summaries and diffs are provided to judges.
* Judge calls are separate from candidate-generation calls.
* Deterministic tests remain visible in the final decision.
* Final selection can be traced to specific evidence.

---

## TC-R04: Real refinement

Select an initially imperfect candidate and run one refinement wave.

Validate:

* Refiner receives the distilled packet.
* Refiner does not receive every raw trajectory.
* Parent and refined diffs are both stored.
* The refined candidate is retested fully.
* The report identifies which external candidate discoveries were incorporated.

---

# 10. GPU-utilization validation

Poll vLLM metrics once per second or at a configurable interval.

Capture:

```text
running requests
waiting requests
prompt tokens per second
generation tokens per second
prefix-cache hits
KV-cache utilization
preemptions
request latency
time to first token
time per output token
```

Where a metric is unavailable, mark it unavailable rather than failing the workflow.

---

## TC-P01: Single versus six-worker throughput

Run the same workload in two configurations:

```text
Configuration A: concurrency = 1
Configuration B: concurrency = 6
```

Measure:

* Total output tokens.
* Wall-clock duration.
* Aggregate output tokens per second.
* Mean active requests.
* Peak waiting requests.
* KV-cache usage.
* Preemptions.

Expected:

* Six-worker aggregate throughput should materially exceed single-worker throughput.
* The target should be measured from the actual server rather than assumed to be 150 tokens/s.

---

## TC-P02: Concurrency sweep

Test:

```text
1, 2, 4, 6, 8 agent processes
```

Even though model concurrency is targeted at six, eight agent processes may help keep six model slots occupied while some agents execute tools.

For each setting, record:

* Aggregate tokens per second.
* Median task completion time.
* Mean active vLLM requests.
* Waiting-request count.
* KV-cache utilization.
* Preemptions.
* Failure rate.

Select the default process count based on measured throughput and stability.

A valid conclusion might be:

```text
Six processes maximize stability.
Eight processes improve utilization because agents spend time running tests.
Beyond eight, queueing and KV pressure dominate.
```

Do not assume this conclusion in advance.

---

## TC-P03: Prefix-cache effectiveness

Run candidates with:

1. A shared identical context prefix.
2. Equivalent content ordered differently.
3. Fully independent prompts.

Compare prefix-cache query and hit metrics.

Expected:

* Identical shared prefixes produce the highest cache reuse.
* Role-specific content should appear after the shared context packet.

---

## TC-P04: KV-cache pressure

Use longer context packets and six simultaneous requests.

Validate:

* KV utilization stays below the configured safety threshold.
* No unexplained request preemption occurs.
* When preemptions appear, the workflow records them and recommends reducing context or concurrency.

---

## TC-P05: Tool-execution gaps

Measure each worker’s time in:

```text
LLM inference
shell/test execution
idle or queueing
```

Expected:

* When many workers are simultaneously running tests, active model requests may fall.
* The scheduler should use queued workers to refill available inference capacity when safe.

---

# 11. Intelligence-gain evaluation

The workflow must prove more than higher throughput. It must show better final problem-solving performance.

Evaluate these configurations:

| ID | Configuration                              |
| -- | ------------------------------------------ |
| A  | One Claude Code agent                      |
| B  | Six agents, choose first passing candidate |
| C  | Six agents + common existing tests         |
| D  | Six agents + generated-test union          |
| E  | D + Recursive Tournament Voting            |
| F  | E + refinement                             |
| G  | Adaptive full workflow                     |

Use the same tasks, repository revisions, token budgets and verification tests.

---

## Required metrics

### Solve rate

Fraction of tasks whose final patch passes all trusted verification tests.

### Oracle pass@6

Fraction of tasks where at least one initial candidate was correct.

### Selected pass@1

Fraction where the workflow selected a correct candidate.

### Selector regret

```text
selector_regret = oracle_pass@6 - selected_pass@1
```

This is one of the most important metrics.

Interpretation:

* High oracle pass@6 and low selected pass@1 means candidate generation works but selection fails.
* Low oracle pass@6 means the system needs better exploration or refinement.
* High selected pass@1 with high cost may require better early stopping.

### Refinement recovery rate

Among tasks with no fully correct initial selection:

```text
number solved after refinement
--------------------------------
number entering refinement
```

### Wall-clock efficiency

Measure:

```text
successful tasks per hour
```

not merely tokens per second.

### Compute efficiency

Measure:

```text
successful tasks per million generated tokens
```

### Diversity-quality relationship

Compare candidate diversity with:

* Oracle pass@6.
* Final solve rate.
* Selector regret.

---

# 12. Benchmark task protocol

Use at least:

* Six deterministic fixture tasks.
* Ten to twenty small real repository tasks.
* A mixture of:

  * Bug fixes.
  * API changes.
  * Test additions.
  * Refactoring with behavioral constraints.
  * Async or concurrency bugs.
  * Parsing and compatibility bugs.
  * Multi-file changes.

Each task must have:

```yaml
id: pagination-boundary
repo: tests/fixtures/pagination_bug
base_ref: <sha>
task: |
  Correct pagination behavior for all input sizes.
public_verification:
  - pytest -q tests/public
trusted_verification:
  - pytest -q tests
constraints:
  - Preserve behavior for empty input.
  - Do not change the public API.
```

The agents may see public verification but must not see trusted hidden tests during candidate generation.

The orchestrator may run trusted tests only for benchmark scoring, not for production candidate selection unless those tests are genuinely available to the user.

This separation prevents benchmark leakage.

---

# 13. Repetition and statistical controls

Because Qwen sampling is nondeterministic:

* Run each benchmark configuration at least three times.
* Use fixed documented seed sets where supported.
* Rotate task order.
* Run configurations on the same machine state when possible.
* Record model parameters.
* Record vLLM version, image ID and server configuration.
* Record Claude Code version and bridge version.
* Report mean, median and standard deviation.
* Use paired comparisons by task.

Do not claim improvement from one successful example.

A minimum useful report should include:

```text
Configuration
Solved / total
Oracle pass@6
Selected pass@1
Selector regret
Median wall time
Total tokens
Aggregate output tok/s
Mean active requests
Refinement recovery
```

---

# 14. Dynamic-policy validation

The adaptive workflow must make correct escalation decisions.

## TC-A01: Easy task

Signals:

* Multiple equivalent passing candidates.
* High judge agreement.
* Low uncertainty.

Expected:

* Stop after initial selection.
* No full refinement wave.

## TC-A02: High disagreement

Signals:

* Different root causes.
* Different changed files.
* Close test scores.
* Judge disagreement.

Expected:

* Escalate to distinguishing tests or refinement.

## TC-A03: No useful diversity

Signals:

* Nearly identical patches.
* Same tests.
* Same failures.

Expected:

* Launch alternative-hypothesis workers rather than three more identical refiners.

## TC-A04: Strong deterministic winner

Signals:

* One candidate passes every test.
* Others fail hard gates.

Expected:

* Skip unnecessary tournament calls or use only one verification judge, depending on configuration.

## TC-A05: All candidates fail

Expected:

* Enter refinement when budget permits.
* Otherwise report unresolved.
* Never label the highest-scoring failing candidate as successful.

## TC-A06: Budget exhaustion

Expected:

* Finish the current safe phase.
* Preserve all artifacts.
* Return the best verified state.
* Clearly distinguish:

  * Verified solution.
  * Partial candidate.
  * Unresolved task.

---

# 15. Final acceptance thresholds

The initial release should satisfy all of the following:

## Functional correctness

* All unit tests pass.
* All mocked integration tests pass.
* All six fixture repositories are solved by the full workflow.
* The selector chooses the trusted correct patch in every deterministic selector fixture.
* No hard-gate failure is selected.

## Safety

* Main checkout is unchanged during candidate generation.
* Dirty repositories are protected.
* Interrupted runs can resume.
* Candidate patches survive cleanup.
* No orphan agent processes remain after cancellation.
* Secrets are redacted from user-facing reports.

## Concurrency

* Configured model-facing concurrency is never exceeded.
* At least six candidate sessions can be managed simultaneously.
* Scheduler slots are released after failures and timeouts.
* Real vLLM runs show overlapping requests.

## Selection

* Selector regret is zero on deterministic fixture tests.
* Generated tests are executed across every candidate.
* Invalid generated tests are excluded from hard gating.
* Tied selections trigger new evidence gathering.

## Performance

On the local Qwen/vLLM setup:

* Six-worker aggregate generation throughput is greater than single-worker throughput.
* The workflow records actual rather than assumed throughput.
* No sustained KV-cache preemption occurs under the recommended default.
* The chosen concurrency setting is supported by measured results.

## Intelligence improvement

On the benchmark suite:

* The full workflow must outperform the single-agent baseline in solve rate.
* Report both absolute and relative gains.
* Improvement must be shown across repeated runs, not one anecdotal task.
* Token and wall-clock costs must be reported alongside solve rate.

A recommended initial target is:

```text
Full workflow solve rate:
  at least 15% relative improvement over single agent

Selector regret:
  less than 10 percentage points

Fixture selector regret:
  0

Aggregate generation throughput:
  at least 2× the single-stream throughput

Main-checkout corruption:
  0 incidents

Unrecovered orchestrator crashes:
  0 incidents
```

These are engineering targets, not assumptions. Report actual values even when targets are missed.

---

# 16. Required validation report

Generate:

```text
.hydra/validation/
├── environment.json
├── unit-results.xml
├── integration-results.xml
├── e2e-results.json
├── gpu-metrics.csv
├── benchmark-results.csv
├── candidate-diversity.csv
├── selector-analysis.json
└── VALIDATION_REPORT.md
```

`VALIDATION_REPORT.md` must contain:

1. Environment and versions.
2. Tests executed.
3. Passed, failed and skipped tests.
4. Concurrency behavior.
5. GPU utilization.
6. Single-agent baseline.
7. Parallel-workflow results.
8. Oracle pass@6.
9. Selected pass@1.
10. Selector regret.
11. Refinement recovery rate.
12. Candidate diversity.
13. Failure-injection results.
14. Safety validation.
15. Known weaknesses.
16. Recommended default configuration.

The report must state conclusions conservatively.

Example:

```text
The workflow increased aggregate model throughput from 25 tok/s to
142 tok/s and improved solve rate from 45% to 60% on 20 local tasks.

Most of the accuracy gain came from generated cross-candidate tests.
Tournament judging improved selection on two tasks but made no
difference when deterministic tests already produced a clear winner.

Eight Claude Code processes kept the six vLLM request slots more
consistently occupied than six processes, but caused KV preemption on
long-context tasks. Six remains the safe default; eight is recommended
only when context length is below the measured threshold.
```

Do not claim that the workflow “hugely improves intelligence” unless benchmark results support that conclusion.

---

# 17. Implementation order for the test suite

Implement validation in this order:

1. Scheduler and concurrency unit tests.
2. Worktree safety tests.
3. Run-state and resume tests.
4. Structured-output validation tests.
5. Hard-gate and scoring tests.
6. Tournament tests.
7. Generated-test validation.
8. Deterministic fixture repositories.
9. Full mocked end-to-end workflow.
10. Failure-injection tests.
11. Real single-agent Qwen smoke test.
12. Real six-agent concurrency test.
13. Real tournament and refinement test.
14. Concurrency sweep.
15. Ablation benchmark.
16. Final validation report.

Do not begin large real-model benchmarks until all deterministic integration tests pass.


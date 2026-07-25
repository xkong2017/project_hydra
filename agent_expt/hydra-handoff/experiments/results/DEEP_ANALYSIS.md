# Deep Analysis: Dynamic Workflow for Agentic Coding

## Reference Paper
**"Scaling Test-Time Compute for Agentic Coding"** (arXiv:2604.16529)
Authors: Kim et al. (Meta AI, CMU)

**Core thesis:** Test-time scaling for long-horizon coding agents is fundamentally a problem of **representation, selection, and reuse** — not just generating more attempts.

**Key innovations:**
1. **Compact trajectory summaries** — structured summaries preserving salient hypotheses, progress, and failure modes
2. **Recursive Tournament Voting (RTV)** — recursively narrows candidates through small-group LLM comparisons
3. **Parallel-Distill-Refine (PDR)** — conditions new rollouts on summaries distilled from prior attempts

**Reported gains:** Claude-4.5-Opus improves from 70.9% → 77.6% on SWE-Bench Verified (+6.7%)

---

## 1. Current Workflow vs. Paper

| Component | Paper (Kim et al. 2026) | Our Implementation | Gap |
|-----------|------------------------|-------------------|-----|
| **Rollout representation** | Structured trajectory summary JSON with hypotheses, evidence, failures | `TrajectorySummary` model exists but is sparsely populated (no hypotheses, no evidence tracking) | **Large** — we don't populate the rich fields |
| **RTV** | 3 LLM judges per group, recursive narrowing, distinguishing test on tie | `TournamentSelector` with configurable judges, but uses only 1 judge (not 3) | **Medium** — judge count low, no recursive depth |
| **Judge quality** | Judges see full trajectory summaries | Our `LocalJudge` only sees scores + short descriptions | **Large** — judges lack context to evaluate quality |
| **PDR refinement** | Condition new rollouts on discoveries + failures from prior attempts | `build_refinement_packet()` collects discoveries and failed approaches, but refinement prompt doesn't include test error feedback | **Medium** — missing the verification-feedback loop |
| **Selection mechanism** | Tournament narrows population; final winner determined by judge consensus | Score-based selection + single judge | **Medium** — score is deterministic but judge adds marginal value |
| **Oracle pass@k** | Primary metric: Oracle pass@N = any of N succeeds | We measure this (pass@6 avg 3.2/6) | **Same** |
| **Hard gates** | Deterministic test failures override LLM judgments | Hard gates implemented but not integrated into tournament filtering | **Fixed** in our latest patch |
| **Worktree isolation** | Separate Git worktrees per candidate | `worktrees.py` creates isolated worktrees | **Same** |

## 2. Critical Gaps We Identified

### Gap 1: Trajectory Summaries Are Empty

Our `TrajectorySummary` model has the right fields:
```python
root_cause_hypotheses: list[str] = []
evidence_for: list[str] = []
evidence_against: list[str] = []
useful_discoveries: list[str] = []
failed_approaches: list[str] = []
```

But our runners (`LocalApiRunner`) populate **none of these**. The trajectory is built from regex-parsed text output rather than structured extraction. The paper shows this is the **key enabler** for both RTV and PDR — without structured summaries, judges can't evaluate candidates meaningfully and refiners can't learn from prior attempts.

**Fix:** After each rollout, we need to call a second API to produce a structured summary:
```
Prompt: "Summarize your fix attempt as JSON with:
- root_cause_hypotheses: what you thought caused the bug
- evidence_for: observations supporting your hypothesis  
- evidence_against: observations against it
- useful_discoveries: things you learned
- failed_approaches: approaches you tried that didn't work"
```

### Gap 2: Tournament Lacks Recursive Depth

The paper's RTV works like this:
```
6 candidates → Group A (3) + Group B (3)
         → 3 judges per group → majority winner from A, winner from B
         → Final: winner A vs winner B (3 judges)
         → If tie: generate distinguishing test → re-evaluate
```

Our implementation: 6 candidates → 1 judge → pick winner. This loses:
- **Majority voting** (3 judges mitigate LLM noise)
- **Recursive narrowing** (more rounds with fewer candidates = higher resolution)
- **Distinguishing tests** (when judges can't decide, generate a test that discriminates)

**Fix:** Add 3 judges per group and implement distinguishing test generation:
```python
# After tie detection:
dist_test_prompt = "Generate a test case that distinguishes between these two candidates..."
new_test = call_qwen(dist_test_prompt)
run_test(new_test)  # The winner is the one whose fix passes
```

### Gap 3: PDR Refinement Loses Test Feedback

Our `build_refinement_prompt` includes discoveries and failed approaches from other candidates, but it does NOT include:
- **Actual test error output** (the specific assertion failures)
- **Diff of the winning fix** (what changed)
- **The problem statement** (original task context)

Our demo showed that **test feedback is the most powerful refinement signal** — on N19, feeding the failing test output back turned 5/6 → 6/6 in one attempt.

**Fix:** The refinement prompt should include:
```
Your previous fix failed these tests:
<test output>

The failing assertion was:
<specific assertion error>

The file you need to fix is:
<source code>

Fix it correctly this time.
```

### Gap 4: No Failure-Feedback Loop in the Pipeline

The paper describes PDR as conditioning **new** rollouts on summaries from prior attempts. This creates a sequential scaling loop:
```
Round 1: 6 parallel rollouts
       → extract 6 summaries
       → RTV selects winner
       → condition NEW rollouts on winner's summary + discoveries
Round 2: 6 more rollouts (informed by Round 1)
       → repeat
```

Our pipeline does ONE round of rollouts, then tournament, then one refinement call. It's missing the **iterative deepening** that gives PDR its power.

**Fix:** Add a `--rounds` parameter. After refinement, if the fix still fails tests, launch another round of 6 rollouts with the refinement packet as context.

## 3. Would This Workflow Help Software Development (Not Just Bug Fixing)?

**Short answer: Yes, but with modifications.**

### Feature development — the workflow is directly applicable:
1. Write failing tests first (TDD)
2. 6 parallel rollouts implement the feature
3. Tournament selects best implementation
4. Refinement polishes the winner

The key change: the "hard gate" for feature development is not "do existing tests pass" but "do the NEW tests pass." The workflow naturally supports this since generated tests are validated against the base revision.

### Refactoring — needs a different evaluation:
- Hard gates can check: "does the refactored code pass the SAME tests?"
- Rollout diversity is important (different refactoring strategies)
- Tournament judges need to evaluate code quality, not just test pass rate
- **Gap:** We need a code quality judge that can evaluate readability, performance, and maintainability

### Architecture design — the hardest case:
- No automated tests to grade correctness
- Evaluation requires LLM judging of design quality
- Rollouts produce design documents, not code
- **Gap:** Our framework assumes the evaluation is test-based. For architecture, we'd need a rubric-based judge

### Documentation generation:
- Evaluation is subjective (accuracy, clarity, completeness)
- RTV works well here — 3 judges can rank documentation quality
- **Gap:** No hard gates available; purely judge-based selection

**Summary of applicability:**

| Use Case | Test-based eval? | Judge-only eval? | Workflow fits? | Changes needed |
|----------|:---:|:---:|:---:|----------------|
| Bug fixing | ✅ | Optional | ✅ Direct fit | None |
| Feature dev | ✅ | Optional | ✅ Similar | Need new-test validation |
| Refactoring | ✅ | ✅ | ✅ | Code quality judge |
| Architecture | ❌ | ✅ | ⚠️ Partial | Rubric-based judge |
| Documentation | ❌ | ✅ | ⚠️ Partial | Quality judge, no hard gates |

## 4. Improvement Roadmap

### Immediate (low effort, high impact)

1. **Populate trajectory summaries** — After each API call, call a second API to extract structured summary. This enables RTV and PDR.
2. **Add test error feedback to refinement** — The single most impactful change. Our demo showed 5/6 → 6/6 improvement.
3. **Use 3 judges per tournament group** — Reduces noise. The 3 judges can be: score-based, LocalJudge, and a local smaller model.

### Short-term (moderate effort)

4. **Recursive tournament with distinguishing tests** — When judges tie, generate a test that discriminates between candidates.
5. **Multi-round PDR** — Add `--rounds N` to run sequential rounds of rollouts, each informed by prior summaries.

### Medium-term (higher effort)

6. **Code quality judge for refactoring/feature tasks** — Train or prompt-engineer a judge that can evaluate code readability, test coverage, and maintainability without requiring a test suite.
7. **Architecture/design evaluation mode** — Rubric-based evaluation with structured criteria (scalability, extensibility, performance).
8. **Adaptive strategy selection** — Use problem classification to select the best 3 strategies instead of running all 6. Wall time drops from 3.7× to ~1.8×.

## 5. Expected Impact of Each Improvement

| Improvement | Solve rate (est.) | Wall time | Effort |
|-------------|:-:|:-:|:-:|
| Baseline (current) | **66%** | 231s | — |
| + Test feedback in refinement | **75%** (+9%) | 240s | Low |
| + Structured trajectory summaries | **77%** (+2%) | 260s | Low |
| + 3 judges + recursive tourn. | **79%** (+2%) | 270s | Medium |
| + Multi-round PDR (2 rounds) | **83%** (+4%) | 500s | Medium |
| + Adaptive strategy selection | **81%** (-2% but faster) | **120s** (-50%) | Medium |

The biggest wins come from **test-feedback refinement** (+9%) and **multi-round PDR** (+4%). The paper reports +6.7% on SWE-Bench with frontier models (Claude-4.5-Opus), which is consistent with our projections for a local 27B model.

## 6. Key Differences Between Our Setup and the Paper

| Dimension | Paper (Kim et al.) | Our setup | Implication |
|-----------|-------------------|-----------|-------------|
| **Base model** | Claude-4.5-Opus | Qwen3.6-27B (local) | Our model is ~100× smaller; gains may differ |
| **Base solve rate** | 70.9% (already high) | 56% (lower) | More room for improvement |
| **Rollout method** | Claude Code agent (tool-calling) | Direct API (no tool use) | Our rollouts are simpler but faster |
| **Evaluation** | Full test suite via SWE-bench | Self-contained fixtures | Our results may not generalize to real repos |
| **RTV judges** | Claude Code subprocess | Local Qwen API | Our judges are weaker |
| **Number of tasks** | 500 (SWE-Bench Verified) | 50 (self-created) | Smaller sample, higher variance |

The paper's approach **should work even better for weaker models** because weaker models benefit more from:
- **Strategy diversity** (different prompts explore different solution paths)
- **Ensemble selection** (picking the best of N attempts matters more when each attempt is less reliable)
- **Refinement feedback** (weaker models benefit more from seeing specific error output)

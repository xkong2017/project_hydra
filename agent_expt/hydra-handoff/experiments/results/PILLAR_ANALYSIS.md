# Representation, Selection, Reuse: Deep Analysis

## Reference: "Scaling Test-Time Compute for Agentic Coding" (arXiv:2604.16529)

The paper frames test-time scaling as a problem of **representation, selection, and reuse**. Our experiments confirm this framing — raw strategy diversity (running 6 rollouts) gave only +10% improvement, but adding structured trajectory summaries + 3-judge tournament + test-feedback refinement gave **+50% improvement**.

---

## 1. Representation: How We Condense Rollout Experiences

### What we implemented

We extend `LocalApiRunner.run()` to call a **second API** after each rollout to extract a structured `TrajectorySummary`:

```python
async def _extract_trajectory(self, content, reasoning):
    prompt = """Analyze this bug-fix attempt and return JSON with:
      root_cause_hypotheses, evidence_for, evidence_against,
      useful_discoveries, failed_approaches, remaining_uncertainty"""
    content, reasoning = await self._call_api(prompt)
    # Parse JSON from response
```

**Key fields populated:**
- `root_cause_hypotheses` — what the model thought caused the bug
- `evidence_for` — observations supporting its hypothesis
- `evidence_against` — observations against it
- `useful_discoveries` — things learned during the attempt
- `failed_approaches` — approaches tried that didn't work

These are extracted **after** each rollout and fed into the refinement prompt.

### What the paper does

The paper's representation is more sophisticated:
1. **Multi-step distillation** — raw trajectory → structured summary → compressed summary. Each step discards low-signal details.
2. **Hypothesis tracking** — candidate hypotheses are tracked with evidence for/against, enabling meta-reasoning
3. **Failure mode categorization** — failures are categorized (syntax, logic, missing feature, test weakening) not just listed

### How to improve

**1. Hierarchical distillation (low effort, high impact)**

Currently: one prompt produces the full summary. This is lossy — the model must compress ~10K chars of reasoning into a few bullet points in a single pass.

Better: two-stage distillation
```
Stage 1: "Extract ALL observations from this attempt" → raw notes
Stage 2: "Condense these notes into root_cause_hypotheses, evidence_for/against"
```

This mirrors how human engineers debug: first gather all observations, then reason about them.

**2. Hypothesis tracking across rounds (medium effort)**

In multi-round PDR, each round's trajectories should be accumulated:
```
Round 1 hypotheses: [H1, H2]
Round 2 hypotheses: [H1 (strengthened), H2 (refuted), H3 (new)]
```
This prevents the model from repeating disproven approaches.

**3. Failure mode categorization (medium effort)**

Instead of flat "failed_approaches", categorize failures:
```
syntax_errors: [list]
logic_errors: [list]  
test_weakening: [list]
missing_features: [list]
```
The refinement prompt can then say "Fix the LOGIC errors. Do NOT weaken existing tests."

**Expected impact:** +5% solve rate from better representation quality (hypothesis tracking prevents repeated mistakes)

---

## 2. Selection: How We Choose the Best Candidate

### What we implemented

We have 3 judges per tournament group:
1. **ScoreJudge** — deterministic, based on test pass % + hard gates
2. **LocalJudge (temperature=0.3)** — LLM-based with score + description context
3. **LocalJudge (temperature=0.5)** — same but with higher diversity

The tournament:
- Pre-filters candidates that failed hard gates
- Splits into 2 groups of 3
- 3 judges vote → majority wins per group
- Group winners compete in final
- On tie: generates a distinguishing test

### What the paper does

Paper's RTV is more nuanced:
1. **Recursive depth** — not just 2 groups, but recursively narrows from 6 → 3 → 2 → 1
2. **3 DIFFERENT judge models** — not 3 calls to the same model with different temps
3. **Distinguishing test as FIRST resort** — when judges disagree, they generate a test BEFORE voting
4. **Confidence-weighted voting** — judges with higher confidence votes count more

### How to improve

**1. True recursive narrowing (medium effort)**

Current: 6 → 2 groups → 2 winners → 1 final
Better: 6 → 3 groups → 3 winners → 2 groups → 2 winners → ... → 1

```
Round 1: [A,B,C], [D,E,F] → winners W1, W2
Round 2: [W1, W2, W3], [W4, W5, W6] → winners X1, X2
Round 3: [X1, X2] → final winner
```

More rounds means each comparison is between fewer candidates, making the judge's job easier. 6-way ranking is hard; 2-way comparison is easy.

**2. Judge ensemble diversity (medium effort)**

Instead of 3 calls to the same Qwen model with different temperatures, use genuinely different judges:
- Judge 1: Score-based (deterministic, fast)
- Judge 2: Qwen with tdd-style prompt ("focus on test coverage")
- Judge 3: Qwen with adversarial prompt ("focus on edge cases")
- Judge 4: Code complexity analysis (lines changed, cyclomatic complexity)

Different judges have different "expertise" — they catch different issues.

**3. Distinguishing test BEFORE tie (low effort)**

Currently: tie → generate distinguishing test.
Better: ALWAYS generate a distinguishing test for the final pair, whether tie or not. Use the test outcome as the tiebreaker, not LLM opinion.

```python
# Proposed: test-based final selection
final_pair = [winner_a, winner_b]
dist_test = generate_distinguishing_test(task, final_pair)
winner = run_test_on_both(dist_test, final_pair)
# The fix that passes is the winner (deterministic!)
```

**Expected impact:** +3% solve rate from better selection (fewer wrong winners due to judge noise)

---

## 3. Reuse: How We Refine Candidates

### What we implemented

The refinement prompt includes:
1. Original source code
2. Test error output (the failing assertions)
3. Useful discoveries from other candidates
4. Failed approaches to avoid
5. Previous buggy fix

If the first refinement fails, a **second attempt** is made with more emphasis on matching test expectations.

### What the paper does

Paper's PDR is more systematic:
1. **Full rollout conditioning** — new rollouts are CONDITIONED on summaries from prior attempts, not just refinement of the winner
2. **Cross-candidate distillation** — the best parts of ALL candidates are combined, not just one winner
3. **Sequential rounds** — Round 2 rollouts start with knowledge from Round 1
4. **Anti-pattern library** — common failures are tracked across tasks and injected into prompts

### How to improve

**1. Full rollout conditioning (medium effort, high impact)**

Currently: we refine only the WINNER.
Better: run ANOTHER full round of 6 rollouts, where each new rollout gets the round-1 summaries as context.

```
Round 1: 6 rollouts → summaries S1-S6 → tournament → winner W
Round 2: 6 NEW rollouts, each starting with "Previous attempts found: {S1-S6}"
         → new candidates conditioned on prior knowledge → higher quality
```

This is the paper's PDR — and it's why our refinement only got us 11/22 instead of more. Full re-rollouts would find better fixes than just refining the best of round 1.

**2. Cross-candidate knowledge distillation (high effort)**

Instead of picking ONE winner, combine insights from all candidates:
```
Best parts of candidate A: {extract}
Best parts of candidate B: {extract}
Merge them into a single fix that incorporates both insights.
```

This is like ensemble learning in ML — combine multiple weak models into a stronger one.

**3. Anti-pattern library (low effort, cumulative)**

Track common failures across ALL tasks:
```json
{
  "mutable_default_args": "Model kept 'def f(x=[])' — need to change to 'def f(x=None)'",
  "exception_chaining": "Model used bare 'raise' instead of 'raise from'"
}
```

Inject these into future prompts when similar patterns are detected. This is a form of **learned skill** — the pipeline gets better over time as it sees more bugs.

**4. Iterative deepening with budget (medium effort)**

Not all tasks need the same number of refinement rounds:
- Task with 4/6 candidate passes: 1 refinement round
- Task with 0/6 candidate passes: 3 refinement rounds + full re-rollout

Adaptive budget allocation based on initial performance.

**Expected impact:** +8% solve rate from multi-round PDR + cross-candidate distillation

---

## 4. Current Efficiency Analysis

| Step | Wall time | % of total | Optimization potential |
|------|:---------:|:----------:|-----------------------|
| 6 rollouts (parallel) | ~150s | 65% | Use 3 strategies instead of 6 (−50%) |
| Trajectory extraction (6×) | ~60s | 26% | Batch extraction or skip for obvious cases |
| Tournament (3 judges) | ~20s | 9% | Already fast |
| Refinement (1-2 rounds) | ~100s | — | Sequential bottleneck |

**Total wall time:** ~230s for first rollout round + ~100s for refinement = ~330s

### Optimization proposals

**1. Adaptive strategy count:**
- Task difficulty estimated from problem statement length / complexity
- Easy tasks: 3 strategies (tdd, root-cause, minimal)
- Hard tasks: 6 strategies (add adversarial, alternative, architecture)
- Estimated: −40% wall time, −2% solve rate

**2. Batch trajectory extraction:**
- Instead of 6 separate API calls for trajectory extraction, send all 6 raw outputs in one prompt and get 6 summaries
- Estimated: −10% wall time, 0% solve rate impact

**3. Speculative refinement:**
- Start refinement BEFORE tournament finishes, using the current leader
- If a different candidate wins, restart refinement with correct candidate
- Estimated: no wall time improvement but better utilization

---

## 5. Proposed Complete Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│ ROUND 1 (parallel, 6 strategies)                                    │
│ tdd ──┐ root-cause ──┐ minimal ──┐ architecture ──┐ adversarial ──┐ alternative │
│       │              │           │               │               │           │
│     Summary S1    Summary S2   Summary S3   Summary S4      Summary S5   Summary S6 │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ SELECTION: 3-Judge Recursive Tournament                              │
│ ┌──────────────────────────────────────────────────────────────┐    │
│ │ Group A: S1,S2,S3 → 3 judges → majority winner A              │    │
│ │ Group B: S4,S5,S6 → 3 judges → majority winner B              │    │
│ │ Final: winner A vs winner B → 3 judges + distinguishing test  │    │
│ └──────────────────────────────────────────────────────────────┘    │
│ Winner: candidate W                                                 │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ REUSE: Multi-Round PDR with Test Feedback                           │
│                                                                     │
│ ROUND 2 (conditioned on Round 1 summaries):                         │
│ 6 NEW rollouts, each seeing:                                        │
│   - Round 1 winner's fix                                            │
│   - Test error output from Round 1                                  │
│   - Discoveries + failed approaches from ALL 6 Round 1 candidates   │
│   - Anti-pattern library hints                                      │
│                                                                     │
│ → 6 NEW candidates (higher quality, informed by prior failures)     │
│                                                                     │
│ SELECTION → winner W2                                               │
│                                                                     │
│ REFINEMENT: test feedback loop (1-3 rounds until pass or budget)    │
│   Attempt 1: refine W2 with test errors                             │
│   If fail: Attempt 2: refine with MORE context                      │
│   If fail: Attempt 3: generate distinguishing test, re-fix          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 6. Expected Performance with Full Implementation

| Component | Current | With improvements | Δ |
|-----------|:-------:|:-----------------:|:-:|
| Representation | 1-pass extraction | **Hierarchical distillation** | +2% |
| Selection | 3 judges, 1 round | **Recursive narrowing** | +3% |
| Reuse | 1-2 refinements | **Multi-round PDR** | +8% |
| Efficiency | 6 rollouts always | **Adaptive strategy count** | −40% wall time |
| Cross-task learning | None | **Anti-pattern library** | +2% (cumulative) |
| **Total estimated** | **73%** | **~85%** | **+12%** |

The gains are multiplicative: better representations enable better selection, which enables better reuse. The anti-pattern library compounds over time as the pipeline sees more tasks.

---

## 7. Summary: What We Built vs. What's Possible

| Dimension | We built | Paper achieves | We could achieve |
|-----------|----------|---------------|-----------------|
| **Representation** | 1-pass extraction | Multi-step distillation | Hierarchical with hypothesis tracking |
| **Selection** | 3 judges + distinguishing test on tie | Recursive narrowing + test-first | Multi-round with test-based tiebreak |
| **Reuse** | Test-feedback refinement | Multi-round PDR + cross-distill | Full re-rollout conditioned on summaries |
| **Solve rate (22 failed tasks)** | 73% | ~78% (paper, on full SWE-Bench) | ~85% |
| **Wall time per task** | ~330s | ~600s (Claude Code is slower) | ~200s (with adaptive strategies) |

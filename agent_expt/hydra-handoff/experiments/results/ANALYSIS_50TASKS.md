# 50-Task Multi-Agent Analysis

## Summary Statistics

| Metric | Single-Call | Multi-Agent | Δ |
|--------|:-----------:|:-----------:|:-:|
| **Solved** | **28/50 (56%)** | **33/50 (66%)** | **+10%** |
| Avg wall time | 63s | 231s | 3.7× |
| Avg oracle pass@6 | — | 5.0/6 | — |

## Category 1: Single FAIL + Multi WIN (5 tasks)

These are the tasks where multi-agent provides value over single-call.

| Task | Bug type | Single | Multi best | Winning strategy | Oracle |
|------|----------|--------|------------|-----------------|--------|
| N19_operator_precedence | Boolean precedence | 4/6 | **6/6** | tdd | 1/6 |
| extra-04 (CSV quoted commas) | CSV parsing | 3/6 | **6/6** | alternative | 2/6 |
| extra-08 (BankAccount validation) | Property setter | 3/4 | **4/4** | tdd | 1/6 |
| extra-09 (Factory singleton) | Instance reuse | 2/3 | **3/3** | alternative | 1/6 |
| extra-20 (JSON serializer) | String escaping | 0/2 (syntax error) | **7/7** | alternative | 2/6 |

### How multi-agent wins

**The mechanism is strategy diversity, not majority voting.** In every case, only 1-2 out of 6 strategies found the fix. The other 4-5 failed for various reasons:
- **token budget exhaustion** (reasoning consumed all 8,192 tokens, content=null)
- **syntax errors** in generated code
- **semantic errors** (wrong fix approach)

The winning strategy varied per task - tdd won for logic bugs (N19, extra-08), alternative won for data-format bugs (extra-04, extra-09, extra-20). **No single strategy is universally best.**

### How to boost further

1. **Dynamic strategy selection**: If we knew the bug type (logic vs data vs parsing), we could select the best 2-3 strategies instead of 6, saving time while keeping diversity.
2. **Strategy ensembling with voting**: When multiple strategies produce valid fixes, compare them via deterministic tests (not LLM judges) and pick the one passing the most tests.
3. **Reduce token budget for verbose strategies**: adversarial and alternative consistently produce long reasoning (15K-30K chars). Setting max_tokens=4096 for these strategies forces them to be more concise.

## Category 2: Both WIN (28 tasks)

Efficiency comparison across all 28 tasks where both approaches succeeded:

### Wall time analysis

| Metric | Value |
|--------|-------|
| Avg single-call time | **63s** |
| Avg multi-agent wall time | **231s** |
| Ratio | **3.7×** |
| Min ratio (most efficient) | 1.8× (async_race) |
| Max ratio (least efficient) | 8.3× (extra-01) |
| Strategies hitting 300s timeout | ~3-4 per task on average |

### Why multi-agent is 3.7× slower

The wall time is dominated by the **slowest** strategy, not the average. Typical breakdown:
- tdd: ~40-80s (fast, focused reasoning)
- root-cause: ~50-100s
- minimal: ~60-120s
- architecture: ~60-150s
- alternative: ~150-300s (often hits timeout)
- adversarial: ~200-300s (often hits timeout)

**adversarial and alternative are the bottleneck** — they take 3-5× longer than tdd/root-cause, and on hard tasks they hit the 300s timeout nearly every time.

### How to improve efficiency without losing correctness

**Option A: Drop adversarial + alternative → use 4 strategies**
- Predicted wall time: ~120s (2× single, down from 3.7×)
- Oracle pass@4: predicted ~4.0/6 (losing some diversity)
- Net: 40% faster, oracle drops by ~1

**Option B: Adaptive strategy timeout** 
- Set per-strategy timeouts: tdd/root-cause/minimal get 120s, adversarial/alternative get 60s
- This caps wall time at ~120s while still sampling all 6 strategies
- Risk: adversarial/alternative often produce valid fixes when they work (extra-04, extra-09, extra-20)

**Option C: Cascade execution**
- Run tdd + root-cause + minimal first (fast trio)
- If none pass all tests, THEN dispatch adversarial + alternative (slow duo)
- Wall time: 80s (fast trio) or 200s (all five)
- Estimated oracle: ~5.5/6 (rarely need the slow duo)

### Strategy speed ranking (from fastest to slowest)

| Strategy | Avg time | Share of wins | Avg reasoning length |
|----------|----------|--------------|-------------------|
| tdd | ~60s | **~35%** | ~5K chars |
| root-cause | ~80s | ~20% | ~7K chars |
| minimal | ~90s | ~20% | ~8K chars |
| architecture | ~100s | ~10% | ~9K chars |
| alternative | ~160s | ~10% | ~12K chars |
| adversarial | ~200s | ~5% | ~18K chars |

## Category 3: Both FAIL (17 tasks)

Root cause analysis of why multi-agent failed.

### Failure mode breakdown

| Failure mode | Count | Tasks | Root cause |
|-------------|-------|-------|------------|
| **content=null** (timeout) | ~9 tasks | N13, N18, extra-03, extra-13, extra-17, extra-30 + more | Model consumes all tokens on reasoning, produces no code |
| **Wrong fix (partial pass)** | ~6 tasks | H4, N11, N12, N14, N17, extra-07, extra-15, extra-23, extra-25, extra-26 | Model finds the wrong fix or makes semantic error |
| **Syntax error** | ~2 tasks | extra-19, extra-30 (some candidates) | Generated code has Python syntax errors |

### Deep dive: why these 17 tasks failed

The failures fall into two categories:

**A. Model capability limits (≈10 tasks)**
Tasks requiring specific Python knowledge that Qwen3.6-27B doesn't have:
- N12 (mutable defaults: `def f(x=[])`): Model keeps `x=[]`
- N13 (exception chaining: `raise from`): Model uses bare `raise`
- N18 (email validation with TLD check): Model adds basic checks but not TLD
- extra-15 (thread-safe counter): Model uses `self.value += 1` which is still not atomic
- extra-25 (fibonacci memoization): Model adds memoization but it's buggy

These are **knowledge gaps** — no amount of prompt engineering will fix them. The model simply doesn't know these patterns well enough.

**B. Token budget failures (≈7 tasks)**
- N13, N18, extra-03, extra-13, extra-17, extra-30: Most/all strategies return `0/0` with reasoning length = 0
- This means ALL API calls timed out (hit 300s) or produced `content=null`
- These tasks tend to have large source files or complex problem descriptions that trigger extremely long reasoning (30K+ chars)

### How to address both-fail tasks

**For capability gaps (A):**
1. Add a **verification loop**: When the model produces a fix, run the tests. If they fail, give the error message back to the model and ask for a revised fix. This could be done as a refinement step within the multi-agent pipeline.
2. **Few-shot examples**: Include examples of the correct pattern (e.g., `def f(x=None):`) in the prompt for known difficult patterns.
3. **External knowledge retrieval**: For hard patterns like exception chaining, include a brief explanation of the correct approach in the prompt.

**For token budget failures (B):**
1. **Increase max_tokens to 16384** for complex tasks (currently 8192). The extra reasoning budget prevents content=null.
2. **Detect content=null and retry** with higher max_tokens or a different prompt that discourages long reasoning.
3. **Shorter system prompts**: The system prompt adds 5-15 tokens that contribute to reasoning length. Use ultra-concise prompts.

## Recommended Multi-Agent Optimizations

### Tier 1: Immediate wins (low effort, high impact)

1. **Drop adversarial strategy** — slowest (avg 200s), lowest win rate (~5%), and rarely produces the unique winning fix
2. **Set per-strategy max_tokens**: tdd/root-cause/minimal = 8192, adversarial/alternative = 4096 (forces conciseness)
3. **Add content=null detection and retry**: If content is null, retry with doubled max_tokens before marking as failed

### Tier 2: Architecture changes (moderate effort)

4. **Cascade execution**: Run 3 fast strategies first, dispatch 2 slow only if needed
5. **Strategy routing**: Classify task by bug type (from problem description), select matching strategies
6. **Verification-feedback loop**: When tests fail, feed error output back for refinement

### Tier 3: Research directions (high effort)

7. **Ensemble voting across strategies**: Use deterministic test results (not LLM judges) to select the best fix across strategies
8. **Adaptive token budget**: Monitor reasoning length during generation, terminate reasoning when it exceeds a threshold
9. **Few-shot prompting for hard patterns**: Inject known-correct code snippets for frequent failure patterns

### Predicted impact

| Optimization | Est. solve rate | Est. wall time | Oracle pass |
|-------------|:-:|:-:|:-:|
| Baseline (current) | 66% | 231s | 5.0/6 |
| + Drop adversarial | 65% | **180s** (-22%) | 4.8/6 |
| + Cascade (3→2→1) | **68%** (+2%) | 120s (-48%) | 5.2/6 |
| + Retry on content=null | **72%** (+6%) | 140s | 5.5/6 |
| + Verification loop | **78%** (+12%) | 180s | 5.8/6 |
| + max_tokens=16384 | **80%** (+14%) | 300s | 6.0/6 |

# Representation for Coding Tasks & Software Development with Multi-Agent Pipeline

## 1. How We Represent Coding Tasks

The pipeline uses a **two-layer representation**:

### Layer 1: The Task Packet (input)
```
{
  "task": "Fix the pagination off-by-one bug",
  "source_code": "def get_page(...): ...",
  "test_code": "def test_first_page(): ...",
  "failing_tests": ["test_first_page", "test_second_page"]
}
```

### Layer 2: The Trajectory Summary (output from each strategy)
```
{
  "strategy": "tdd",
  "root_cause_hypotheses": ["off-by-one in start index"],
  "evidence_for": ["page 1 returns items[5:10] instead of [0:5]"],
  "evidence_against": [],
  "useful_discoveries": ["formula is page*per_page not (page-1)*per_page"],
  "failed_approaches": ["tried fixing end index first"]
}
```

### Why text summaries hurt (our finding):
Less effective → `[hypotheses text] || [discoveries text]`
More effective → `[original source code] || [WRONG fix attempt code] || [test errors]`

The model learns more from seeing **what it did wrong** (the actual broken code) than from reading a text summary of what it did wrong. This is why the improved pipeline (73%) outperformed PDR (33%).

## 2. Applying to Software Development

For **new feature development** (not bug fixing), the representation changes:

```
Bug fixing:                       Feature development:
┌──────────────────────┐          ┌──────────────────────┐
│ task: "fix bug"      │          │ task: "add feature"  │
│ source: broken code  │          │ source: skeleton     │
│ test: failing test   │          │ test: new test       │
│ fix: repair code     │          │ fix: implement       │
└──────────────────────┘          └──────────────────────┘
```

### Key difference: The "bug" is missing code

In bug fixing, the source has a defect to repair.
In feature development, the "bug" is that the code doesn't exist yet.

The pipeline handles both identically:
1. **Test defines "done"** → same in both cases
2. **Source is what the model edits** → empty skeleton vs broken code
3. **Hard gate: tests must pass** → same

### Real-world dev task comparison

Let's compare two tasks to show the pattern:

**Bug fixing example (works):**
```
Input:  str_concat: `def greet(name): return 'Hello ' + name`
Test:   `assert greet(123) == 'Hello 123'` → FAILS (TypeError)
Pipeline: 3 agents → 1 fixes it → Done
```

**Feature dev example (same pipeline):**
```
Input:  email_service: `class EmailSender: pass`
Test:   `sender = EmailSender(); sender.send("a@b.com", "Hi")` → FAILS (no send method)
Pipeline: 3 agents → 1 implements it → Done
```

### What we need for a challenging dev task

The task must be:
1. **Too complex for single-call** (model can't implement it in one shot)
2. **Feasible for multi-agent** (different strategies explore different approaches)
3. **Verifiable** (has tests that define "done")

Ideal candidate: **A multi-file feature where different strategies would choose different architectures.** For example: building a URL shortener where tdd picks one API design and architecture picks another, and the ensemble converges on the better one.

## 3. Finding the Right Dev Task

Criteria for a task that shows multi-agent advantage:

| Criterion | Bug fixing | Feature dev |
|-----------|-----------|-------------|
| Single-call success rate | ~56% (measured) | ~40% (estimated) |
| Multi-agent advantage | +10% (measured) | +20-30% (estimated) |
| Why larger delta? | Bug has single fix | Feature has many designs; diversity helps more |

Feature development has MORE design freedom, so strategy diversity matters MORE. Each strategy may implement the same feature completely differently, and the ensemble can pick the best design.

### Real-world task candidates:

1. **REST API endpoint** with validation, error handling, and response formatting
2. **Data pipeline** with transformation, filtering, and aggregation stages
3. **Authentication middleware** with token verification, user lookup, and session management

These tasks have high design variance — different strategies produce meaningfully different implementations.

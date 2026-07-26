# Using the Optimized Multi-Agent Pipeline for Software Development

This document describes how to leverage the HydraCode-6 pipeline for **new feature development** and **product building** — beyond bug fixing.

## 1. Core Insight: The Pipeline Works for Any Testable Specification

The pipeline is agnostic to whether you're fixing a bug or building a feature. The only requirement is:

> **You need a test that defines "done".**

For bug fixing, the test already exists (it fails on the buggy code).  
For feature development, **you write the test first** (it fails because the feature doesn't exist).

```
┌──────────────────────────────────────────────────────────────┐
│                     USER PROVIDES                            │
│  ┌─────────────────┐  ┌──────────────────────────────────┐   │
│  │ Task Description │  │  Failing Tests (define the spec) │   │
│  │ "Build a user    │  │  def test_create_user(): ...    │   │
│  │  authentication  │  │  def test_login(): ...          │   │
│  │  system"         │  │  def test_token_refresh(): ...  │   │
│  └─────────────────┘  └──────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  PHASE 1: 3×    │
                    │  Parallel Agents │
                    │  (tdd, root-    │
                    │  cause, minimal)│
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Any pass?      │──YES──→ Done (~60s)
                    └────────┬────────┘
                             │ NO
                    ┌────────▼────────┐
                    │  PHASE 2: 3×    │
                    │  More Agents    │
                    │  (architecture, │
                    │  adversarial,   │
                    │  alternative)   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Any pass?      │──YES──→ Done (~150s)
                    └────────┬────────┘
                             │ NO
                    ┌────────▼────────┐
                    │  PHASE 3:       │
                    │  Refinement     │
                    │  (test feedback │
                    │  + anti-        │
                    │  patterns)      │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Pass now?      │──YES──→ Done (~250s)
                    │  or report gaps │
                    └─────────────────┘
```

## 2. Development Workflow Instructions

### Step 1: Define the feature as a failing test

```python
# tests/test_user_auth.py
def test_create_user():
    """A new user can be created with email + password."""
    service = UserService()
    user = service.create_user("alice@example.com", "secure_pass123")
    assert user.email == "alice@example.com"
    assert user.verify_password("secure_pass123") is True

def test_duplicate_email_raises():
    """Creating a user with an existing email raises."""
    service = UserService()
    service.create_user("alice@example.com", "pass1")
    with pytest.raises(DuplicateEmailError):
        service.create_user("alice@example.com", "pass2")
```

### Step 2: Provide a skeleton

```python
# app/user_service.py
class UserService:
    def create_user(self, email, password):
        pass

class DuplicateEmailError(Exception):
    pass
```

### Step 3: Run the pipeline

```bash
hydra-code run \
  --task "Build UserService.create_user with email/password auth, duplicate detection, and password hashing" \
  --test tests/test_user_auth.py \
  --source app/user_service.py \
  --local  # uses local Qwen instead of Claude
```

### Step 4: The pipeline does the rest

1. **Phase 1**: 3 agents try to implement the feature (tdd reads tests first, root-cause traces requirements, minimal writes the simplest implementation)
2. **Phase 2**: If all 3 fail, 3 more agents try with different approaches
3. **Phase 3**: The best attempt is refined with test-feedback

## 3. Example: Building a Todo API

### Tests (what you write):

```python
# tests/test_todo.py
def test_create_todo():
    api = TodoAPI()
    todo = api.create("Buy milk", user_id=1)
    assert todo.title == "Buy milk"
    assert todo.completed is False

def test_list_by_user():
    api = TodoAPI()
    api.create("Task 1", user_id=1)
    api.create("Task 2", user_id=2)
    assert len(api.list(user_id=1)) == 1

def test_mark_complete():
    api = TodoAPI()
    todo = api.create("Task", user_id=1)
    api.complete(todo.id)
    assert api.get(todo.id).completed is True
```

### Skeleton (what you provide):

```python
# app/todo.py
class TodoAPI:
    def create(self, title, user_id):
        pass
    def list(self, user_id):
        pass
    def complete(self, todo_id):
        pass
    def get(self, todo_id):
        pass
```

### Pipeline result (what the model produces):

```python
# app/todo.py (after Phase 1 — tdd strategy wins)
class Todo:
    def __init__(self, id, title, user_id, completed=False):
        self.id = id
        self.title = title
        self.user_id = user_id
        self.completed = completed

class TodoAPI:
    def __init__(self):
        self._todos = {}
        self._next_id = 1

    def create(self, title, user_id):
        todo = Todo(self._next_id, title, user_id)
        self._todos[todo.id] = todo
        self._next_id += 1
        return todo

    def list(self, user_id):
        return [t for t in self._todos.values() if t.user_id == user_id]

    def complete(self, todo_id):
        self._todos[todo_id].completed = True

    def get(self, todo_id):
        return self._todos.get(todo_id)
```

## 4. When to Use Each Phase

| Scenario | Phase | Expected time | Success rate |
|----------|-------|:-------------:|:------------:|
| Simple feature (add method) | 1 | ~30s | ~95% |
| Medium feature (new class) | 1-2 | ~60s | ~85% |
| Complex feature (multi-class) | 2-3 | ~120s | ~70% |
| New product (multi-file) | 3 + rounds | ~300s | ~50% |

## 5. Product Development Strategy

For building entire products (not just features), use the pipeline in **layered sprints**:

```
Sprint 1: Core data model + basic CRUD
  └─ Pipeline: 3 parallel agents, 1 refinement round
      
Sprint 2: Business logic layer
  └─ Pipeline: 3 parallel agents, tests for each business rule
  
Sprint 3: API/interface layer
  └─ Pipeline: 3 parallel agents, integration tests
  
Sprint 4: Polish + edge cases
  └─ Pipeline: 6 parallel agents (adversarial helps here)
```

Each sprint's output is:
1. The generated code (passing all tests)
2. A trajectory summary (what was tried, what worked, what failed)
3. Anti-patterns detected (common mistakes avoided)

## 6. Comparison: Bug Fixing vs Feature Development

| Aspect | Bug fixing | Feature dev |
|--------|-----------|-------------|
| **Tests** | Already exist (failing) | You write them (failing) |
| **Source** | Existing code with bug | Skeleton or empty file |
| **Hard gates** | Existing tests must pass | New tests must pass |
| **Best strategy** | root-cause, tdd | tdd, architecture |
| **Refinement** | Test-feedback loop | Requirement check |
| **Multi-round** | Rarely needed | Often needed |

## 7. Scaling to Larger Products

For a full product (e.g., SaaS backend with auth + API + database):

```
┌─ Step 1: Architecture agent ─────────────────────────────┐
│  Prompt: "Design the architecture for a SaaS app with    │
│           user auth, payment processing, and admin API"   │
│  Output: architecture.md (data models, API routes, deps)  │
└──────────────────────────────────────────────────────────┘
                            │
┌─ Step 2: Generate tests per module ──────────────────────┐
│  Pipeline: For each module (auth, payments, admin)       │
│  Input: architecture.md + module spec                    │
│  Output: test_module.py (failing tests)                  │
└──────────────────────────────────────────────────────────┘
                            │
┌─ Step 3: Implement each module ──────────────────────────┐
│  Pipeline: For each test file, run full pipeline        │
│  Phase 1: 3 agents → pass? → next module                 │
│  Phase 2: 3 more → pass? → next                          │
│  Phase 3: Refine → pass? → next                          │
│  Output: module.py (passing all tests)                   │
└──────────────────────────────────────────────────────────┘
                            │
┌─ Step 4: Integration tests ─────────────────────────────┐
│  Pipeline: Full 6-strategy run on integration tests     │
│  Anti-pattern library checks for security, perf issues  │
│  Output: All tests passing, anti-pattern report          │
└──────────────────────────────────────────────────────────┘
```

## 8. Key Advantages Over Single-Agent Development

| Aspect | Single agent | Multi-agent pipeline |
|--------|-------------|-------------------|
| **Coverage** | 1 approach | 6 diverse approaches |
| **Debugging** | Blind | Test-feedback refinement |
| **Edge cases** | Missed | Adversarial strategy finds them |
| **Architecture** | Local optimization | Architectural strategy considers big picture |
| **Robustness** | Brittle | Hard gates prevent regressions |
| **Speed** | Fast (~30s) | Efficient (3 agents first, 3 more if needed) |

## 9. Limitations

1. **Model capability ceiling**: The pipeline can't overcome the base model's knowledge gaps. For tasks requiring specific domain expertise (e.g., cryptography, audio processing), the model may fail regardless of strategy diversity.

2. **Test quality matters**: The pipeline is only as good as the tests you write. Missing tests → missing features. The pipeline's hard gates check "do all tests pass?" not "is the implementation complete?"

3. **Multi-file coordination**: The current pipeline works best for single-file changes. Multi-file features require the architecture strategy to identify all affected files, which is less reliable.

4. **Stateful evaluation**: Features that require database setup, external services, or complex state cannot be evaluated purely through unit tests.

#!/usr/bin/env python3
"""Demonstrate the full downstream pipeline: evaluation, tournament, refinement.

This shows the value the user identified — the real pipeline is not just rollouts,
but the feedback loop that refines candidates.

We take the 5 tasks where multi-agent barely won (oracle 1/6) and show how
the tournament + refinement steps could turn a weak win into a robust fix.
"""

import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hydra-code/src"))
from hydra_code.models import CandidateResult, CandidateRole, CandidateStatus, JudgeResult, TournamentResult, TrajectorySummary, RefinementPacket, RefineMode, ScoreWeights
from hydra_code.tournament import TournamentSelector
from hydra_code.local_judge import LocalJudge
from hydra_code.refinement import build_refinement_packet, build_refinement_prompt

API_BASE = "http://localhost:8000/v1"
API_MODEL = "qwen"

def call_qwen(prompt, max_tokens=8192, temperature=0.3):
    import httpx
    payload = {"model": API_MODEL, "messages": [
        {"role": "system", "content": "You fix bugs. Return ONLY the corrected file."},
        {"role": "user", "content": prompt},
    ], "max_tokens": max_tokens, "temperature": temperature}
    try:
        resp = httpx.post(f"{API_BASE}/chat/completions", json=payload, timeout=300)
        resp.raise_for_status()
        d = resp.json()
        c = d["choices"][0]["message"]
        content = c.get("content") or ""
        reasoning = c.get("reasoning") or ""
        return content, reasoning
    except Exception as e:
        return "", f"error: {e}"


def extract_code(text):
    in_code, lines = False, []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```python"): in_code=True; continue
        if s.startswith("```") and in_code: break
        if in_code: lines.append(line)
    return "\n".join(lines) if lines else text


# Tasks where multi-agent barely won (oracle 1/6) — perfect for demonstrating refinement
DEMO_TASKS = [
    {
        "name": "N19_operator_precedence",
        "fixture": "swebench-n-19",
        "source": "access.py",
        "test": "test_access.py",
        "n_tests": 6,
        "bug": "Boolean expression `is_admin or is_owner and action in permissions` grouped wrong",
        "task_desc": "Fix the operator precedence bug in can_access(). The condition should give admin unconditional access, and non-admin owners access only if they have the required permission.",
    },
    {
        "name": "extra-08 (BankAccount)",
        "fixture": "swebench-extra-08",
        "source": "account.py",
        "test": "test_account.py",
        "n_tests": 4,
        "bug": "Property setter doesn't validate negative balance",
        "task_desc": "Fix BankAccount.balance setter to reject negative values. The setter should raise ValueError when a negative balance is assigned.",
    },
    {
        "name": "extra-09 (Factory singleton)",
        "fixture": "swebench-extra-09",
        "source": "factory.py",
        "test": "test_factory.py",
        "n_tests": 3,
        "bug": "Factory returns same connection for different configs",
        "task_desc": "Fix get_connection() so different configs return different Connection instances. Currently the factory caches globally by first call.",
    },
]

BASE = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures"
OUT = Path("experiments/results/downstream_demo")
OUT.mkdir(parents=True, exist_ok=True)


def main():
    print("=" * 78)
    print("  DOWNSTREAM PIPELINE DEMO: Evaluation → Tournament → Refinement")
    print("  Showing the value ADDED by pipeline steps after rollouts")
    print("=" * 78)

    r = subprocess.run([sys.executable, "-c", """
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/v1/models",timeout=5) as resp:
    print(json.loads(resp.read())["data"][0]["id"])
    """], capture_output=True, text=True, timeout=10)
    print(f"  Server: {r.stdout.strip()}\n")

    for task in DEMO_TASKS:
        name = task["name"]
        fixture_dir = BASE / task["fixture"]
        src_file = fixture_dir / task["source"]
        test_file = fixture_dir / task["test"]

        print(f"{'='*78}")
        print(f"  TASK: {name}")
        print(f"  Bug: {task['bug']}")
        print(f"{'='*78}")

        # Step 1: Simulate 6 candidates with varying quality
        # We use our 50-task data as the "rollout outputs"
        # But we also run a FRESH set of 6 strategies via API to get real data
        print(f"\n  Phase 1: Generating 6 candidate fixes...")

        strategies = [
            ("tdd", "Read the test first."),
            ("root-cause", "Find root cause."),
            ("minimal", "Smallest change."),
            ("architecture", "Full API surface."),
            ("adversarial", "Edge cases."),
            ("alternative", "Different approach."),
        ]

        candidates = {}
        for sn, sp in strategies:
            cid = f"{name}_{sn}"
            src_code = src_file.read_text()

            # Call API
            prompt = f"{sp}\n\nFix the bug in {task['source']}. Return ONLY the corrected code.\n\n```python\n{src_code}\n```"
            content, reasoning = call_qwen(prompt)
            code = extract_code(content) or extract_code(reasoning)

            # Test in temp dir
            with tempfile.TemporaryDirectory() as td:
                w = Path(td)
                shutil.copy2(src_file, w / task["source"])
                shutil.copy2(test_file, w / task["test"])
                (w / task["source"]).write_text(code)
                r = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q", task["test"], "--tb=no"],
                    cwd=w, capture_output=True, text=True, timeout=15,
                )
                p = f = 0
                for line in r.stdout.split("\n"):
                    for i, t in enumerate(line.replace(",","").replace(".","").split()):
                        if t=="passed":
                            try: p=int(line.split()[i-1])
                            except: pass
                        if t=="failed":
                            try: f=int(line.split()[i-1])
                            except: pass

                # Check syntax
                has_syntax = None
                try: compile(code, task["source"], "exec")
                except SyntaxError as e: has_syntax = str(e)

                success = r.returncode == 0
                passed = p
                failed = f if f else (r.returncode if r.returncode and not has_syntax else 0)

            candidates[cid] = {
                "passed": passed, "failed": failed, "success": success,
                "syntax_error": has_syntax, "approach": sn,
                "code": code,
            }
            mark = "✓" if success else ("⚡" if has_syntax else "✗")
            print(f"    [{mark}] {sn:<12}: {passed}/{passed+failed}  "
                  f"{'syntax err' if has_syntax else ''}")

        # Step 2: Scoring
        print(f"\n  Phase 2: Deterministic scoring + hard gates...")
        scores = {}
        hard_gates = {}
        for cid, c in candidates.items():
            score = 0
            if c["syntax_error"]:
                score = -10
                hard_gates[cid] = False
            elif c["success"]:
                score = c["passed"] / (c["passed"] + c["failed"]) * 100
                hard_gates[cid] = True
            else:
                score = max(0, c["passed"] / (c["passed"] + c["failed"]) * 50)
                hard_gates[cid] = False
            scores[cid] = round(score, 1)

        print(f"    Scores: {json.dumps(scores, indent=6)}")
        print(f"    Hard gates passed: {sum(1 for v in hard_gates.values() if v)}/6")

        # Step 3: Tournament
        print(f"\n  Phase 3: Tournament voting (local Qwen as judge)...")
        judge = LocalJudge()
        selector = TournamentSelector(judges=[judge], judges_per_group=1)

        context = {
            "scores": scores,
            "hard_gates": hard_gates,
            "candidate_descriptions": {
                cid: f"Approach: {c['approach']}. Tests: {c['passed']}/{c['passed']+c['failed']}."
                for cid, c in candidates.items()
            },
        }

        candidate_ids = sorted(candidates.keys())
        tournament_result = selector.select(candidate_ids, task["task_desc"], context)
        winner_id = tournament_result.winner

        print(f"    Winner: {winner_id}")
        print(f"    Winner tests: {candidates[winner_id]['passed']}/{candidates[winner_id]['passed']+candidates[winner_id]['failed']}")
        print(f"    Tie: {tournament_result.is_tie}")

        if not winner_id or not candidates[winner_id]["success"]:
            print(f"    ✗ Tournament didn't improve — running refinement anyway...")
            winner_id = max(candidates, key=lambda c: (candidates[c]["passed"], -candidates[c]["failed"]))

        # Step 4: Refinement (the key step the user identified!)
        print(f"\n  Phase 4: Refinement — verification-feedback loop...")
        print(f"    Feeding test failures back to model for refinement...")

        winner = candidates[winner_id]
        if winner["success"]:
            print(f"    ✓ Winner already passes all tests. No refinement needed.")
            print(f"    (In real pipeline, refinement still runs for robustness)")
            refined_code = winner["code"]
        else:
            # Build refinement prompt with failing test feedback
            with tempfile.TemporaryDirectory() as td:
                w = Path(td)
                shutil.copy2(src_file, w / task["source"])
                shutil.copy2(test_file, w / task["test"])
                (w / task["source"]).write_text(winner["code"])
                r = subprocess.run(
                    [sys.executable, "-m", "pytest", "-v", task["test"], "--tb=long"],
                    cwd=w, capture_output=True, text=True, timeout=15,
                )
                test_feedback = r.stdout[-1000:] + "\n" + r.stderr[-500:]

            # Refinement prompt: original bug + failing test output + ask for fix
            src_code = src_file.read_text()
            refinement_prompt = f"""
The previous fix for this bug was INCORRECT. Here is the error from running tests:

```
{test_feedback}
```

Original code:
```python
{src_code}
```

Your previous fix:
```python
{winner['code']}
```

Fix the bug correctly this time, avoiding the mistakes that caused the test failures.
Return ONLY the corrected code.
"""
            print(f"    Refinement attempt 1...")
            content, reasoning = call_qwen(refinement_prompt, max_tokens=8192)
            refined_code = extract_code(content) or extract_code(reasoning)

            # Test refined code
            with tempfile.TemporaryDirectory() as td:
                w = Path(td)
                shutil.copy2(src_file, w / task["source"])
                shutil.copy2(test_file, w / task["test"])
                (w / task["source"]).write_text(refined_code)
                r = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q", task["test"], "--tb=no"],
                    cwd=w, capture_output=True, text=True, timeout=15,
                )
                refined_p = refined_f = 0
                for line in r.stdout.split("\n"):
                    for i, t in enumerate(line.replace(",","").replace(".","").split()):
                        if t=="passed":
                            try: refined_p=int(line.split()[i-1])
                            except: pass
                        if t=="failed":
                            try: refined_f=int(line.split()[i-1])
                            except: pass
                refined_success = r.returncode == 0

            print(f"    Refined: {'PASS' if refined_success else 'FAIL'} ({refined_p}/{refined_p+refined_f})")

            if not refined_success:
                # Second refinement attempt with MORE context
                print(f"    Refinement attempt 2 (with more context)...")
                r2_content, r2_reasoning = call_qwen(refinement_prompt + "\n\nIMPORTANT: Look at the test carefully. The test expects specific behavior. Fix the function to match the test expectations exactly.", max_tokens=8192)
                refined_code = extract_code(r2_content) or extract_code(r2_reasoning)

                with tempfile.TemporaryDirectory() as td:
                    w = Path(td)
                    shutil.copy2(src_file, w / task["source"])
                    shutil.copy2(test_file, w / task["test"])
                    (w / task["source"]).write_text(refined_code)
                    r = subprocess.run(
                        [sys.executable, "-m", "pytest", "-q", task["test"], "--tb=no"],
                        cwd=w, capture_output=True, text=True, timeout=15,
                    )
                    refined_p2 = refined_f2 = 0
                    for line in r.stdout.split("\n"):
                        for i, t in enumerate(line.replace(",","").replace(".","").split()):
                            if t=="passed":
                                try: refined_p2=int(line.split()[i-1])
                                except: pass
                            if t=="failed":
                                try: refined_f2=int(line.split()[i-1])
                                except: pass
                    refined_success = r.returncode == 0
                print(f"    Refined (attempt 2): {'PASS' if refined_success else 'FAIL'} ({refined_p2}/{refined_p2+refined_f2})")

        # Summary for this task
        all_results = {cid: {"passed": c["passed"], "failed": c["failed"], "success": c["success"]} for cid, c in candidates.items()}
        best_raw = max(candidates.values(), key=lambda c: (c["passed"], -c["failed"]))
        print(f"\n  {'─'*70}")
        print(f"  TASK RESULT: {name}")
        print(f"  {'─'*70}")
        print(f"  Raw best candidate: {best_raw['passed']}/{best_raw['passed']+best_raw['failed']}")
        if winner:
            print(f"  Tournament winner:  {candidates[winner_id]['passed']}/{candidates[winner_id]['passed']+candidates[winner_id]['failed']}")
        # Track refinement results
        ref_result = {"success": False, "passed": 0, "failed": 0}
        if 'refined_success' in locals():
            ref_result["success"] = refined_success
            if 'refined_p2' in locals():
                ref_result["passed"] = refined_p2
                ref_result["failed"] = refined_f2
            elif 'refined_p' in locals():
                ref_result["passed"] = refined_p
                ref_result["failed"] = refined_f
            else:
                ref_result["passed"] = candidates[winner_id]["passed"]
                ref_result["failed"] = candidates[winner_id]["failed"]
            print(f"  After refinement:   {ref_result['passed']}/{ref_result['passed']+ref_result['failed']}")
        print()

        # Save detailed results
        task_results = {
            "name": name,
            "candidates": {cid: {"approach": c["approach"], "passed": c["passed"], "failed": c["failed"],
                                  "success": c["success"], "syntax_error": c.get("syntax_error")} for cid, c in candidates.items()},
            "scores": scores,
            "tournament_winner": winner_id,
            "tournament_tie": tournament_result.is_tie,
            "refinement": ref_result,
        }
        (OUT / f"{name.replace(' ','_').replace('(','').replace(')','')}.json").write_text(
            json.dumps(task_results, indent=2)
        )

    print(f"{'='*78}")
    print("  DEMO COMPLETE — Results saved to experiments/results/downstream_demo/")
    print(f"{'='*78}")


if __name__ == "__main__":
    main()

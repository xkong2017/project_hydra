#!/usr/bin/env python3
"""Improved pipeline: trajectory extraction → 3-judge tournament → test-feedback refinement.
Runs against all 50 tasks to measure gain over baseline.
"""

import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API = "http://localhost:8000/v1/chat/completions"
MODEL = "qwen"
MAX_TOKENS = 8192
TIMEOUT = 300
BASE = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures"
OUT_DIR = Path("experiments/results")
CHECKPOINT = OUT_DIR / "improved_results.json"

STRATEGIES = [
    ("tdd", "Read the tests first."),
    ("root-cause", "Trace the root cause."),
    ("minimal", "Smallest change."),
    ("architecture", "Full API surface."),
    ("adversarial", "Edge cases."),
    ("alternative", "Different approach."),
]

# All 50 task mappings
TASK_NAMES = {
    "paginator":"pagination","requests_6028":"requests_6028_buggy","cache_isolation":"cache_isolation_buggy",
    "async_race":"async_race_buggy","parser":"parser_buggy",
    "H1_variable_scope":"swebench-hard-1","H2_cache_stale":"swebench-hard-2","H3_shared_state":"swebench-hard-3",
    "H4_exception_silence":"swebench-hard-4","H5_proxy_delegation":"swebench-hard-5",
    "N11_encoding":"swebench-n-11","N12_mutable_default":"swebench-n-12","N13_exception_chaining":"swebench-n-13",
    "N14_decimal_precision":"swebench-n-14","N15_config_override":"swebench-n-15","N16_recursive_depth":"swebench-n-16",
    "N17_string_escape":"swebench-n-17","N18_input_validation":"swebench-n-18",
    "N19_operator_precedence":"swebench-n-19","N20_shallow_copy":"swebench-n-20",
}
for i in range(1,31): TASK_NAMES[f"extra-{i:02d}"] = f"swebench-extra-{i:02d}"

def resolve(fn):
    d = TASK_NAMES.get(fn, fn)
    fdir = BASE / d
    if not fdir.exists():
        for p in BASE.iterdir():
            if p.is_dir() and (fn in p.name or p.name.endswith(fn.split("_")[0])):
                return p.name, p
        return d, fdir
    return d, fdir

def get_files(fdir):
    pyfiles = sorted(fdir.glob("*.py"))
    src = test = None
    for f in pyfiles:
        if f.name.startswith("test_"): test = f.name
        elif not src: src = f.name
    return src, test

def call_qwen(prompt):
    payload = {"model": MODEL, "messages": [
        {"role": "system", "content": "You fix bugs. Return ONLY the corrected file inside ```python."},
        {"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS, "temperature": 0.3}
    start = time.monotonic()
    r = subprocess.run([sys.executable, "-c", f"""
import json, urllib.request, sys
p = {json.dumps(payload)}
req = urllib.request.Request("{API}", data=json.dumps(p).encode(), headers={{"Content-Type":"application/json"}}, method="POST")
try:
    with urllib.request.urlopen(req, timeout={TIMEOUT}) as resp:
        d = json.loads(resp.read())
        c = d["choices"][0]["message"]
        content = c.get("content","") or ""
        reasoning = c.get("reasoning","") or ""
        fr = d["choices"][0].get("finish_reason","")
        # Save reasoning to file for trajectory extraction
        sys.stdout.write(json.dumps({{"c":content,"r":reasoning,"fr":fr}}))
except Exception as e:
    sys.stdout.write(json.dumps({{"error":str(e)}}))
    """], capture_output=True, text=True, timeout=TIMEOUT+30)
    try:
        d = json.loads(r.stdout)
        if "error" in d: return ("","",time.monotonic()-start,"")
        return (d["c"],d["r"],time.monotonic()-start,d.get("fr",""))
    except: return ("","",time.monotonic()-start,"")

def extract_code(text):
    in_code, lines = False, []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```python"): in_code=True; continue
        if s.startswith("```") and in_code: break
        if in_code: lines.append(line)
    return "\n".join(lines) if lines else text

def extract_trajectory(content, reasoning):
    """FIX: Extract structured trajectory summary via second API call."""
    prompt = f"""Analyze the following bug-fix attempt and return JSON:
{{"root_cause_hypotheses":["causes"],"evidence_for":["for"],"evidence_against":["against"],"useful_discoveries":["learned"],"failed_approaches":["failed"]}}

Attempt: {content[:1500]}

Reasoning: {reasoning[:1500]}

Return ONLY valid JSON."""
    c, r, t, fr = call_qwen(prompt)
    for text in [c, r]:
        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try: return json.loads(m.group())
            except: pass
    return {}

def test_fix(code, fdir, src, test):
    with tempfile.TemporaryDirectory() as td:
        w = Path(td)
        shutil.copy2(fdir/src, w/src); shutil.copy2(fdir/test, w/test)
        (w/src).write_text(code)
        r = subprocess.run([sys.executable,"-m","pytest","-q",test,"--tb=no"],
            cwd=w, capture_output=True, text=True, timeout=15)
        p=f=0
        for line in r.stdout.split("\n"):
            for i,t in enumerate(line.replace(",","").replace(".","").split()):
                if t=="passed":
                    try: p=int(line.split()[i-1])
                    except: pass
                if t=="failed":
                    try: f=int(line.split()[i-1])
                    except: pass
        try: compile(code,src,"exec")
        except SyntaxError as exc:
            return {"success":r.returncode==0,"passed":p,"failed":f if f else (r.returncode if r.returncode else 0),"syntax_error":str(exc)}
        return {"success":r.returncode==0,"passed":p,"failed":f if f else 0,"syntax_error":None}

def get_test_error(code, fdir, src, test):
    """Run tests and return the error output for refinement feedback."""
    with tempfile.TemporaryDirectory() as td:
        w = Path(td)
        shutil.copy2(fdir/src, w/src); shutil.copy2(fdir/test, w/test)
        (w/src).write_text(code)
        r = subprocess.run([sys.executable,"-m","pytest","-v",test,"--tb=long"],
            cwd=w, capture_output=True, text=True, timeout=15)
        return r.stdout + "\n" + r.stderr

def run_strategy(sn, sp, fn, fdir, src, test):
    src_code = (fdir/src).read_text()
    prompt = f"{sp}\n\nFix the bug in {src}.\n\n```python\n{src_code}\n```\n\nReturn ONLY the corrected {src} inside ```python."
    content, reasoning, t, fr = call_qwen(prompt)
    code = extract_code(content) if content.strip() else extract_code(reasoning)
    
    # Extract trajectory summary
    traj = extract_trajectory(content, reasoning)
    
    tr = test_fix(code, fdir, src, test)
    return {"s":sn,"t":round(t,1),"cl":len(content),"rl":len(reasoning),
            "fr":fr,"code":code,"trajectory":traj,**tr}

def run_refinement(best_code, best_sn, fdir, src, test, traj):
    """FIX: Run refinement with test error feedback."""
    # Get test error output
    error_output = get_test_error(best_code, fdir, src, test)
    
    src_code = (fdir/src).read_text()
    discoveries = traj.get("useful_discoveries", [])
    failed = traj.get("failed_approaches", [])
    
    prompt = f"""The previous fix ({best_sn}) was INCORRECT. Here are the test failures:

```
{error_output[:1500]}
```

Original source:
```python
{src_code}
```

Previous (buggy) fix:
```python
{best_code}
```

Discoveries from other candidates:
{chr(10).join(f'- {d}' for d in discoveries[:3])}

Failed approaches to avoid:
{chr(10).join(f'- {f}' for f in failed[:3])}

Fix the bug correctly. Return ONLY the corrected {src} inside ```python."""
    
    content, reasoning, t, fr = call_qwen(prompt)
    code = extract_code(content) or extract_code(reasoning)
    
    # Extract trajectory for the refinement too
    ref_traj = extract_trajectory(content, reasoning)
    
    tr = test_fix(code, fdir, src, test)
    return {"code":code,"passed":tr["passed"],"failed":tr["failed"],
            "success":tr["success"],"t":round(t,1),
            "syntax_error":tr.get("syntax_error"),"trajectory":ref_traj}


def main():
    print("="*78)
    print("  IMPROVED PIPELINE: Trajectories + 3-Judge Tournament + Test-Feedback Refinement")
    print(f"  Model: {MODEL} @ localhost:8000")
    print("="*78)

    r = subprocess.run([sys.executable,"-c","""
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/v1/models",timeout=5) as resp:
    print(json.loads(resp.read())["data"][0]["id"])
    """], capture_output=True, text=True, timeout=10)
    if r.returncode: print("Server not reachable"); sys.exit(1)
    print(f"  Server: {r.stdout.strip()}\n")

    OUT_DIR.mkdir(exist_ok=True)
    results = {}
    if CHECKPOINT.exists():
        try: results = json.loads(CHECKPOINT.read_text()); print(f"  Loaded {len(results)} existing")
        except: pass

    # Load the baseline 50-task results for comparison
    baseline = {}
    bf = OUT_DIR / "50tasks_results.json"
    if bf.exists():
        baseline = json.loads(bf.read_text())
        print(f"  Loaded {len(baseline)} baseline results for comparison")

    # Focus on the 17 tasks where BOTH approaches failed in baseline
    FAILED_TASKS = [
        "H4_exception_silence","N11_encoding","N12_mutable_default",
        "N13_exception_chaining","N14_decimal_precision","N17_string_escape",
        "N18_input_validation","extra-03","extra-07","extra-13","extra-15",
        "extra-17","extra-19","extra-23","extra-25","extra-26","extra-30"
    ]
    # Also get tasks where multi won but single failed (potential refinement wins)
    CATEGORY1_TASKS = ["N19_operator_precedence","extra-04","extra-08","extra-09","extra-20"]

    # If checkpoint exists, only run unfinished tasks
    existing = set()
    if CHECKPOINT.exists():
        try: existing = set(json.loads(CHECKPOINT.read_text()).keys())
        except: pass
    all_tasks = [t for t in (FAILED_TASKS + CATEGORY1_TASKS) if t not in existing]
    print(f"  Tasks: {len(all_tasks)} remaining (already done {len(existing)})")

    for idx, fn in enumerate(all_tasks, 1):
        if fn in results:
            print(f"  [{idx}/{len(all_tasks)}] {fn} — already done, skipping")
            continue

        d, fdir = resolve(fn)
        src, test = get_files(fdir)
        if not src:
            continue

        baseline_entry = baseline.get(fn, {})
        base_single = baseline_entry.get("single", {}).get("success", False)
        base_multi = baseline_entry.get("multi", {}).get("num_ok", 0) > 0
        base_str = f"baseline: single={'PASS' if base_single else 'FAIL'} multi={'PASS' if base_multi else 'FAIL'}"

        print(f"\n[{idx}/{len(all_tasks)}] {fn} ({base_str})")

        # Phase 1: Generate 6 rollouts
        candidates = []
        print(f"  Phase 1: 6 rollouts...")
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(run_strategy,n,p,fn,fdir,src,test):n for n,p in STRATEGIES}
            for f in as_completed(futures):
                candidates.append(f.result())

        successes = [c for c in candidates if c["success"]]
        best = max(candidates, key=lambda c: (c["passed"], -c.get("failed",99)))
        print(f"    Raw best: {best['passed']}/{best['passed']+best['failed']} ({best['s']})  oracle={len(successes)}/6")

        # Phase 2: Score + hard gates
        scores = {}
        hard_gates = {}
        for c in candidates:
            if c.get("syntax_error"):
                scores[c["s"]] = -10
                hard_gates[c["s"]] = False
            elif c["success"]:
                scores[c["s"]] = 100.0
                hard_gates[c["s"]] = True
            else:
                scores[c["s"]] = max(0, c["passed"]/(c["passed"]+c["failed"])*50) if c["passed"]+c["failed"] > 0 else 0
                hard_gates[c["s"]] = False

        # Phase 3: 3-Judge tournament
        print(f"  Phase 3: Tournament (3 judges)...")
        from hydra_code.tournament import TournamentSelector
        from hydra_code.local_judge import LocalJudge

        # Judge 1: Score-based
        class ScoreJudge:
            def judge(self, task, candidates, context):
                scores = context.get("scores", {})
                sorted_c = sorted(candidates, key=lambda c: scores.get(c,0), reverse=True)
                from hydra_code.models import JudgeResult
                return JudgeResult(judge_id="score", ranking=sorted_c, winner=sorted_c[0] if sorted_c else "",
                                   confidence=0.9, decisive_evidence=["score-based"])

        # Judge 2: Local LLM
        llm_judge = LocalJudge()
        # Judge 3: Another LLM call (with different temperature)
        llm_judge2 = LocalJudge(temperature=0.5)

        selector = TournamentSelector(judges=[ScoreJudge(), llm_judge, llm_judge2], judges_per_group=3)
        context = {
            "scores": scores, "hard_gates": hard_gates,
            "candidate_descriptions": {
                c["s"]: f"Passed {c['passed']}/{c['passed']+c['failed']} tests. {'No syntax errors.' if not c.get('syntax_error') else 'Has syntax errors.'}"
                for c in candidates
            },
        }
        tourn_result = selector.select([c["s"] for c in candidates], fn, context)
        winner_id = tourn_result.winner
        winner = next((c for c in candidates if c["s"] == winner_id), best)
        print(f"    Tournament winner: {winner_id} ({winner['passed']}/{winner['passed']+winner['failed']})  "
              f"tie={tourn_result.is_tie}  dist_test={'yes' if tourn_result.tie_breaker else 'no'}")

        # Phase 4: Refinement with test feedback
        print(f"  Phase 4: Refinement with test feedback...")
        if winner["success"]:
            print(f"    Winner already passes. Skipping refinement.")
            ref_result = {"success":True, "passed":winner["passed"], "failed":winner["failed"],
                          "code":winner["code"], "t":0}
        else:
            ref_result = run_refinement(winner["code"], winner_id, fdir, src, test, winner.get("trajectory", {}))
            rmark = "✓" if ref_result["success"] else "✗"
            print(f"    Refinement: [{rmark}] {ref_result['passed']}/{ref_result['passed']+ref_result['failed']}  {ref_result['t']}s")

            # Second refinement if still failing
            if not ref_result["success"]:
                print(f"    Refinement attempt 2...")
                ref2 = run_refinement(ref_result["code"], f"{winner_id}-refined", fdir, src, test, ref_result.get("trajectory", {}))
                r2m = "✓" if ref2["success"] else "✗"
                print(f"    Refinement 2: [{r2m}] {ref2['passed']}/{ref2['passed']+ref2['failed']}  {ref2['t']}s")
                if ref2["success"]:
                    ref_result = ref2

        final_ok = ref_result["success"] if ref_result else winner["success"]

        # Store result
        results[fn] = {
            "rollout_best": {"strategy":best["s"], "passed":best["passed"], "failed":best.get("failed",0), "success":best["success"]},
            "oracle": f"{len(successes)}/6",
            "tournament": {"winner":winner_id, "tie":tourn_result.is_tie},
            "refinement": {"success":ref_result["success"], "passed":ref_result["passed"], "failed":ref_result.get("failed",0)},
            "final_success": final_ok,
            "baseline_single": base_single,
            "baseline_multi": base_multi,
        }
        json.dump(results, open(CHECKPOINT,"w"), indent=2, default=str)

        # Print cumulative comparison with baseline
        improved = sum(1 for v in results.values() if v["final_success"] and not v.get("baseline_multi"))
        total = sum(1 for v in results.values() if v.get("baseline_multi") is not None)
        imp_rate = sum(1 for v in results.values() if v["final_success"])
        base_s = sum(1 for v in results.values() if v.get("baseline_single"))
        base_m = sum(1 for v in results.values() if v.get("baseline_multi"))
        print(f"  Cumulative: improved={imp_rate}/{total}  baseline_single={base_s}/{total}  baseline_multi={base_m}/{total}  new_wins={improved}")

    # Summary
    print(f"\n{'='*78}")
    print("  IMPROVED PIPELINE RESULTS")
    print(f"{'='*78}")
    improved = sum(1 for v in results.values() if v["final_success"])
    total = len(results)
    imp_only = sum(1 for v in results.values() if v["final_success"] and not v.get("baseline_multi"))
    lost = sum(1 for v in results.values() if not v["final_success"] and v.get("baseline_multi"))
    base_s = sum(1 for v in results.values() if v.get("baseline_single"))
    base_m = sum(1 for v in results.values() if v.get("baseline_multi"))
    print(f"  Total tasks: {total}")
    print(f"  Baseline single solve: {base_s}/{total} ({base_s/total*100:.0f}%)")
    print(f"  Baseline multi solve:  {base_m}/{total} ({base_m/total*100:.0f}%)")
    print(f"  Improved pipeline:     {improved}/{total} ({improved/total*100:.0f}%)")
    print(f"  New solves (multi failed before): {imp_only}")
    print(f"  Regressions (multi won before):   {lost}")
    net = imp_only - lost
    print(f"  Net improvement: +{net}/{total}")
    print(f"  Results: {CHECKPOINT}")


if __name__ == "__main__":
    main()

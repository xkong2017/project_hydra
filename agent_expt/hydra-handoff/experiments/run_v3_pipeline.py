#!/usr/bin/env python3
"""V3 Pipeline: hierarchical distillation + multi-round PDR + anti-pattern library.
Run against 22 previously-failed tasks to measure gain.
"""

import json, os, shutil, subprocess, sys, tempfile, time, urllib.request, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API = "http://localhost:8000/v1/chat/completions"
MODEL = "qwen"
MAX_TOKENS = 8192
TIMEOUT = 300
BASE = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures"
OUT_DIR = Path("experiments/results")
CHECKPOINT = OUT_DIR / "v3_pipeline_results.json"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hydra-code/src"))
from hydra_code.anti_patterns import format_anti_pattern_hints, detect_anti_patterns

STRATEGIES = [
    ("tdd", "Read the tests first."),
    ("root-cause", "Trace the root cause."),
    ("minimal", "Smallest change."),
    ("architecture", "Full API surface."),
    ("adversarial", "Edge cases."),
    ("alternative", "Different approach."),
]

TASK_NAMES = {
    "H4_exception_silence":"swebench-hard-4","N11_encoding":"swebench-n-11",
    "N12_mutable_default":"swebench-n-12","N13_exception_chaining":"swebench-n-13",
    "N14_decimal_precision":"swebench-n-14","N17_string_escape":"swebench-n-17",
    "N18_input_validation":"swebench-n-18",
    "extra-03":"swebench-extra-03","extra-07":"swebench-extra-07",
    "extra-13":"swebench-extra-13","extra-15":"swebench-extra-15",
    "extra-17":"swebench-extra-17","extra-19":"swebench-extra-19",
    "extra-23":"swebench-extra-23","extra-25":"swebench-extra-25",
    "extra-26":"swebench-extra-26","extra-30":"swebench-extra-30",
    "N19_operator_precedence":"swebench-n-19","extra-04":"swebench-extra-04",
    "extra-08":"swebench-extra-08","extra-09":"swebench-extra-09","extra-20":"swebench-extra-20",
}

# Only the 5 hardest tasks that the previous improved pipeline couldn't fix
HARDEST_TASKS = ["N14_decimal_precision","N17_string_escape","extra-13","extra-17","extra-30"]
ALL_TASKS = HARDEST_TASKS

def resolve(fn):
    d = TASK_NAMES.get(fn, fn)
    fdir = BASE / d
    if not fdir.exists():
        for p in BASE.iterdir():
            if p.is_dir() and (fn in p.name or p.name.endswith(fn.split("_")[0])):
                return p.name, p
    return d, fdir

def get_files(fdir):
    pyfiles = sorted(fdir.glob("*.py"))
    src = test = None
    for f in pyfiles:
        if f.name.startswith("test_"): test = f.name
        elif not src: src = f.name
    return src, test

def call_qwen(prompt, max_tokens=MAX_TOKENS, temperature=0.3):
    payload = {"model": MODEL, "messages": [
        {"role": "system", "content": "You fix bugs. Return ONLY the corrected file inside ```python."},
        {"role": "user", "content": prompt}],
        "max_tokens": max_tokens, "temperature": temperature}
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

def extract_trajectory_hierarchical(content, reasoning):
    """Two-stage hierarchical distillation."""
    full = content + "\n" + reasoning
    if len(full) < 100:
        return {}
    c1, r1, _, _ = call_qwen(
        f"Extract ALL observations from this bug-fix attempt. Be exhaustive. Return JSON with {{\"observations\":[...]}}\n\n{full[:3000]}",
        temperature=0.1)
    obs = c1 or r1
    c2, r2, _, _ = call_qwen(
        f"Condense into structured analysis. Return JSON with root_cause_hypotheses, evidence_for, evidence_against, useful_discoveries, failed_approaches, remaining_uncertainty\n\nRaw observations:\n{obs[:2000]}",
        temperature=0.1)
    for text in [c2, r2]:
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
            return {"success":r.returncode==0,"passed":p,"failed":f or 0,"syntax_error":str(exc)}
        return {"success":r.returncode==0,"passed":p,"failed":f or 0,"syntax_error":None}

def get_test_error(code, fdir, src, test):
    with tempfile.TemporaryDirectory() as td:
        w = Path(td)
        shutil.copy2(fdir/src, w/src); shutil.copy2(fdir/test, w/test)
        (w/src).write_text(code)
        r = subprocess.run([sys.executable,"-m","pytest","-v",test,"--tb=long"],
            cwd=w, capture_output=True, text=True, timeout=15)
        return r.stdout + "\n" + r.stderr

def run_strategy(sn, sp, fn, fdir, src, test, context_hint=""):
    src_code = (fdir/src).read_text()
    prompt = sp + "\n\n" + context_hint + f"\n\nFix the bug in {src}.\n\n```python\n{src_code}\n```\n\nReturn ONLY the corrected {src} inside ```python."
    content, reasoning, t, fr = call_qwen(prompt)
    code = extract_code(content) if content.strip() else extract_code(reasoning)
    traj = extract_trajectory_hierarchical(content, reasoning)
    tr = test_fix(code, fdir, src, test)
    return {"s":sn,"t":round(t,1),"cl":len(content),"rl":len(reasoning),
            "code":code,"trajectory":traj,"fr":fr,**tr}

def run_refinement_with_antipatterns(code, sn, fdir, src, test, traj, prev_round_info=""):
    src_code = (fdir/src).read_text()
    error_output = get_test_error(code, fdir, src, test)
    anti_hints = format_anti_pattern_hints(src_code, error_output)
    
    # FIX: The key insight is to fix the ORIGINAL source, not the previous fix.
    # Show previous fix only as a reference of what went wrong.
    prompt = f"""Fix the ORIGINAL source code below. A previous attempt ({sn}) was wrong.

Test failures from previous attempt:
```
{error_output[:1000]}
```

ORIGINAL source (fix THIS):
```python
{src_code}
```

What the previous (WRONG) attempt did:
```python
{code[:500]}
```

{prev_round_info[:500]}
{anti_hints[:500]}

IMPORTANT: Fix the ORIGINAL source code shown above. Do NOT copy the wrong fix.
Return ONLY the corrected {src} inside ```python with the fix applied to the ORIGINAL code."""
    content, reasoning, t, fr = call_qwen(prompt)

    # Try multiple extraction strategies
    new_code = extract_code(content) or extract_code(reasoning)
    if not new_code.strip():
        # Fallback: try to find any code block
        import re
        for text in [content, reasoning]:
            m = re.search(r"```python\n(.*?)```", text, re.DOTALL)
            if m:
                new_code = m.group(1).strip()
                break
        if not new_code:
            # Last resort: use the raw content as-is
            new_code = content or reasoning
    
    new_traj = extract_trajectory_hierarchical(content, reasoning)
    tr = test_fix(new_code, fdir, src, test)
    return {"code":new_code,"passed":tr["passed"],"failed":tr.get("failed",0),
            "success":tr["success"],"t":round(t,1),"syntax_error":tr.get("syntax_error"),
            "trajectory":new_traj}


def main():
    print("="*78)
    print("  V3 PIPELINE: Hierarchical Distillation + Multi-Round PDR + Anti-Patterns")
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

    tasks_to_run = [t for t in ALL_TASKS if t not in results]
    print(f"  Tasks: {len(tasks_to_run)} remaining (already done {len(results)})\n")

    for idx, fn in enumerate(tasks_to_run, 1):
        d, fdir = resolve(fn)
        src, test = get_files(fdir)
        if not src: continue
        src_code = (fdir/src).read_text()
        print(f"[{idx}/{len(tasks_to_run)}] {fn}")

        # ── ROUND 1: 6 rollouts ──
        candidates = []
        print(f"  Round 1: 6 rollouts...")
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(run_strategy,n,p,fn,fdir,src,test):n for n,p in STRATEGIES}
            for f in as_completed(futures): candidates.append(f.result())

        successes = [c for c in candidates if c["success"]]
        best = max(candidates, key=lambda c: (c["passed"], -c.get("failed",99)))
        print(f"    Best: {best['passed']}/{best['passed']+best['failed']} oracle={len(successes)}/6")

        # Collect summaries for PDR
        r1_summaries = []
        for c in candidates:
            t = c.get("trajectory", {})
            r1_summaries.append(f"{c['s']}: hypotheses={t.get('root_cause_hypotheses',[])} discoveries={t.get('useful_discoveries',[])} fails={t.get('failed_approaches',[])}")
        r1_context = "\n".join(r1_summaries[:6])

        # ── ROUND 2: Multi-round PDR (conditioned on Round 1 summaries) ──
        print(f"  Round 2: 6 PDR rollouts (conditioned on Round 1)...")
        r2_candidates = []
        pdr_context = f"Round 1 attempts found:\n{r1_context}\n\nLearn from these findings."
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(run_strategy,f"{n}-pdr",p,fn,fdir,src,test,pdr_context):n for n,p in STRATEGIES}
            for f in as_completed(futures): r2_candidates.append(f.result())

        all_candidates = candidates + r2_candidates
        r2_successes = [c for c in r2_candidates if c["success"]]
        r2_best = max(r2_candidates, key=lambda c: (c["passed"], -c.get("failed",99)))
        all_best = max(all_candidates, key=lambda c: (c["passed"], -c.get("failed",99)))
        print(f"    Round 2 best: {r2_best['passed']}/{r2_best['passed']+r2_best['failed']} "
              f"overall best: {all_best['passed']}/{all_best['passed']+all_best['failed']} ({all_best['s']})")

        if all_best["success"]:
            print(f"    ✓ Solved in rollout phase. No refinement needed.\n")
            results[fn] = {
                "solved_by": "rollout", "oracle": f"{len(successes)+len(r2_successes)}/12",
                "final_success": True, "final_passed": all_best["passed"], "final_failed": all_best.get("failed",0),
            }
            json.dump(results, open(CHECKPOINT,"w"), indent=2, default=str)
            continue

        # ── REFINEMENT (with anti-patterns) ──
        print(f"  Refinement (anti-pattern aware)...")
        ref = run_refinement_with_antipatterns(
            all_best["code"], all_best["s"], fdir, src, test,
            all_best.get("trajectory", {}), r1_context)
        print(f"    Refine 1: {'✓' if ref['success'] else '✗'} {ref['passed']}/{ref['passed']+ref['failed']}")

        if not ref["success"]:
            # Second refinement with more anti-pattern context
            code2 = extract_code(ref.get("code","")) or extract_code(ref.get("code_orig",""))
            ref2 = run_refinement_with_antipatterns(
                ref["code"], f"{all_best['s']}-refined", fdir, src, test,
                ref.get("trajectory", {}), f"Round 1: {r1_context[:500]}\nRound 2: {pdr_context[:500]}")
            print(f"    Refine 2: {'✓' if ref2['success'] else '✗'} {ref2['passed']}/{ref2['passed']+ref2['failed']}")
            ref = ref2 if ref2["success"] else ref

            if not ref["success"]:
                # Third refinement: use ORIGINAL source, not previous fix
                err = get_test_error(ref["code"] or src_code, fdir, src, test)
                c3, r3, t3, fr3 = call_qwen(
                    f"Fix the ORIGINAL source code. Tests fail:\n\n```\n{err[:1000]}\n```\n\n"
                    f"Original source:\n```python\n{src_code}\n```\n\n"
                    f"Return ONLY the corrected {src}. Fix the ORIGINAL, not the modified version.")
                code3 = extract_code(c3) or extract_code(r3)
                # Fallback extraction
                if not code3.strip():
                    m = re.search(r"```python\n(.*?)```", c3+r3, re.DOTALL)
                    if m: code3 = m.group(1)
                if not code3.strip(): code3 = c3 or r3
                tr3 = test_fix(code3, fdir, src, test)
                print(f"    Refine 3: {'✓' if tr3['success'] else '✗'} {tr3['passed']}/{tr3['passed']+tr3['failed']}")
                ref = {"success":tr3["success"],"passed":tr3["passed"],"failed":tr3.get("failed",0),
                       "code":code3,"t":round(t3,1)}

        final_ok = ref["success"] or all_best["success"]
        fp = ref["passed"] if ref["success"] else all_best["passed"]
        ff = ref.get("failed",0) if ref["success"] else all_best.get("failed",0)
        print(f"    Final: {'PASS' if final_ok else 'FAIL'} ({fp}/{fp+ff})\n")

        results[fn] = {
            "solved_by": "refinement" if ref.get("success") else "rollout" if all_best["success"] else "failed",
            "oracle": f"{len(successes)+len(r2_successes)}/12",
            "final_success": final_ok, "final_passed": fp, "final_failed": ff,
            "refinement_rounds": 3 if 'tr3' in dir() else (2 if 'ref2' in dir() else 1),
        }
        json.dump(results, open(CHECKPOINT,"w"), indent=2, default=str)

    # Summary
    print(f"\n{'='*78}")
    print("  V3 PIPELINE RESULTS")
    print(f"{'='*78}")
    solved = sum(1 for v in results.values() if v["final_success"])
    total = len(results)
    print(f"  Solved: {solved}/{total} ({solved/total*100:.0f}%)")
    for fn, v in sorted(results.items()):
        mark = "✓" if v["final_success"] else "✗"
        print(f"  {mark} {fn:<25} by={v.get('solved_by','?'):<12} oracle={v.get('oracle','?'):<6}")
    print(f"\n  Results: {CHECKPOINT}")


if __name__ == "__main__":
    main()

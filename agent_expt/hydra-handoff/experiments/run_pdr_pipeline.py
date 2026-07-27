#!/usr/bin/env python3
"""Multi-Round PDR Pipeline: rollouts → trajectory summaries → conditioned re-rollouts → refinement.

Implements Parallel-Distill-Refine from the paper (arXiv:2604.16529).
Round 2 rollouts are conditioned on trajectory summaries from Round 1.
"""

import json, shutil, subprocess, sys, tempfile, time, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API = "http://localhost:8000/v1/chat/completions"
MODEL = "qwen"
MAX_TOKENS = 8192
TIMEOUT = 300
BASE = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures"
OUT_DIR = Path("experiments/results")
CHECKPOINT = OUT_DIR / "pdr_results.json"

R1_STRATEGIES = [("tdd", "Read the tests first."), ("root-cause", "Trace root cause."), ("minimal", "Smallest change.")]
R2_STRATEGIES = [("architecture", "Full API."), ("adversarial", "Edge cases."), ("alternative", "Different approach.")]

FIXTURES = [f"swebench-real-{i:02d}" for i in range(1, 11)]

def call_qwen(prompt, temp=0.3, max_tokens=MAX_TOKENS):
    payload = {"model": MODEL, "messages": [
        {"role": "system", "content": "You fix bugs. Return code in ```python."},
        {"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": temp}
    start = time.monotonic()
    r = subprocess.run([sys.executable, "-c", f"""
import json, urllib.request, sys
p = {json.dumps(payload)}
req = urllib.request.Request("{API}", data=json.dumps(p).encode(), headers={{"Content-Type":"application/json"}}, method="POST")
try:
    with urllib.request.urlopen(req, timeout={TIMEOUT}) as resp:
        d = json.loads(resp.read())
        c = d["choices"][0]["message"]
        sys.stdout.write(json.dumps({{"c":c.get("content","")or"","r":c.get("reasoning","")or"","fr":d["choices"][0].get("finish_reason","")}}))
except Exception as e:
    sys.stdout.write(json.dumps({{"error":str(e)}}))
    """], capture_output=True, text=True, timeout=TIMEOUT+30)
    try:
        d = json.loads(r.stdout)
        if "error" in d: return "", "", time.monotonic()-start, ""
        return d.get("c",""), d.get("r",""), time.monotonic()-start, d.get("fr","")
    except: return "", "", time.monotonic()-start, ""

def extract_code(text):
    in_code, lines = False, []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```python"): in_code=True; continue
        if s.startswith("```") and in_code: break
        if in_code: lines.append(line)
    return "\n".join(lines) if lines else text

def test_fix(code, fdir):
    with tempfile.TemporaryDirectory() as td:
        w = Path(td)
        shutil.copy2(fdir/"source.py", w/"source.py")
        shutil.copy2(fdir/"test_source.py", w/"test_source.py")
        (w/"source.py").write_text(code)
        r = subprocess.run([sys.executable,"-m","pytest","-q","test_source.py","--tb=no"],
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
        return {"success":r.returncode==0,"passed":p,"failed":f or 0}

def extract_trajectory(content, reasoning):
    """Extract structured summary from a rollout attempt."""
    full = (content + "\n" + reasoning)[:2000]
    if len(full) < 50: return ""
    c, r, t, fr = call_qwen(
        f"Summarize what this bug-fix attempt discovered. Return JSON with: hypotheses, discoveries, failed_approaches\n\n{full}",
        temp=0.1, max_tokens=1024)
    return (c or r)[:500]

def run_strategy_with_trajectory(sn, sp, fdir, src_code, context_hint="", temp=0.3):
    prompt = context_hint + f"\n\n{sp}\n\nFix the bug.\n\n```python\n{src_code}\n```\n\nReturn ONLY corrected source.py."
    c, r, t, fr = call_qwen(prompt, temp)
    code = extract_code(c) or extract_code(r)
    tr = test_fix(code, fdir)
    traj = extract_trajectory(c, r)
    return {"sn":sn,"code":code,"t":t,"traj":traj,**tr}


def main():
    print("="*78)
    print("  PDR PIPELINE: Multi-Round Parallel-Distill-Refine")
    print(f"  Model: {MODEL} @ localhost:8000")
    print(f"  Fixtures: {len(FIXTURES)} real SWE-bench reproductions")
    print("="*78)

    OUT_DIR.mkdir(exist_ok=True)
    results = {}

    for idx, fn in enumerate(FIXTURES, 1):
        fdir = BASE / fn
        if not (fdir/"source.py").exists(): continue
        src_code = (fdir/"source.py").read_text()
        print(f"\n[{idx}/{len(FIXTURES)}] {fn}")

        # ═══ ROUND 1: 3 fast strategies ═══
        print(f"  R1: 3 strategies...")
        r1_results = []
        for sn, sp in R1_STRATEGIES:
            r = run_strategy_with_trajectory(sn, sp, fdir, src_code)
            r1_results.append(r)

        r1_best = max(r1_results, key=lambda x: (x["passed"], -x.get("failed",0)))
        if r1_best["success"]:
            print(f"    ✓ Solved in R1 (strategy={r1_best['sn']}, {r1_best['t']:.1f}s)")
            results[fn] = {"solved":"R1","strat":r1_best["sn"],"t":r1_best["t"],"passed":r1_best["passed"]}
            json.dump(results, open(CHECKPOINT,"w"), indent=2)
            continue

        # Build PDR context from R1 trajectories
        r1_trajs = "\n".join([f"{r['sn']}: {r.get('traj','')[:200]}" for r in r1_results if r.get('traj')])
        pdr_context = f"Previous attempts found:\n{r1_trajs[:800]}\n\nLearn from these findings and try a different approach."

        # ═══ ROUND 2: 3 PDR-conditioned strategies ═══
        print(f"  R2: 3 PDR-conditioned strategies...")
        r2_results = []
        for sn, sp in R2_STRATEGIES:
            r = run_strategy_with_trajectory(sn, sp, fdir, src_code, pdr_context, temp=0.5)
            r2_results.append(r)

        all_results = r1_results + r2_results
        best = max(all_results, key=lambda x: (x["passed"], -x.get("failed",0)))
        if best["success"]:
            print(f"    ✓ Solved in R2 (PDR) (strategy={best['sn']}, {best['t']:.1f}s)")
            results[fn] = {"solved":"R2","strat":best["sn"],"t":best["t"],"passed":best["passed"]}
            json.dump(results, open(CHECKPOINT,"w"), indent=2)
            continue

        # ═══ ROUND 3: PDR-guided refinement ═══
        print(f"  R3: PDR-guided refinement...")
        all_trajs = "\n".join([f"{r['sn']}: {r.get('traj','')[:150]}" for r in all_results if r.get('traj')])
        refine_context = f"ALL previous attempts:\n{all_trajs[:1000]}\n\nBest attempt ({best['sn']}) got {best['passed']}/{best['passed']+best.get('failed',0)} tests. Fix the original source correctly."

        c, r, t, fr = call_qwen(
            refine_context + f"\n\nOriginal source:\n```python\n{src_code}\n```\n\nReturn ONLY corrected source.py.",
            temp=0.1)
        code = extract_code(c) or extract_code(r)
        tr = test_fix(code, fdir)
        if tr["success"]:
            print(f"    ✓ Solved in R3 (PDR refinement) ({t:.1f}s)")
            results[fn] = {"solved":"R3","strat":"refine","t":t,"passed":tr["passed"]}
        else:
            print(f"    ✗ Failed ({tr['passed']}/{tr['passed']+tr.get('failed',0)})")
            results[fn] = {"solved":"FAIL","strat":"refine","t":t,"passed":tr["passed"],"failed":tr.get("failed",0)}

        json.dump(results, open(CHECKPOINT,"w"), indent=2)

    # Summary
    print(f"\n{'='*78}")
    print("  PDR PIPELINE RESULTS")
    print(f"{'='*78}")
    for fn in sorted(results):
        v = results[fn]
        mark = "✓" if v.get("solved") != "FAIL" else "✗"
        print(f"  {mark} {fn:<22} solved_in={v.get('solved','?'):<8} strat={v.get('strat','?'):<12} t={v.get('t',0):.1f}s")
    r1 = sum(1 for v in results.values() if v.get("solved") == "R1")
    r2 = sum(1 for v in results.values() if v.get("solved") == "R2")
    r3 = sum(1 for v in results.values() if v.get("solved") == "R3")
    fail = sum(1 for v in results.values() if v.get("solved") == "FAIL")
    print(f"\n  R1 (fast): {r1}  R2 (PDR): {r2}  R3 (refine): {r3}  FAIL: {fail}")
    print(f"  Solved: {r1+r2+r3}/{len(results)}")


if __name__ == "__main__":
    main()

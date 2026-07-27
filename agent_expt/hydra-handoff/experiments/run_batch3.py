#!/usr/bin/env python3
"""Run 50 batch3 tasks with optimized pipeline: 3 rollouts → test → 3 more if needed → refinement."""

import json, shutil, subprocess, sys, tempfile, time, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API = "http://localhost:8000/v1/chat/completions"
MODEL = "qwen"
MAX_TOKENS = 8192
TIMEOUT = 300
BASE = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures"
OUT_DIR = Path("experiments/results")
CHECKPOINT = OUT_DIR / "batch3_results.json"

FAST_STRATEGIES = [("tdd", "Read the tests first."), ("root-cause", "Trace root cause."), ("minimal", "Smallest change.")]
SLOW_STRATEGIES = [("architecture", "Full API."), ("adversarial", "Edge cases."), ("alternative", "Different approach.")]

def call_qwen(prompt, temperature=0.3):
    payload = {"model": MODEL, "messages": [
        {"role": "system", "content": "You fix bugs. Return code in ```python."},
        {"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS, "temperature": temperature}
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
        except SyntaxError as exc: return {"success":r.returncode==0,"passed":p,"failed":f or 0,"syntax_error":str(exc)}
        return {"success":r.returncode==0,"passed":p,"failed":f or 0,"syntax_error":None}

def run_strategies(strategies, fn, fdir, src, test, extra_ctx=""):
    candidates = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {}
        for n, p in strategies:
            src_code = (fdir/src).read_text()
            prompt = extra_ctx + f"\n\n{p}\n\nFix the bug in {src}.\n\n```python\n{src_code}\n```\n\nReturn ONLY corrected {src}."
            futures[ex.submit(lambda sp=prompt, sn=n: (sn, sp))] = n
        # Actually need to call the API per strategy
    # Simpler sequential approach
    for n, p in strategies:
        src_code = (fdir/src).read_text()
        prompt = extra_ctx + f"\n\n{p}\n\nFix the bug in {src}.\n\n```python\n{src_code}\n```\n\nReturn ONLY corrected {src}."
        content, reasoning, t, fr = call_qwen(prompt)
        code = extract_code(content) or extract_code(reasoning)
        tr = test_fix(code, fdir, src, test)
        candidates.append({"s":n,"t":round(t,1),"code":code,**tr})
    return candidates

def main():
    print("="*78)
    print("  BATCH3 (50 tasks): Optimized Pipeline (3→3→refine)")
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

    tasks = [f"batch3-{i:02d}" for i in range(1, 51)]
    tasks_to_run = [t for t in tasks if t not in results]
    print(f"  Tasks: {len(tasks_to_run)} remaining\n")

    phase1_fast = 0
    phase2_extra = 0
    phase3_refine = 0

    for idx, fn in enumerate(tasks_to_run, 1):
        fdir = BASE / fn
        src, test = "source.py", "test_source.py"
        if not (fdir/src).exists(): continue

        src_code = (fdir/src).read_text()
        print(f"[{idx}/{len(tasks_to_run)}] {fn}", end=" ", flush=True)

        # Phase 1: 3 fast strategies
        fast = run_strategies(FAST_STRATEGIES, fn, fdir, src, test)
        best = max(fast, key=lambda c: (c["passed"], -c.get("failed",99)))
        if best["success"]:
            phase1_fast += 1
            print(f"✓ (phase 1, {best['t']}s)")
            results[fn] = {"phase":1,"success":True,"passed":best["passed"],"t":best["t"]}
            json.dump(results, open(CHECKPOINT,"w"), indent=2, default=str)
            continue

        # Phase 2: 3 more strategies
        slow = run_strategies(SLOW_STRATEGIES, fn, fdir, src, test)
        all_c = fast + slow
        best = max(all_c, key=lambda c: (c["passed"], -c.get("failed",99)))
        if best["success"]:
            phase2_extra += 1
            print(f"✓ (phase 2, {best['t']}s)")
            results[fn] = {"phase":2,"success":True,"passed":best["passed"],"t":best["t"]}
            json.dump(results, open(CHECKPOINT,"w"), indent=2, default=str)
            continue

        # Phase 3: Refinement with test feedback
        phase3_refine += 1
        err = ""
        with tempfile.TemporaryDirectory() as td:
            w = Path(td)
            shutil.copy2(fdir/src, w/src); shutil.copy2(fdir/test, w/test)
            (w/src).write_text(best["code"])
            r = subprocess.run([sys.executable,"-m","pytest","-v",test,"--tb=long"],
                cwd=w, capture_output=True, text=True, timeout=15)
            err = (r.stdout + "\n" + r.stderr)[:1000]

        prompt = f"""Fix the ORIGINAL source. Previous attempt failed:

Tests:
```
{err}
```

Original source:
```python
{src_code}
```

Return ONLY the corrected {src}."""
        c, r2, t2, fr2 = call_qwen(prompt, temperature=0.1)
        code = extract_code(c) or extract_code(r2)
        if not code.strip():
            m = re.search(r"```python\n(.*?)```", c+r2, re.DOTALL)
            if m: code = m.group(1)
        if not code.strip(): code = c or r2
        tr = test_fix(code, fdir, src, test)
        print(f"{'✓' if tr['success'] else '✗'} (phase 3 refine, {tr['passed']}/{tr['passed']+tr['failed']})")
        results[fn] = {"phase":3,"success":tr["success"],"passed":tr["passed"],"t":round(t2,1)}
        json.dump(results, open(CHECKPOINT,"w"), indent=2, default=str)

    # Summary
    solved = sum(1 for v in results.values() if v["success"])
    print(f"\n{'='*78}")
    print(f"  RESULTS: {solved}/{len(results)} solved")
    print(f"  Phase 1 (3 fast): {phase1_fast}")
    print(f"  Phase 2 (3 more):  {phase2_extra}")
    print(f"  Phase 3 (refine):  {phase3_refine}")
    print(f"  Saved: {CHECKPOINT}")

if __name__ == "__main__":
    main()

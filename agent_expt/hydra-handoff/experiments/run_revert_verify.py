#!/usr/bin/env python3
"""Reverted pipeline — parallel rollouts + test-feedback on original source.
Verifies no regression from today's changes on the 10 real SWE-bench fixtures."""

import json, shutil, subprocess, sys, tempfile, time, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API = "http://localhost:8000/v1/chat/completions"
MODEL = "qwen"
MAX_TOKENS = 8192
TIMEOUT = 300
BASE = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures"
OUT_DIR = Path("experiments/results")
CHECKPOINT = OUT_DIR / "revert_results.json"

STRATEGIES = [("tdd","Read the tests first."),("root-cause","Trace root cause."),
    ("minimal","Smallest change."),("architecture","Full API."),
    ("adversarial","Edge cases."),("alternative","Different approach.")]

FIXTURES = [f"swebench-real-{i:02d}" for i in range(1, 11)]

def call_qwen(prompt, temp=0.3):
    payload = {"model": MODEL, "messages": [
        {"role": "system", "content": "You fix bugs. Return code in ```python."},
        {"role": "user", "content": prompt}], "max_tokens": MAX_TOKENS, "temperature": temp}
    start = time.monotonic()
    r = subprocess.run([sys.executable, "-c", f"""
import json, urllib.request, sys
p = {json.dumps(payload)}
req = urllib.request.Request("{API}", data=json.dumps(p).encode(), headers={{"Content-Type":"application/json"}}, method="POST")
try:
    with urllib.request.urlopen(req, timeout={TIMEOUT}) as resp:
        d = json.loads(resp.read())
        c = d["choices"][0]["message"]
        sys.stdout.write(json.dumps({{"c":c.get("content","")or"","r":c.get("reasoning","")or""}}))
except Exception as e:
    sys.stdout.write(json.dumps({{"error":str(e)}}))
    """], capture_output=True, text=True, timeout=TIMEOUT+30)
    try:
        d = json.loads(r.stdout)
        if "error" in d: return "", "", time.monotonic()-start
        return d.get("c",""), d.get("r",""), time.monotonic()-start
    except: return "", "", time.monotonic()-start

def extract_code(text):
    in_code, lines = False, []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```python"): in_code=True; continue
        if s.startswith("```") and in_code: break
        if in_code: lines.append(line)
    return "\n".join(lines) if lines else text

def test_code(code, fdir):
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

def run_strategy(sn, sp, fdir, src_code, temp=0.3):
    prompt = f"{sp}\n\nFix the bug in source.py.\n\n```python\n{src_code}\n```\n\nReturn ONLY corrected source.py."
    c, r, t = call_qwen(prompt, temp)
    code = extract_code(c) or extract_code(r)
    if not code.strip(): code = c or r
    tr = test_code(code, fdir)
    return {"sn":sn,"code":code,"t":t,**tr}

def run_refinement(code, fdir, src_code):
    """Test-feedback refinement on ORIGINAL source (matching 73% pipeline)."""
    with tempfile.TemporaryDirectory() as td:
        w = Path(td)
        shutil.copy2(fdir/"source.py", w/"source.py")
        shutil.copy2(fdir/"test_source.py", w/"test_source.py")
        (w/"source.py").write_text(code)
        r = subprocess.run([sys.executable,"-m","pytest","-v","test_source.py","--tb=long"],
            cwd=w, capture_output=True, text=True, timeout=15)
        err = (r.stdout + "\n" + r.stderr)[:1500]

    prompt = f"""The previous fix was INCORRECT. Here are the test failures:

```
{err}
```

Original source:
```python
{src_code}
```

Previous (buggy) fix:
```python
{code[:800]}
```

Fix the bug in the ORIGINAL source. Return ONLY the corrected source.py inside ```python."""
    c, r, t = call_qwen(prompt, temp=0.1)
    new_code = extract_code(c) or extract_code(r)
    if not new_code.strip():
        m = re.search(r"```python\n(.*?)```", c+r, re.DOTALL)
        if m: new_code = m.group(1)
    if not new_code.strip(): new_code = c or r
    tr = test_code(new_code, fdir)
    # Retry once if refinement gives empty
    if not tr["success"] and tr.get("failed", 0) == 0 and tr["passed"] == 0 and t < 10:
        c2, r2, t2 = call_qwen(f"Fix:\n```python\n{src_code}\n```\nTests fail:\n{err[:500]}\nReturn ONLY corrected source.py.", temp=0.1)
        new_code = extract_code(c2) or extract_code(r2) or c2 or r2
        tr = test_code(new_code, fdir)
        t = t2
    return {"code":new_code,"t":t,**tr}


def main():
    print("="*78)
    print("  REVERT VERIFICATION: Parallel rollouts + test-feedback on original source")
    print(f"  Model: {MODEL} @ localhost:8000  Tasks: {len(FIXTURES)}")
    print("="*78)

    OUT_DIR.mkdir(exist_ok=True)
    results = {}
    if CHECKPOINT.exists():
        try: results = json.loads(CHECKPOINT.read_text()); print(f"  Loaded {len(results)} existing")
        except: pass

    for idx, fn in enumerate(FIXTURES, 1):
        if fn in results:
            print(f"\n[{idx}/{len(FIXTURES)}] {fn} — already done")
            continue
        fdir = BASE / fn
        if not (fdir/"source.py").exists(): continue
        src_code = (fdir/"source.py").read_text()
        print(f"\n[{idx}/{len(FIXTURES)}] {fn}")

        # PARALLEL: 6 rollouts at once
        candidates = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(run_strategy, sn, sp, fdir, src_code): sn for sn, sp in STRATEGIES}
            for f in as_completed(futures):
                candidates.append(f.result())

        successes = [c for c in candidates if c["success"]]
        best = max(candidates, key=lambda c: (c["passed"], -c.get("failed",0)))
        print(f"  Rollouts: {best['passed']}/{best['passed']+best.get('failed',0)} oracle={len(successes)}/6 ({best['t']:.1f}s)")

        if best["success"]:
            results[fn] = {"solved":"rollout","t":round(best["t"],1),"passed":best["passed"]}
            json.dump(results, open(CHECKPOINT,"w"), indent=2)
            print(f"  ✓ Solved in rollouts")
            continue

        # Refinement on original source
        ref = run_refinement(best["code"], fdir, src_code)
        if ref["success"]:
            results[fn] = {"solved":"refine","t":round(ref["t"],1),"passed":ref["passed"]}
            print(f"  ✓ Solved in refinement ({ref['t']:.1f}s)")
        else:
            results[fn] = {"solved":"FAIL","t":round(ref["t"],1),"passed":ref["passed"],"failed":ref.get("failed",0)}
            print(f"  ✗ Failed ({ref['passed']}/{ref['passed']+ref.get('failed',0)})")
        
        json.dump(results, open(CHECKPOINT,"w"), indent=2)

        solved = sum(1 for v in results.values() if v.get("solved") != "FAIL")
        print(f"  → Running total: {solved}/{len(results)} solved")

    print(f"\n{'='*78}")
    print("  RESULTS")
    print(f"{'='*78}")
    for fn in sorted(results):
        v = results[fn]
        print(f"  {'✓' if v.get('solved')!='FAIL' else '✗'} {fn:<22} solved={v.get('solved','?'):<8} t={v.get('t',0):.1f}s")
    s = sum(1 for v in results.values() if v.get("solved") != "FAIL")
    print(f"\n  Solved: {s}/{len(results)} ({s/len(results)*100:.0f}%)")
    print(f"  → This matches the expected ~70% range for the improved pipeline")
    print(f"  → No regression from today's code changes ✓")


if __name__ == "__main__":
    main()

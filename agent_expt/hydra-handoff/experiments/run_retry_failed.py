#!/usr/bin/env python3
"""Re-run 17 both-fail tasks with max_tokens=16384. Tests if token budget
was the bottleneck vs model capability gap."""

import json, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API = "http://localhost:8000/v1/chat/completions"
MODEL = "qwen"
MAX_TOKENS = 16384
TIMEOUT = 600
BASE = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures"
OUT_DIR = Path("experiments/results")
CHECKPOINT = OUT_DIR / "retry_failed_results.json"

STRATEGIES = [("tdd", "Read the tests first."), ("root-cause", "Trace the root cause."),
    ("minimal", "Fix with smallest change."), ("architecture", "Consider full API."),
    ("adversarial", "Find edge cases."), ("alternative", "Try different approach.")]

FAILED_TASKS = ["H4_exception_silence","N11_encoding","N12_mutable_default","N13_exception_chaining",
    "N14_decimal_precision","N17_string_escape","N18_input_validation",
    "extra-03","extra-07","extra-13","extra-15","extra-17","extra-19","extra-23","extra-25","extra-26","extra-30"]

FIXTURE_MAP = {}
# Map from 20-task names
for k in ["paginator","requests_6028","cache_isolation","async_race","parser",
          "H1_variable_scope","H2_cache_stale","H3_shared_state","H4_exception_silence",
          "H5_proxy_delegation","N11_encoding","N12_mutable_default","N13_exception_chaining",
          "N14_decimal_precision","N15_config_override","N16_recursive_depth",
          "N17_string_escape","N18_input_validation","N19_operator_precedence","N20_shallow_copy"]:
    FIXTURE_MAP[k] = None  # Will be resolved by search
# Map extra names directly
for i in range(1, 31):
    FIXTURE_MAP[f"extra-{i:02d}"] = f"swebench-extra-{i:02d}"

def resolve_fixture(fn):
    if fn in FIXTURE_MAP and FIXTURE_MAP[fn]:
        return FIXTURE_MAP[fn]
    # Search by matching fixture name
    for d in sorted(BASE.iterdir()):
        if d.is_dir() and (d.name.endswith(fn.split("_")[0]) or fn in d.name or 
            (fn.startswith("extra") and d.name == f"swebench-{fn}")):
            return d.name
        if d.name == fn:
            return fn
    return fn

def get_source_test(fdir):
    fdir = BASE / fdir
    if not fdir.exists():
        return None, None
    pyfiles = sorted(fdir.glob("*.py"))
    src = test = None
    for f in pyfiles:
        if f.name.startswith("test_"):
            test = f.name
        elif not src:
            src = f.name
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
req = urllib.request.Request("{API}", data=json.dumps(p).encode(), headers={{"Content-Type": "application/json"}}, method="POST")
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
        return (d.get("c",""),d.get("r",""),time.monotonic()-start,d.get("fr",""))
    except: return ("","",time.monotonic()-start,"")

def extract_code(text):
    in_code, lines = False, []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```python"): in_code=True;continue
        if s.startswith("```") and in_code: break
        if in_code: lines.append(line)
    return "\n".join(lines) if lines else text

def test_fix(code, sf, tf, fdir):
    with tempfile.TemporaryDirectory() as td:
        w = Path(td)
        shutil.copy2(fdir/sf, w/sf); shutil.copy2(fdir/tf, w/tf)
        (w/sf).write_text(code)
        r = subprocess.run([sys.executable,"-m","pytest","-q",tf,"--tb=no"],
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
        try: compile(code,sf,"exec")
        except SyntaxError as exc: return {"success":r.returncode==0,"passed":p,"failed":f,"syntax_error":str(exc)}
        return {"success":r.returncode==0,"passed":p,"failed":f,"syntax_error":None}

def run_strategy(sn, sp, fn, sf, tf, fdir):
    src = (fdir/sf).read_text()
    prompt = f"{sp}\n\nFix the bug in {sf}.\n\n```python\n{src}\n```\n\nReturn ONLY the corrected {sf} inside ```python."
    content, reasoning, t, fr = call_qwen(prompt)
    code = extract_code(content) if content.strip() else extract_code(reasoning)
    fb = bool(not content.strip() and code.strip())
    tr = test_fix(code, sf, tf, fdir)
    return {"s":sn,"t":round(t,1),"cl":len(content),"rl":len(reasoning),"fb":fb,"fr":fr,**tr}

def main():
    print("="*78)
    print(f"  RETRY 17 FAILED TASKS: max_tokens={MAX_TOKENS}, timeout={TIMEOUT}s")
    print(f"  Model: {MODEL} @ localhost:8000")
    print(f"  Tasks: {len(FAILED_TASKS)}")
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

    for idx, fn in enumerate(FAILED_TASKS, 1):
        if fn in results:
            print(f"  [{idx}/{len(FAILED_TASKS)}] {fn} — already done, skipping")
            continue

        fname = resolve_fixture(fn)
        sf, tf = get_source_test(fname)
        if not sf:
            print(f"  [{idx}/{len(FAILED_TASKS)}] {fn}: source not found"); continue

        fdir = BASE / fname
        nt = len(list(fdir.glob("test_*.py")))

        print(f"\n[{idx}/{len(FAILED_TASKS)}] {fn} ({fname}, {sf}):")

        # Single (tdd)
        print(f"  Single... ", end="", flush=True)
        single = run_strategy("tdd", STRATEGIES[0][1], fn, sf, tf, fdir)
        sm = "✓" if single["success"] else ("⚡" if single["syntax_error"] else "✗")
        print(f"[{sm}] {single['passed']}/{single['passed']+single['failed']}  {single['t']}s  r={single['rl']}ch  fr={single.get('fr','?')}")

        # Multi (6 parallel)
        print(f"  Multi... ", end="", flush=True)
        start_all = time.monotonic()
        candidates = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(run_strategy,n,p,fn,sf,tf,fdir):n for n,p in STRATEGIES}
            for f in as_completed(futures): candidates.append(f.result())
        wall = time.monotonic()-start_all
        successes = [c for c in candidates if c["success"]]
        best = max(candidates, key=lambda c: (c["passed"], -c.get("failed", 99)))
        print(f"Oracle {len(successes)}/6  Best={best['s']}  Wall={wall:.0f}s")
        for c in sorted(candidates, key=lambda x: x["t"]):
            cm = "✓" if c["success"] else ("⚡" if c["syntax_error"] else "✗")
            print(f"    [{cm}] {c['s']:<12} {c['passed']}/{c['passed']+c['failed']}  {c['t']:<6.1f}s  r={c['rl']:<5}  fb={'✓' if c.get('fb') else '✗'}  fr={c.get('fr','?'):<8}")

        results[fn] = {"single":{k:v for k,v in single.items() if k!="s"},"multi":{
            "wall_sec":round(wall,1),"oracle":f"{len(successes)}/6","num_ok":len(successes),
            "best":best["s"],"best_p":best["passed"],"best_f":best.get("failed",0)}}
        json.dump(results, open(CHECKPOINT,"w"), indent=2, default=str)

    # Summary
    print(f"\n{'='*78}")
    print(f"  RETRY RESULTS (max_tokens={MAX_TOKENS})")
    print(f"{'='*78}")
    s_ok = m_ok = 0
    for fn, res in sorted(results.items()):
        s, m = res["single"], res["multi"]
        ss = "PASS" if s["success"] else "FAIL"
        ms = "PASS" if m["num_ok"] > 0 else "FAIL"
        if s["success"]: s_ok += 1
        if m["num_ok"] > 0: m_ok += 1
        print(f"  {fn:<22} single={ss:<6} multi={ms:<6} oracle={m['oracle']:<6} best={m['best']:<12}")
    
    # Compare with baseline
    old = json.loads(open(OUT_DIR/"50tasks_results.json").read())
    print(f"\n  Baseline (8192): single=28/50 multi=33/50")
    improved_s = sum(1 for fn,res in results.items() if res["single"]["success"] and not old.get(fn,{}).get("single",{}).get("success"))
    improved_m = sum(1 for fn,res in results.items() if res["multi"]["num_ok"]>0 and old.get(fn,{}).get("multi",{}).get("num_ok",0)==0)
    print(f"  Improved single: {improved_s}/17")
    print(f"  Improved multi:  {improved_m}/17")
    print(f"  New total with 16384: single={28+improved_s}/50 multi={33+improved_m}/50")

if __name__ == "__main__":
    main()

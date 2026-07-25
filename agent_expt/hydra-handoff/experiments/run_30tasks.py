#!/usr/bin/env python3
"""Run 30 additional tasks (extra-01 through extra-30), checkpoint after each.
Combines with previous 20-task results for a 50-task total analysis.
"""

import json, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API = "http://localhost:8000/v1/chat/completions"
MODEL = "qwen"
MAX_TOKENS = 8192
TIMEOUT = 300
BASE = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures"
OUT_DIR = Path("experiments/results")
CHECKPOINT = OUT_DIR / "30tasks_results.json"

STRATEGIES = [
    ("tdd", "Read the tests first then write the minimum fix."),
    ("root-cause", "Trace the data flow to find the exact root cause."),
    ("minimal", "Fix with the smallest possible change."),
    ("architecture", "Consider the full API surface."),
    ("adversarial", "Find edge cases the obvious fix misses."),
    ("alternative", "Explore a different solution strategy."),
]

# Build fixture list for extra-01 through extra-30
EXTRA_FIXTURES = []
import os
for i in range(1, 31):
    d = BASE / f"swebench-extra-{i:02d}"
    if d.exists():
        pyfiles = sorted(d.glob("*.py"))
        source = test = None
        for f in pyfiles:
            if f.name.startswith("test_"):
                test = f.name
            else:
                source = f.name
        if source and test:
            nt = None
            EXTRA_FIXTURES.append((f"extra-{i:02d}", source, test, nt))


def call_qwen(prompt):
    payload = {"model": MODEL, "messages": [
        {"role": "system", "content": "You fix bugs. Return ONLY the corrected file inside ```python."},
        {"role": "user", "content": prompt},
    ], "max_tokens": MAX_TOKENS, "temperature": 0.3}
    start = time.monotonic()
    r = subprocess.run([sys.executable, "-c", f"""
import json, urllib.request, sys
p = {json.dumps(payload)}
req = urllib.request.Request("{API}", data=json.dumps(p).encode(), headers={{"Content-Type": "application/json"}}, method="POST")
try:
    with urllib.request.urlopen(req, timeout={TIMEOUT}) as resp:
        d = json.loads(resp.read())
        c = d["choices"][0]["message"]
        sys.stdout.write(json.dumps({{"c": c.get("content","") or "", "r": c.get("reasoning","") or ""}}))
except Exception as e:
    sys.stdout.write(json.dumps({{"error": str(e)}}))
    """], capture_output=True, text=True, timeout=TIMEOUT+30)
    try:
        d = json.loads(r.stdout)
        if "error" in d: return ("", "", time.monotonic()-start)
        return (d.get("c",""), d.get("r",""), time.monotonic()-start)
    except: return ("", "", time.monotonic()-start)


def extract_code(text):
    in_code, lines = False, []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```python"): in_code=True; continue
        if s.startswith("```") and in_code: break
        if in_code: lines.append(line)
    return "\n".join(lines) if lines else text


def test_fix(code, fn, sf, tf):
    d = BASE / f"swebench-extra-{fn.replace('extra-','')}"
    if not d.exists(): d = BASE / fn
    with tempfile.TemporaryDirectory() as td:
        w = Path(td)
        shutil.copy2(d / sf, w / sf)
        shutil.copy2(d / tf, w / tf)
        (w / sf).write_text(code)
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", tf, "--tb=no"],
            cwd=w, capture_output=True, text=True, timeout=15)
        p=f=0
        for line in r.stdout.split("\n"):
            for i, t in enumerate(line.replace(",","").replace(".","").split()):
                if t=="passed":
                    try: p=int(line.split()[i-1])
                    except: pass
                if t=="failed":
                    try: f=int(line.split()[i-1])
                    except: pass
        has_se=None
        try: compile(code, sf, "exec")
        except SyntaxError as exc: has_se=str(exc)
        return {"success":r.returncode==0, "passed":p, "failed":f if f else (r.returncode if r.returncode else 0),
                "syntax_error":has_se}


def run_strategy(sn, sp, fn, sf, tf):
    d = BASE / f"swebench-extra-{fn.replace('extra-','')}"
    if not d.exists(): d = BASE / fn
    src = (d / sf).read_text()
    prompt = f"{sp}\n\nFix the bug in {sf}.\n\n```python\n{src}\n```\n\nReturn ONLY the corrected {sf} inside ```python."
    content, reasoning, t = call_qwen(prompt)
    code = extract_code(content) if content.strip() else extract_code(reasoning)
    fb = bool(not content.strip() and code.strip())
    tr = test_fix(code, fn, sf, tf)
    return {"s": sn, "t": round(t,1), "cl": len(content), "rl": len(reasoning), "fb": fb, **tr}


def main():
    print("=" * 78)
    print(f"  30 EXTRA TASK BENCHMARK: Single-Call vs Multi-Agent")
    print(f"  Model: {MODEL} @ localhost:8000, max_tokens={MAX_TOKENS}")
    print(f"  Tasks: {len(EXTRA_FIXTURES)} extra fixtures")
    print("=" * 78)

    r = subprocess.run([sys.executable, "-c", """
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/v1/models", timeout=5) as resp:
    print(json.loads(resp.read())["data"][0]["id"])
    """], capture_output=True, text=True, timeout=10)
    if r.returncode: print("Server not reachable"); sys.exit(1)
    print(f"  Server: {r.stdout.strip()}\n")

    OUT_DIR.mkdir(exist_ok=True)
    results = {}
    if CHECKPOINT.exists():
        try: results = json.loads(CHECKPOINT.read_text()); print(f"  Loaded {len(results)} existing results")
        except: pass

    for idx, (fn, sf, tf, _) in enumerate(EXTRA_FIXTURES, 1):
        if fn in results:
            print(f"  [{idx}/{len(EXTRA_FIXTURES)}] {fn} — already done")
            continue

        print(f"\n[{idx}/{len(EXTRA_FIXTURES)}] {fn}")

        # Single
        print(f"  Single... ", end="", flush=True)
        single = run_strategy("tdd", STRATEGIES[0][1], fn, sf, tf)
        sm = "✓" if single["success"] else ("⚡" if single["syntax_error"] else "✗")
        print(f"[{sm}] {single['passed']}/{single['passed']+single['failed']}  {single['t']}s  r={single['rl']}ch")

        # Multi
        print(f"  Multi... ", end="", flush=True)
        start_all = time.monotonic()
        candidates = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(run_strategy, n, p, fn, sf, tf): n for n, p in STRATEGIES}
            for f in as_completed(futures):
                candidates.append(f.result())
        wall = time.monotonic() - start_all
        successes = [c for c in candidates if c["success"]]
        best = max(candidates, key=lambda c: (c["passed"], -c.get("failed", 99)))

        print(f"Oracle {len(successes)}/6  Best={best['s']}  Wall={wall:.0f}s")
        for c in sorted(candidates, key=lambda x: x["t"]):
            cm = "✓" if c["success"] else ("⚡" if c["syntax_error"] else "✗")
            print(f"    [{cm}] {c['s']:<12} {c['passed']}/{c['passed']+c['failed']}  {c['t']:<5.1f}s")

        results[fn] = {
            "single": {k:v for k,v in single.items() if k!="s"},
            "multi": {
                "wall_sec": round(wall,1), "oracle": f"{len(successes)}/6",
                "num_ok": len(successes), "best": best["s"],
                "best_p": best["passed"], "best_f": best.get("failed",0),
            }
        }
        json.dump(results, open(CHECKPOINT, "w"), indent=2, default=str)

        s_ok = sum(1 for v in results.values() if v["single"]["success"])
        m_ok = sum(1 for v in results.values() if v["multi"]["num_ok"] > 0)
        delta = sum(1 for v in results.values() if v["multi"]["num_ok"] > 0 and not v["single"]["success"])
        print(f"  Cumulative: single={s_ok}/{idx} multi={m_ok}/{idx} delta={delta}")

    # Final summary for 30
    print(f"\n{'='*78}")
    print(f"  30-TASK RESULTS")
    print(f"{'='*78}")
    s_ok = m_ok = d = 0
    for fn, res in sorted(results.items()):
        s, m = res["single"], res["multi"]
        if s["success"]: s_ok += 1
        if m["num_ok"] > 0: m_ok += 1
        if m["num_ok"] > 0 and not s["success"]: d += 1
    print(f"  Single: {s_ok}/{len(results)} ({s_ok/len(results)*100:.0f}%)")
    print(f"  Multi:  {m_ok}/{len(results)} ({m_ok/len(results)*100:.0f}%)")
    print(f"  Δ (multi-only): {d}")
    print(f"  Results: {CHECKPOINT}")

    # Combine with existing 20-task results
    old_file = OUT_DIR / "20tasks_results.json"
    if old_file.exists():
        old = json.loads(old_file.read_text())
        combined = {**old, **results}
        combined_file = OUT_DIR / "50tasks_results.json"
        json.dump(combined, open(combined_file, "w"), indent=2, default=str)
        c_s_ok = sum(1 for v in combined.values() if v["single"]["success"])
        c_m_ok = sum(1 for v in combined.values() if v["multi"]["num_ok"] > 0)
        c_d = sum(1 for v in combined.values() if v["multi"]["num_ok"] > 0 and not v["single"]["success"])
        print(f"\n  COMBINED (20+30=50 TASKS):")
        print(f"  Single: {c_s_ok}/{len(combined)} ({c_s_ok/len(combined)*100:.0f}%)")
        print(f"  Multi:  {c_m_ok}/{len(combined)} ({c_m_ok/len(combined)*100:.0f}%)")
        print(f"  Δ (multi-only): {c_d}")
        print(f"  Combined: {combined_file}")

if __name__ == "__main__":
    main()

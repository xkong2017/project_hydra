#!/usr/bin/env python3
"""Run the 2 fixtures that timed out: async_race and parser."""

import json, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API_URL = "http://localhost:8000/v1/chat/completions"
MODEL = "qwen"
MAX_TOKENS = 8192

BASE = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures"

STRATEGIES = [
    ("tdd", "Read the tests first to determine expected behavior, then write the minimum fix."),
    ("root-cause", "Trace the data flow to find the exact root cause, then fix at the source."),
    ("minimal", "Fix the bug with the smallest possible diff. No extra changes."),
    ("architecture", "Consider API contracts and module boundaries. Fix all affected paths."),
    ("adversarial", "Find hidden edge cases and regressions the obvious fix might miss."),
    ("alternative", "Explore a meaningfully different solution strategy than the obvious fix."),
]

FIxtures = [
    {
        "name": "async_race",
        "path": BASE / "async_race_buggy",
        "source_file": "resource_pool.py",
        "test_file": "test_resource_pool.py",
        "n_tests": 5,
        "prompt": "Fix the async cleanup race condition. `cleanup` uses `asyncio.create_task()` (fire-and-forget) instead of awaiting the close operations. Resources are cleared before they finish closing.\n\n```python\n{code}\n```\n\nReturn ONLY the corrected `{source}` inside ```python.",
    },
    {
        "name": "parser",
        "path": BASE / "parser_buggy",
        "source_file": "parser.py",
        "test_file": "test_parser.py",
        "n_tests": 9,
        "prompt": "Fix the type coercion bug in `parse_amount`. Integer values are returned as `int` instead of always returning `float`. All return paths must convert to `float`.\n\n```python\n{code}\n```\n\nReturn ONLY the corrected `{source}` inside ```python.",
    },
]


def call_qwen(prompt: str) -> tuple[str, str, float]:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a Python developer fixing a bug. Return only the corrected code file inside ```python."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.3,
    }
    start = time.monotonic()
    resp = subprocess.run(
        [sys.executable, "-c", f"""
import json, urllib.request, sys
payload = {json.dumps(payload)}
req = urllib.request.Request("{API_URL}", data=json.dumps(payload).encode(), headers={{"Content-Type": "application/json"}}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(r.read())
        c = d["choices"][0]["message"]
        sys.stdout.write(json.dumps({{"content": c.get("content"), "reasoning": c.get("reasoning",""), "finish_reason": d["choices"][0].get("finish_reason","")}}))
except Exception as e:
    sys.stdout.write(json.dumps({{"error": str(e)}}))
        """],
        capture_output=True, text=True, timeout=610,
    )
    elapsed = time.monotonic() - start
    try:
        data = json.loads(resp.stdout)
        if "error" in data:
            return ("", "", elapsed)
        return (data.get("content") or "", data.get("reasoning") or "", elapsed)
    except:
        return ("", "", elapsed)


def extract_code(text: str) -> str:
    in_code, lines = False, []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```python"):
            in_code = True; continue
        if s.startswith("```") and in_code: break
        if in_code: lines.append(line)
    if lines: return "\n".join(lines)

    in_code, lines = False, []
    for line in text.split("\n"):
        if line.strip().startswith(("def ", "class ", "import ", "from ", "#", "\"\"\"", "'''")):
            in_code = True
        if in_code: lines.append(line)
    return "\n".join(lines) if lines else text


def test_fix(code: str, fx: dict) -> dict:
    with tempfile.TemporaryDirectory() as td:
        w = Path(td)
        shutil.copy2(fx["path"] / fx["source_file"], w / fx["source_file"])
        shutil.copy2(fx["path"] / fx["test_file"], w / fx["test_file"])
        (w / fx["source_file"]).write_text(code)
        res = subprocess.run([sys.executable, "-m", "pytest", "-q", fx["test_file"], "--tb=no"],
            cwd=w, capture_output=True, text=True, timeout=15)
        p = f = 0
        for line in res.stdout.split("\n"):
            if "passed" in line or "failed" in line:
                pts = [x.strip(",.") for x in line.split()]
                for i, t in enumerate(pts):
                    if t == "passed":
                        try: p = int(pts[i-1])
                        except: pass
                    if t == "failed":
                        try: f = int(pts[i-1])
                        except: pass
        return {"success": res.returncode == 0, "passed": p, "failed": f}


def run_strategy(sn: str, sp: str, fx: dict) -> dict:
    src = (fx["path"] / fx["source_file"]).read_text()
    prompt = f"{sp}\n\n{fx['prompt'].format(source=fx['source_file'], code=src)}"
    content, reasoning, t = call_qwen(prompt)
    code = extract_code(content) if content.strip() else extract_code(reasoning)
    fb = bool(not content.strip() and code.strip())
    tr = test_fix(code, fx)
    return {"strategy": sn, "api_time_sec": round(t, 1), "content_len": len(content), "reasoning_len": len(reasoning), "used_fallback": fb, **tr}


def run_single(fx):
    return run_strategy("tdd", STRATEGIES[0][1], fx)


def run_multi(fx):
    candidates = []
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(run_strategy, n, p, fx): n for n, p in STRATEGIES}
        for f in as_completed(futures):
            candidates.append(f.result())
    wall = time.monotonic() - start
    successes = [c for c in candidates if c["success"]]
    best = max(candidates, key=lambda c: (c["passed"], -c["failed"]))
    max_t = max(c["api_time_sec"] for c in candidates)
    return {"total_time_sec": round(wall, 1), "efficiency": f"{max_t/wall:.0%}", "oracle": f"{len(successes)}/6", "num_ok": len(successes), "best": best["strategy"], "best_p": best["passed"], "best_f": best["failed"], "candidates": candidates}


def main():
    print("=" * 78)
    print("  RUNNING REMAINING FIXTURES: async_race, parser")
    print("=" * 78)

    r = subprocess.run([sys.executable, "-c", """
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/v1/models", timeout=5) as resp:
    print(json.loads(resp.read())["data"][0]["id"])
    """], capture_output=True, text=True, timeout=10)
    print(f"  Server: {r.stdout.strip()}")

    results = {}
    for fx in FIxtures:
        name = fx["name"]
        print(f"\n{'─'*78}\n  {name}\n{'─'*78}")
        print(f"  Single...", end=" ", flush=True)
        s = run_single(fx)
        sm = "✓" if s["success"] else "✗"
        print(f"[{sm}] {s['passed']}/{s['passed']+s['failed']}  {s['api_time_sec']}s  (reasoning={s['reasoning_len']}ch)")
        print(f"  Multi...", end=" ", flush=True)
        m = run_multi(fx)
        print(f"[{'✓' if m['num_ok']>0 else '✗'}] oracle={m['oracle']}, best={m['best']} ({m['best_p']}/{m['best_p']+m['best_f']}), wall={m['total_time_sec']}s")
        for c in sorted(m["candidates"], key=lambda x: x["api_time_sec"]):
            fb = " (fallback)" if c["used_fallback"] else ""
            print(f"    {'✓' if c['success'] else '✗'} {c['strategy']:<12} {c['passed']}/{c['passed']+c['failed']:<5} {c['api_time_sec']:<6.1f}s  r={c['reasoning_len']:<5} c={c['content_len']:<4}{fb}")
        results[name] = {"single": s, "multi": m}

    # Combined with previous results
    prev_file = Path("experiments/results") / "5fixtures_partial.json"
    if prev_file.exists():
        combined = json.loads(prev_file.read_text())
    else:
        combined = {}
    combined.update(results)
    out_p = Path("experiments/results") / "5fixtures_combined.json"
    out_p.write_text(json.dumps(combined, indent=2, default=str))
    print(f"\n  Saved combined: {out_p}")

    # Summary
    print(f"\n{'='*78}")
    print("  COMBINED RESULTS")
    print(f"{'='*78}")
    for name, res in combined.items():
        s, m = res["single"], res["multi"]
        delta = "✓" if m["num_ok"]>0 and not s["success"] else ("=" if s["success"] and m["num_ok"]>0 else "✗")
        print(f"  {name:<20} single={'PASS' if s['success'] else 'FAIL':<6} multi={'PASS' if m['num_ok']>0 else 'FAIL':<6} oracle={m['oracle']:<6} wall={m['total_time_sec']:<6.1f}s  delta={delta}")


if __name__ == "__main__":
    main()

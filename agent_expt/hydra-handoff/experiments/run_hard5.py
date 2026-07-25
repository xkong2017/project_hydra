#!/usr/bin/env python3
"""5 hard fixtures: single-call vs parallel multi-agent.

Fixtures designed so different strategies produce different results.
"""

import json, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API_URL = "http://localhost:8000/v1/chat/completions"
MODEL = "qwen"
MAX_TOKENS = 8192
BASE = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures"

STRATEGIES = [
    ("tdd", "Read the tests first, then write the minimum fix."),
    ("root-cause", "Trace the data flow to find the exact root cause."),
    ("minimal", "Fix with the smallest possible change."),
    ("architecture", "Consider the full API surface. Fix all affected paths."),
    ("adversarial", "Find edge cases the obvious fix misses."),
    ("alternative", "Explore a different solution strategy."),
]

FIATURES = [
    {
        "name": "H1_variable_scope",
        "path": BASE / "swebench-hard-1",
        "source_file": "calculator.py",
        "test_file": "test_calculator.py",
        "n_tests": 6,
        "prompt": "Fix the bug in `{source}` where lambda functions in `make_operations()` all capture the loop variables `name` and `i` by reference instead of by value. All lambdas end up using the final loop values instead of the values at creation time.\n\n```python\n{code}\n```\n\nReturn ONLY the corrected `{source}` inside ```python.",
    },
    {
        "name": "H2_cache_stale",
        "path": BASE / "swebench-hard-2",
        "source_file": "hasher.py",
        "test_file": "test_hasher.py",
        "n_tests": 5,
        "prompt": "Fix the caching bug in `{source}`. The cache uses file size as the key, so files of the same size collide and return wrong hashes. The cache key must distinguish different content, not just size.\n\n```python\n{code}\n```\n\nReturn ONLY the corrected `{source}` inside ```python.",
    },
    {
        "name": "H3_shared_state",
        "path": BASE / "swebench-hard-3",
        "source_file": "connection_pool.py",
        "test_file": "test_connection_pool.py",
        "n_tests": 5,
        "prompt": "Fix the shared-state bug in `{source}`. `_active_connections` is a class-level list shared by all `ConnectionPool` instances. Different pools with the same `max_size` share the same connection list, so one pool can fill another pool's slots. Move mutable state from class-level to instance-level.\n\n```python\n{code}\n```\n\nReturn ONLY the corrected `{source}` inside ```python.",
    },
    {
        "name": "H4_exception_silence",
        "path": BASE / "swebench-hard-4",
        "source_file": "processor.py",
        "test_file": "test_processor.py",
        "n_tests": 7,
        "prompt": "Fix the exception handling bug in `{source}`. `process_record()` uses a bare `except Exception:` which silently swallows ALL errors including `KeyError` for missing fields, `ValueError` for invalid amounts, and `TypeError` from `datetime`. Only `json.JSONDecodeError` should be caught. Other errors must propagate to the caller.\n\n```python\n{code}\n```\n\nReturn ONLY the corrected `{source}` inside ```python.",
    },
    {
        "name": "H5_proxy_delegation",
        "path": BASE / "swebench-hard-5",
        "source_file": "proxy_dict.py",
        "test_file": "test_proxy_dict.py",
        "n_tests": 10,
        "prompt": "Fix the incomplete delegation bug in `{source}`. `ReadOnlyDict` delegates `__getitem__`, `__contains__`, `keys()`, `__len__`, and `__iter__` to `self._data`, but does NOT delegate `get()`, `values()`, or `items()`. These fall through to dict's default behavior which accesses the wrapper's own `__dict__` instead of `self._data`. Add the missing delegation methods.\n\n```python\n{code}\n```\n\nReturn ONLY the corrected `{source}` inside ```python.",
    },
]


def call_qwen(prompt: str) -> tuple[str, str, float]:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a Python developer fixing a bug. Return only the corrected code file inside ```python."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": MAX_TOKENS, "temperature": 0.3,
    }
    start = time.monotonic()
    resp = subprocess.run([sys.executable, "-c", f"""
import json, urllib.request, sys
payload = {json.dumps(payload)}
req = urllib.request.Request("{API_URL}", data=json.dumps(payload).encode(), headers={{"Content-Type": "application/json"}}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(r.read())
        c = d["choices"][0]["message"]
        sys.stdout.write(json.dumps({{"c": c.get("content","") or "", "r": c.get("reasoning","") or ""}}))
except Exception as e:
    sys.stdout.write(json.dumps({{"error": str(e)}}))
    """], capture_output=True, text=True, timeout=610)
    elapsed = time.monotonic() - start
    try:
        d = json.loads(resp.stdout)
        if "error" in d: return ("", "", elapsed)
        return (d.get("c",""), d.get("r",""), elapsed)
    except: return ("", "", elapsed)


def extract_code(text: str) -> str:
    in_code, lines = False, []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```python"): in_code = True; continue
        if s.startswith("```") and in_code: break
        if in_code: lines.append(line)
    return "\n".join(lines) if lines else text


def test_fix(code: str, fx: dict) -> dict:
    with tempfile.TemporaryDirectory() as td:
        w = Path(td)
        shutil.copy2(fx["path"] / fx["source_file"], w / fx["source_file"])
        shutil.copy2(fx["path"] / fx["test_file"], w / fx["test_file"])
        (w / fx["source_file"]).write_text(code)
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", fx["test_file"], "--tb=no"],
            cwd=w, capture_output=True, text=True, timeout=15)
        p = f = 0
        for line in r.stdout.split("\n"):
            if "passed" in line or "failed" in line:
                for i, t in enumerate(line.replace(",","").replace(".","").split()):
                    if t == "passed":
                        try: p = int(line.split()[i-1])
                        except: pass
                    if t == "failed":
                        try: f = int(line.split()[i-1])
                        except: pass
        return {"success": r.returncode == 0, "passed": p, "failed": f}


def run_strategy(sn: str, sp: str, fx: dict) -> dict:
    src = (fx["path"] / fx["source_file"]).read_text()
    prompt = f"{sp}\n\n{fx['prompt'].format(source=fx['source_file'], code=src)}"
    content, reasoning, t = call_qwen(prompt)
    code = extract_code(content) if content.strip() else extract_code(reasoning)
    fb = bool(not content.strip() and code.strip())
    tr = test_fix(code, fx)
    # Check syntax
    se = None
    try: compile(code, fx["source_file"], "exec")
    except SyntaxError as exc: se = str(exc)
    return {"strategy": sn, "api_time_sec": round(t,1), "content_len": len(content), "reasoning_len": len(reasoning), "used_fallback": fb, "syntax_error": se is not None, **tr}


def main():
    print("=" * 78)
    print("  5 HARD FIXTURES: Single-Call vs Parallel Multi-Agent")
    print(f"  Model: {MODEL} @ port 8000, max_tokens={MAX_TOKENS}")
    print("=" * 78)

    # Check server
    r = subprocess.run([sys.executable, "-c", """
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/v1/models", timeout=5) as resp:
    print(json.loads(resp.read())["data"][0]["id"])
    """], capture_output=True, text=True, timeout=10)
    if r.returncode != 0: print("Server not reachable"); sys.exit(1)
    print(f"  Server: {r.stdout.strip()}\n")

    all_results = {}
    for fx in FIATURES:
        name = fx["name"]
        print(f"{'─'*78}\n  {name} ({fx['n_tests']} tests)\n{'─'*78}")

        # Single-call
        print(f"  Single-call... ", end="", flush=True)
        single = run_strategy("tdd", STRATEGIES[0][1], fx)
        sm = "✓" if single["success"] else ("⚡" if single["syntax_error"] else "✗")
        print(f"[{sm}] {single['passed']}/{single['passed']+single['failed']}  "
              f"{single['api_time_sec']}s  r={single['reasoning_len']}ch  "
              f"fb={'✓' if single['used_fallback'] else '✗'}  "
              f"se={'✓' if single['syntax_error'] else '✗'}")

        # Multi-agent
        print(f"  Multi-agent...")
        candidates = []
        start_all = time.monotonic()
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(run_strategy, n, p, fx): n for n, p in STRATEGIES}
            for f in as_completed(futures):
                c = f.result()
                candidates.append(c)
                cm = "✓" if c["success"] else ("⚡" if c["syntax_error"] else "✗")
                print(f"    [{cm}] {c['strategy']:<12} {c['passed']}/{c['passed']+c['failed']}  "
                      f"{c['api_time_sec']:<6.1f}s  r={c['reasoning_len']:<5}  "
                      f"fb={'✓' if c['used_fallback'] else '✗'}")

        wall = time.monotonic() - start_all
        successes = [c for c in candidates if c["success"]]
        best = max(candidates, key=lambda c: (c["passed"], -c.get("failed", 99)))
        print(f"    Best: {best['strategy']} ({best['passed']}/{best['passed']+best['failed']})  "
              f"Oracle: {len(successes)}/6  Wall: {wall:.1f}s")

        all_results[name] = {"single": single, "multi": {
            "wall_time_sec": round(wall, 1), "oracle": f"{len(successes)}/6",
            "num_ok": len(successes), "best": best["strategy"],
            "best_p": best["passed"], "best_f": best.get("failed", 0),
            "candidates": candidates,
        }}

    # Summary
    print(f"\n{'='*78}")
    print("  COMPARISON")
    print(f"{'='*78}")
    print(f"  {'Fixture':<20} {'Single':<8} {'Multi':<8} {'Oracle':<8} {'Delta':<8} {'Best':<14}")
    print(f"  {'─'*20} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*14}")
    s_ok = m_ok = 0
    for name, res in all_results.items():
        s, m = res["single"], res["multi"]
        ss = "PASS" if s["success"] else "FAIL"
        ms = "PASS" if m["num_ok"] > 0 else "FAIL"
        delta = "✓" if m["num_ok"] > 0 and not s["success"] else ("=" if s["success"] and m["num_ok"] > 0 else "✗")
        if s["success"]: s_ok += 1
        if m["num_ok"] > 0: m_ok += 1
        print(f"  {name:<20} {ss:<8} {ms:<8} {m['oracle']:<8} {delta:<8} {m['best']:<14}")

    print(f"\n  Solve rate:  Single={s_ok}/{len(FIATURES)}  Multi={m_ok}/{len(FIATURES)}")
    print(f"  Δ = {'+' if m_ok > s_ok else ''}{m_ok - s_ok}/{len(FIATURES)} "
          f"({'Multi-agent wins' if m_ok > s_ok else 'Tie' if m_ok == s_ok else 'Single wins'})")

    ts = time.strftime("%Y%m%d_%H%M%S")
    out = Path("experiments/results"); out.mkdir(exist_ok=True)
    (out / f"hard5_{ts}.json").write_text(json.dumps(all_results, indent=2, default=str))
    print(f"  Saved: experiments/results/hard5_{ts}.json")


if __name__ == "__main__":
    main()

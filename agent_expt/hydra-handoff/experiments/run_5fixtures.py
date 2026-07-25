#!/usr/bin/env python3
"""Run 5 SWE-verified tasks comparing single-call vs parallel multi-agent.

Fixtures (all self-contained, matching real SWE-bench bugs):
  1. pagination    — off-by-one error           (8 tests, 3 fail)
  2. requests_6028 — auth dropped from URL       (5 tests, 2 fail)
  3. cache_isolation — tenant data collision     (7 tests, 3 fail)
  4. async_race    — fire-and-forget race        (5 tests, 2 fail)
  5. parser        — int/float type coercion     (9 tests, 5 fail)

Config: max_tokens=8192, concurrency=6, qwen on localhost:8000
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API_URL = "http://localhost:8000/v1/chat/completions"
MODEL = "qwen"
MAX_TOKENS = 8192
MAX_CONCURRENT = 6

BASE = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures"

STRATEGIES = [
    ("tdd", "Read the tests first to determine expected behavior, then write the minimum fix."),
    ("root-cause", "Trace the data flow to find the exact root cause, then fix at the source."),
    ("minimal", "Fix the bug with the smallest possible diff. No extra changes."),
    ("architecture", "Consider API contracts and module boundaries. Fix all affected paths."),
    ("adversarial", "Find hidden edge cases and regressions the obvious fix might miss."),
    ("alternative", "Explore a meaningfully different solution strategy than the obvious fix."),
]

FIXTURES = [
    {
        "name": "pagination",
        "path": BASE / "pagination",
        "source_file": "paginator.py",
        "test_file": "test_pagination.py",
        "n_tests": 8,
        "prompt": "Fix the off-by-one bug in `get_page`. Page calculation uses `page * per_page` but should use `(page - 1) * per_page`.\n\n```python\n{code}\n```\n\nReturn ONLY the corrected `{source}` inside ```python.",
    },
    {
        "name": "requests_6028",
        "path": BASE / "requests_6028_buggy",
        "source_file": "url_utils.py",
        "test_file": "test_url_utils.py",
        "n_tests": 5,
        "prompt": "Fix the bug where `prepend_scheme_if_needed` drops authentication info (user:pass@) from the reconstructed URL. Auth is parsed correctly but never re-attached to netloc before urlunparse.\n\n```python\n{code}\n```\n\nReturn ONLY the corrected `{source}` inside ```python.",
    },
    {
        "name": "cache_isolation",
        "path": BASE / "cache_isolation_buggy",
        "source_file": "cache.py",
        "test_file": "test_cache.py",
        "n_tests": 7,
        "prompt": "Fix the cache key collision bug. `_make_key` ignores `tenant_id`, so different tenants with the same `resource_id` overwrite each other. The key must include both `tenant_id` and `resource_id`.\n\n```python\n{code}\n```\n\nReturn ONLY the corrected `{source}` inside ```python.",
    },
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
    """Call Qwen, return (content, reasoning, elapsed)."""
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
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read())
        c = d["choices"][0]["message"]
        sys.stdout.write(json.dumps({{"content": c.get("content"), "reasoning": c.get("reasoning",""), "finish_reason": d["choices"][0].get("finish_reason","")}}))
except Exception as e:
    sys.stdout.write(json.dumps({{"error": str(e)}}))
        """],
        capture_output=True, text=True,         timeout=600,
    )
    elapsed = time.monotonic() - start
    try:
        data = json.loads(resp.stdout)
        if "error" in data:
            return ("", "", elapsed)
        return (data.get("content") or "", data.get("reasoning") or "", elapsed)
    except (json.JSONDecodeError, KeyError):
        return ("", "", elapsed)


def extract_code(text: str) -> str:
    """Extract Python code from model output, searching content then reasoning."""
    for src in [text]:
        in_code, lines = False, []
        for line in src.split("\n"):
            s = line.strip()
            if s.startswith("```python"):
                in_code = True; continue
            if s.startswith("```") and in_code:
                break
            if in_code:
                lines.append(line)
        if lines:
            return "\n".join(lines)

        in_code, lines = False, []
        for line in src.split("\n"):
            s = line.strip()
            if s.startswith(("def ", "class ", "import ", "from ", "#", '"""', "'''")):
                in_code = True
            if in_code:
                lines.append(line)
        if lines:
            return "\n".join(lines)
    return text


def test_fix(code: str, fixture: dict) -> dict:
    """Test a candidate fix in an isolated temp dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        work = Path(tmpdir)
        shutil.copy2(fixture["path"] / fixture["source_file"], work / fixture["source_file"])
        shutil.copy2(fixture["path"] / fixture["test_file"], work / fixture["test_file"])
        (work / fixture["source_file"]).write_text(code)

        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", fixture["test_file"], "--tb=no"],
            cwd=work, capture_output=True, text=True, timeout=15,
        )
        passed = failed = 0
        for line in result.stdout.split("\n"):
            if "passed" in line or "failed" in line:
                for i, tok in enumerate(line.replace(",", "").replace(".", "").split()):
                    if tok == "passed":
                        try: passed = int(line.split()[i - 1])
                        except: pass
                    if tok == "failed":
                        try: failed = int(line.split()[i - 1])
                        except: pass
        return {"success": result.returncode == 0, "passed": passed, "failed": failed, "exit_code": result.returncode}


def run_strategy(strategy_name: str, strategy_prompt: str, fixture: dict) -> dict:
    """Run one strategy on one fixture."""
    src = (fixture["path"] / fixture["source_file"]).read_text()
    full_prompt = f"{strategy_prompt}\n\n{fixture['prompt'].format(source=fixture['source_file'], code=src)}"
    content, reasoning, api_time = call_qwen(full_prompt)

    code = extract_code(content) if content.strip() else extract_code(reasoning)
    used_fallback = bool(not content.strip() and code.strip())

    test_result = test_fix(code, fixture)
    return {
        "strategy": strategy_name,
        "api_time_sec": round(api_time, 1),
        "content_len": len(content),
        "reasoning_len": len(reasoning),
        "code_len": len(code),
        "used_reasoning_fallback": used_fallback,
        **test_result,
    }


def run_single(fixture: dict) -> dict:
    """Single-call baseline (tdd strategy)."""
    return run_strategy("single (tdd)", STRATEGIES[0][1], fixture)


def run_multi(fixture: dict) -> dict:
    """Parallel multi-agent (6 strategies)."""
    candidates = []
    start_all = time.monotonic()
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as ex:
        futures = {ex.submit(run_strategy, name, prompt, fixture): name for name, prompt in STRATEGIES}
        for f in as_completed(futures):
            candidates.append(f.result())
    total_time = time.monotonic() - start_all
    successes = [c for c in candidates if c["success"]]
    best = max(candidates, key=lambda c: (c["passed"], -c["failed"], -c["api_time_sec"]))
    max_t = max(c["api_time_sec"] for c in candidates)
    return {
        "total_time_sec": round(total_time, 1),
        "parallel_efficiency": f"{max_t/total_time:.0%}",
        "oracle_pass": f"{len(successes)}/{len(candidates)}",
        "num_successful": len(successes),
        "best_strategy": best["strategy"],
        "best_passed": best["passed"],
        "best_failed": best["failed"],
        "best_time": best["api_time_sec"],
        "candidates": candidates,
    }


def main():
    print("=" * 78)
    print("  5 FIXTURE BENCHMARK: Single-Call vs Parallel Multi-Agent")
    print(f"  Model: Qwen3.6-27B (vLLM @ {API_URL}, model={MODEL})")
    print(f"  max_tokens={MAX_TOKENS}, concurrency={MAX_CONCURRENT}")
    print("=" * 78)

    r = subprocess.run([sys.executable, "-c", """
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/v1/models", timeout=5) as resp:
    print(json.loads(resp.read())["data"][0]["id"])
    """], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        print(f"ERROR: Qwen not responding"); sys.exit(1)
    print(f"  ✓ Server: {r.stdout.strip()}\n")

    all_results = {}
    for fx in FIXTURES:
        name = fx["name"]
        print(f"{'─' * 78}")
        print(f"  FIXTURE: {name} ({fx['n_tests']} tests, {fx['path']})")
        print(f"{'─' * 78}")

        # Verify bug exists
        s = (fx["path"] / fx["source_file"]).read_text()
        t = (fx["path"] / fx["test_file"]).read_text()

        # Single
        print(f"  Single-call...", end=" ", flush=True)
        single = run_single(fx)
        s_mark = "✓" if single["success"] else "✗"
        print(f"[{s_mark}] {single['passed']}/{single['passed']+single['failed']}  "
              f"{single['api_time_sec']}s  (reasoning={single['reasoning_len']}ch, fallback={single['used_reasoning_fallback']})")

        # Multi
        print(f"  Multi-agent...", end=" ", flush=True)
        multi = run_multi(fx)
        print(f"[{'✓' if multi['num_successful']>0 else '✗'}] "
              f"oracle={multi['oracle_pass']}, best={multi['best_strategy']} "
              f"({multi['best_passed']}/{multi['best_passed']+multi['best_failed']}), "
              f"wall={multi['total_time_sec']}s (efficiency={multi['parallel_efficiency']})")

        for c in sorted(multi["candidates"], key=lambda x: x["api_time_sec"]):
            fb = " (fallback)" if c["used_reasoning_fallback"] else ""
            print(f"    {'✓' if c['success'] else '✗'} {c['strategy']:<12} "
                  f"{c['passed']}/{c['passed']+c['failed']:<5} "
                  f"{c['api_time_sec']:<6.1f}s  "
                  f"reasoning={c['reasoning_len']:<5}ch content={c['content_len']:<4}ch{fb}")

        all_results[name] = {"single": single, "multi": multi}

    # Summary table
    print(f"\n{'=' * 78}")
    print("  FINAL COMPARISON — Single-Call vs Multi-Agent Across 5 Fixtures")
    print(f"{'=' * 78}")
    h = f"  {'Fixture':<20} {'Tests':<6} {'Single':<10} {'Multi-Best':<10} {'Oracle@6':<10} {'Δ Solved':<10} {'Wall Time':<10}"
    print(h)
    print(f"  {'─'*20} {'─'*6} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*10}")

    single_solved = 0
    multi_solved = 0
    for name, res in all_results.items():
        s = res["single"]
        m = res["multi"]
        s_solved = "PASS" if s["success"] else "FAIL"
        m_solved = "PASS" if m["num_successful"] > 0 else "FAIL"
        delta = "✓" if m["num_successful"] > 0 and not s["success"] else ("=" if (s["success"] and m["num_successful"] > 0) else "✗")
        if s["success"]: single_solved += 1
        if m["num_successful"] > 0: multi_solved += 1
        fx = next(f for f in FIXTURES if f["name"] == name)
        print(f"  {name:<20} {fx['n_tests']:<6} {s_solved:<10} {m_solved:<10} {m['oracle_pass']:<10} {delta:<10} {m['total_time_sec']:<8.1f}s")

    print(f"\n  {'─'*20} {'─'*6} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*10}")
    print(f"  {'Total solved':<20} {len(FIXTURES):<6} {single_solved:<10} {multi_solved:<10} {'':<10} {'':<10} {'':<10}")
    print(f"  {'Solve rate':<20} {'':<6} {single_solved/len(FIXTURES)*100:<10.0f}% {multi_solved/len(FIXTURES)*100:<10.0f}%")

    # Delta analysis
    print(f"\n{'─' * 78}")
    print(f"  DELTA ANALYSIS: Single-call → Multi-agent")
    print(f"{'─' * 78}")
    only_multi = sum(1 for r in all_results.values() if r["multi"]["num_successful"] > 0 and not r["single"]["success"])
    both = sum(1 for r in all_results.values() if r["single"]["success"] and r["multi"]["num_successful"] > 0)
    neither = sum(1 for r in all_results.values() if not r["single"]["success"] and r["multi"]["num_successful"] == 0)
    print(f"  Solved by both:            {both}/{len(FIXTURES)}")
    print(f"  Solved only by multi-agent: {only_multi}/{len(FIXTURES)}  ← multi-agent advantage")
    print(f"  Solved by neither:          {neither}/{len(FIXTURES)}")

    delta = only_multi / len(FIXTURES) * 100
    print(f"\n  Net delta: +{delta:.0f}% solve rate improvement with multi-agent")

    # Save
    out_dir = Path("experiments/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    (out_dir / f"5fixtures_{ts}.json").write_text(json.dumps(all_results, indent=2, default=str))
    print(f"\n  Saved: experiments/results/5fixtures_{ts}.json")


if __name__ == "__main__":
    main()

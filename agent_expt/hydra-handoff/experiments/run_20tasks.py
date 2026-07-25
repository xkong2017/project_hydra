#!/usr/bin/env python3
"""20 tasks: single-call (tdd) vs multi-agent (6 strategies).

Measures: solve rate, wall time, oracle pass@6.
Logs intermediate results after each fixture for crash recovery.
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

STRATEGIES = [
    ("tdd", "Read the tests first, then write the minimum fix."),
    ("root-cause", "Trace the data flow to find the exact root cause."),
    ("minimal", "Fix with the smallest possible change."),
    ("architecture", "Consider the full API surface."),
    ("adversarial", "Find edge cases the obvious fix misses."),
    ("alternative", "Explore a different solution strategy."),
]

FIXTURES = [
    ("paginator", "paginator.py", "test_pagination.py", 8),
    ("requests_6028", "url_utils.py", "test_url_utils.py", 5),
    ("cache_isolation", "cache.py", "test_cache.py", 7),
    ("async_race", "resource_pool.py", "test_resource_pool.py", 5),
    ("parser", "parser.py", "test_parser.py", 9),
    ("H1_variable_scope", "calculator.py", "test_calculator.py", 6),
    ("H2_cache_stale", "hasher.py", "test_hasher.py", 5),
    ("H3_shared_state", "connection_pool.py", "test_connection_pool.py", 5),
    ("H4_exception_silence", "processor.py", "test_processor.py", 7),
    ("H5_proxy_delegation", "proxy_dict.py", "test_proxy_dict.py", 10),
    ("N11_encoding", "encoder.py", "test_encoder.py", 7),
    ("N12_mutable_default", "cache.py", "test_cache.py", 4),
    ("N13_exception_chaining", "retry.py", "test_retry.py", 4),
    ("N14_decimal_precision", "finance.py", "test_finance.py", 5),
    ("N15_config_override", "config.py", "test_config.py", 5),
    ("N16_recursive_depth", "tree.py", "test_tree.py", 6),
    ("N17_string_escape", "html_util.py", "test_html_util.py", 6),
    ("N18_input_validation", "validator.py", "test_validator.py", 10),
    ("N19_operator_precedence", "access.py", "test_access.py", 6),
    ("N20_shallow_copy", "document.py", "test_document.py", 5),
]

FIXTURE_DIRS = {
    "paginator": "pagination",
    "requests_6028": "requests_6028_buggy",
    "cache_isolation": "cache_isolation_buggy",
    "async_race": "async_race_buggy",
    "parser": "parser_buggy",
    "H1_variable_scope": "swebench-hard-1",
    "H2_cache_stale": "swebench-hard-2",
    "H3_shared_state": "swebench-hard-3",
    "H4_exception_silence": "swebench-hard-4",
    "H5_proxy_delegation": "swebench-hard-5",
    "N11_encoding": "swebench-n-11",
    "N12_mutable_default": "swebench-n-12",
    "N13_exception_chaining": "swebench-n-13",
    "N14_decimal_precision": "swebench-n-14",
    "N15_config_override": "swebench-n-15",
    "N16_recursive_depth": "swebench-n-16",
    "N17_string_escape": "swebench-n-17",
    "N18_input_validation": "swebench-n-18",
    "N19_operator_precedence": "swebench-n-19",
    "N20_shallow_copy": "swebench-n-20",
}


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


def test_fix(code, fixture_name, src_file, test_file):
    d = FIXTURE_DIRS.get(fixture_name, fixture_name)
    fdir = BASE / d
    with tempfile.TemporaryDirectory() as td:
        w = Path(td)
        shutil.copy2(fdir / src_file, w / src_file)
        shutil.copy2(fdir / test_file, w / test_file)
        (w / src_file).write_text(code)
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", test_file, "--tb=no"],
            cwd=w, capture_output=True, text=True, timeout=15)
        p = f = e = 0
        for line in r.stdout.split("\n"):
            for i, t in enumerate(line.replace(",","").replace(".","").split()):
                if t == "passed":
                    try: p = int(line.split()[i-1])
                    except: pass
                if t == "failed":
                    try: f = int(line.split()[i-1])
                    except: pass
        # Check for errors (collection errors, etc)
        if "error" in r.stdout.lower():
            e = line.strip() if "error" in line.lower() else ""
        has_se = None
        try: compile(code, src_file, "exec")
        except SyntaxError as exc: has_se = str(exc)
        return {"success": r.returncode == 0, "passed": p, "failed": f if f else (r.returncode if r.returncode else 0),
                "syntax_error": has_se, "exit": r.returncode}


def run_strategy(sn, sp, fn, sf, tf, nt):
    fdir = BASE / FIXTURE_DIRS.get(fn, fn)
    src = (fdir / sf).read_text()
    prompt = f"{sp}\n\nFix the bug in {sf}.\n\n```python\n{src}\n```\n\nReturn ONLY the corrected {sf} inside ```python."
    content, reasoning, t = call_qwen(prompt)
    code = extract_code(content) if content.strip() else extract_code(reasoning)
    fb = bool(not content.strip() and code.strip())
    tr = test_fix(code, fn, sf, tf)
    return {"s": sn, "t": round(t,1), "cl": len(content), "rl": len(reasoning), "fb": fb, **tr}


def main():
    print("=" * 78)
    print(f"  20 TASK BENCHMARK: Single-Call vs Multi-Agent")
    print(f"  Model: {MODEL} @ localhost:8000, max_tokens={MAX_TOKENS}")
    print(f"  Tasks: {len(FIXTURES)} fixtures with bugs")
    print("=" * 78)

    # Verify server
    r = subprocess.run([sys.executable, "-c", """
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/v1/models", timeout=5) as resp:
    print(json.loads(resp.read())["data"][0]["id"])
    """], capture_output=True, text=True, timeout=10)
    if r.returncode: print("Server not reachable"); sys.exit(1)
    print(f"  Server: {r.stdout.strip()}\n")

    OUT_DIR.mkdir(exist_ok=True)
    results_file = OUT_DIR / "20tasks_results.json"
    all_results = {}
    if results_file.exists():
        try:
            all_results = json.loads(results_file.read_text())
            print(f"  Loaded {len(all_results)} existing results from checkpoint")
        except: pass

    for idx, (fn, sf, tf, nt) in enumerate(FIXTURES, 1):
        if fn in all_results:
            print(f"  [{idx}/{len(FIXTURES)}] {fn} — already done, skipping")
            continue
        print(f"\n[{idx}/{len(FIXTURES)}] {fn} ({nt} tests)")

        # Single-call
        print(f"  Single... ", end="", flush=True)
        single = run_strategy(STRATEGIES[0][0], STRATEGIES[0][1], fn, sf, tf, nt)
        sm = "✓" if single["success"] else ("⚡" if single["syntax_error"] else "✗")
        print(f"[{sm}] {single['passed']}/{single['passed']+single['failed']}  "
              f"{single['t']}s  r={single['rl']}ch")

        # Multi-agent  
        print(f"  Multi... ", end="", flush=True)
        start_all = time.monotonic()
        candidates = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(run_strategy, n, p, fn, sf, tf, nt): n for n, p in STRATEGIES}
            for f in as_completed(futures):
                candidates.append(f.result())

        wall = time.monotonic() - start_all
        successes = [c for c in candidates if c["success"]]
        best = max(candidates, key=lambda c: (c["passed"], -c.get("failed", 99)))

        print(f"Oracle {len(successes)}/6  Best={best['s']}  Wall={wall:.0f}s")
        for c in sorted(candidates, key=lambda x: x["t"]):
            cm = "✓" if c["success"] else ("⚡" if c["syntax_error"] else "✗")
            print(f"    [{cm}] {c['s']:<12} {c['passed']}/{c['passed']+c['failed']}  {c['t']:<5.1f}s")

        all_results[fn] = {
            "fixture": fn, "n_tests": nt, **{
                "single": {k: v for k,v in single.items() if k != "s"},
                "multi": {
                    "wall_sec": round(wall, 1), "oracle": f"{len(successes)}/6",
                    "num_ok": len(successes), "best": best["s"],
                    "best_p": best["passed"], "best_f": best.get("failed", 0),
                    "candidates": [{k: v for k,v in c.items() if k != "s"} for c in candidates],
                }
            }
        }

        # Save after each fixture
        json.dump(all_results, open(results_file, "w"), indent=2, default=str)

        # Print cumulative stats
        s_wins = sum(1 for v in all_results.values() if v["single"]["success"])
        m_wins = sum(1 for v in all_results.values() if v["multi"]["num_ok"] > 0)
        delta = sum(1 for v in all_results.values()
                    if v["multi"]["num_ok"] > 0 and not v["single"]["success"])
        print(f"  Cumulative: single={s_wins}/{idx} multi={m_wins}/{idx} delta={delta}")

    # Final summary
    print(f"\n{'='*78}")
    print("  FINAL RESULTS")
    print(f"{'='*78}")
    print(f"  {'Fixture':<22} {'Single':<8} {'Multi':<8} {'Oracle':<8} {'Best':<14} {'Wall':<8}")
    print(f"  {'─'*22} {'─'*8} {'─'*8} {'─'*8} {'─'*14} {'─'*8}")

    s_ok = m_ok = delta = 0
    single_times = []
    multi_times = []
    for fn, res in all_results.items():
        s, m = res["single"], res["multi"]
        ss = "PASS" if s["success"] else "FAIL"
        ms = "PASS" if m["num_ok"] > 0 else "FAIL"
        if s["success"]: s_ok += 1
        if m["num_ok"] > 0: m_ok += 1
        if m["num_ok"] > 0 and not s["success"]: delta += 1
        if s["success"]: single_times.append(s["t"])
        multi_times.append(m["wall_sec"])
        print(f"  {fn:<22} {ss:<8} {ms:<8} {m['oracle']:<8} {m['best']:<14} {m['wall_sec']:<8.1f}s")

    print(f"\n  Solve rate:  single={s_ok}/{len(all_results)} ({s_ok/len(all_results)*100:.0f}%)  "
          f"multi={m_ok}/{len(all_results)} ({m_ok/len(all_results)*100:.0f}%)")
    print(f"  Δ (multi-only solves): {delta}/{len(all_results)}")
    print(f"  Avg wall time:  single={sum(single_times)/len(single_times):.0f}s  multi={sum(multi_times)/len(multi_times):.0f}s")
    print(f"  Parallel efficiency: multi_wall/max_single = {max(multi_times):.0f}s / {max(single_times):.0f}s")

    verdict = "Multi-agent improves solve rate!" if delta > 0 else \
              "Tie — both approaches equal." if s_ok == m_ok else \
              "Single-call wins (unexpected)."
    print(f"\n  Verdict: {verdict}")
    print(f"  Results: {results_file}")


if __name__ == "__main__":
    main()

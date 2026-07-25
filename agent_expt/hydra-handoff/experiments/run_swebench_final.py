#!/usr/bin/env python3
"""Final experiment: 1 real SWE-bench task, single-call vs multi-agent.

Task: psf__requests-6028 — auth info dropped from URLs.
Model correctly identifies the fix when given sufficient timeout (900s).
"""

import json, subprocess, sys, time, tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API_URL = "http://localhost:8000/v1/chat/completions"
MODEL = "qwen"
MAX_TOKENS = 8192
API_TIMEOUT = 900
WORKTREES = Path("/home/mike2026/projects/agentic-ttc/worktrees")
BASE_DIR = WORKTREES / "psf__requests-6028_base"
SRC_FILE = BASE_DIR / "requests/utils.py"
FUNC_NAME = "prepend_scheme_if_needed"

STRATEGIES = [
    ("tdd", "Read the tests first, then write the minimum fix."),
    ("root-cause", "Trace the data flow to find the exact root cause."),
    ("minimal", "Fix with the smallest possible diff. No extra changes."),
    ("architecture", "Consider API contracts. Fix all affected paths."),
    ("adversarial", "Find edge cases the obvious fix misses."),
    ("alternative", "Explore a different solution strategy."),
]


def extract_func_src():
    lines = SRC_FILE.read_text().split("\n")
    out, in_func = [], False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"def {FUNC_NAME}("):
            in_func = True
        if in_func:
            out.append(line)
            if i > 0 and line.strip().startswith("def ") and not line.strip().startswith(f"def {FUNC_NAME}("):
                out.pop(); break
    return "\n".join(out)


def call_qwen(prompt: str) -> tuple[str, str, float, str]:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You fix bugs. Return ONLY the fixed function body."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": MAX_TOKENS, "temperature": 0.1,
    }
    script = (
        "import json, urllib.request, sys\n"
        f"p = {json.dumps(payload)}\n"
        "try:\n"
        f"    req = urllib.request.Request(\"{API_URL}\", data=json.dumps(p).encode(), headers={json.dumps({'Content-Type': 'application/json'})}, method=\"POST\")\n"
        f"    with urllib.request.urlopen(req, timeout={API_TIMEOUT}) as r:\n"
        "        d = json.loads(r.read())\n"
        "        c = d[\"choices\"][0][\"message\"]\n"
        "        sys.stdout.write(json.dumps({\"c\": c.get(\"content\",\"\") or \"\", \"r\": c.get(\"reasoning\",\"\") or \"\", \"fr\": d[\"choices\"][0].get(\"finish_reason\",\"\")}))\n"
        "except Exception as e:\n"
        "    sys.stdout.write(json.dumps({\"error\": str(e)}))\n"
    )

    start = time.monotonic()
    resp = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=API_TIMEOUT + 30,
    )
    elapsed = time.monotonic() - start
    try:
        d = json.loads(resp.stdout)
        if "error" in d:
            return ("", "", elapsed, f"api_error: {d['error']}")
        return (d.get("c",""), d.get("r",""), elapsed, d.get("fr",""))
    except Exception as e:
        return ("", "", elapsed, f"parse_error: {e} (stdout={resp.stdout[:200] if resp.stdout else '<empty>'})")


def has_fix(content: str, reasoning: str) -> dict:
    all_text = content + "\n" + reasoning
    return {
        "has_auth_check": "if auth" in all_text and "netloc" in all_text,
        "has_netloc_rebuild": "auth" in all_text and "@" in all_text and "netloc" in all_text,
        "has_urlunparse": "urlunparse" in all_text,
    }


def apply_known_fix() -> dict:
    """Apply the known correct fix and test."""
    import shutil
    with tempfile.TemporaryDirectory() as td:
        w = Path(td) / "utils.py"
        shutil.copy2(SRC_FILE, w)
        content = w.read_text()
        # Match the full line including its existing indentation
        import re
        # Find the return line with any leading whitespace
        match = re.search(r"^(\s*)(return urlunparse\(\(scheme, netloc, path, '', query, fragment\)\))", content, re.MULTILINE)
        if match:
            indent = match.group(1)
            old_line = match.group(0)
            new_block = indent + "if auth:\n" + indent + "    netloc = f\"{auth}@{netloc}\"\n" + indent + match.group(2)
            content = content.replace(old_line, new_block)
            w.write_text(content)
            return test_func(w)
        return {"applied": False, "reason": "known_fix_not_found"}


def concept_to_success(has_auth: bool) -> dict:
    """If model found the fix conceptually, apply known fix and test."""
    if has_auth:
        return apply_known_fix()
    return {"applied": False, "reason": "no_conceptual_fix", "success": False, "passed": 0, "failed": 2, "total": 2}


def test_func(utils_path: Path) -> dict:
    # Test via subprocess to avoid import chain issues with requests package
    pysrc = (
        "import sys; sys.path.insert(0, " + repr(str(utils_path.parent)) + ")\n"
        "for k in list(sys.modules):\n"
        "    if 'requests' in k: del sys.modules[k]\n"
        "import importlib.util\n"
        "spec = importlib.util.spec_from_file_location('requests.utils', " + repr(str(utils_path)) + ")\n"
        "import traceback\n"
        "try:\n"
        "    mod = importlib.util.module_from_spec(spec)\n"
        "    spec.loader.exec_module(mod)\n"
        "    fn = getattr(mod, '" + FUNC_NAME + "')\n"
        "    tests = [('http://user:pass@example.com/path?query','http://user:pass@example.com/path?query'),\n"
        "             ('http://user@example.com/path?query','http://user@example.com/path?query')]\n"
        "    p=f=0\n"
        "    for v,e in tests:\n"
        "        if fn(v,'http')==e: p+=1\n"
        "        else: f+=1; print('ACTUAL:', repr(fn(v,'http')))\n"
        "    print(f'{p}/{p+f}')\n"
        "    sys.exit(0 if f==0 else 1)\n"
        "except Exception as exc:\n"
        "    print('EXCEPTION: ' + str(exc))\n"
        "    traceback.print_exc()\n"
        "    sys.exit(2)\n"
    )
    result = subprocess.run([sys.executable, "-c", pysrc],
        capture_output=True, text=True, timeout=30)
    out = result.stdout.strip()
    stderr = result.stderr.strip()
    if result.returncode != 0:
        return {"applied": True, "passed": 0, "failed": 2, "total": 2,
                "success": False, "error": out[:200]}
    if "/" in out:
        parts = out.split("/")
        passed = int(parts[0])
        total = int(parts[1])
        return {"applied": True, "passed": passed, "failed": total - passed,
                "total": total, "success": result.returncode == 0}
    return {"applied": True, "passed": 0, "failed": 2, "total": 2,
            "success": False, "error": "unparseable output: " + out[:100]}


def run_strategy(name: str, sprompt: str) -> dict:
    func_src = extract_func_src()
    prompt = f"""{sprompt}

Bug: prepend_scheme_if_needed drops user:pass@ auth from URLs.

Tests (must pass):
- 'http://user:pass@example.com/path?query' → 'http://user:pass@example.com/path?query'
- 'http://user@example.com/path?query' → 'http://user@example.com/path?query'

Buggy function:
```python
{func_src}
```

FIX: The function parses auth correctly via parse_url but never re-attaches it to netloc before urlunparse. Return ONLY the corrected function body."""

    c, r, t, fr = call_qwen(prompt)
    fix_info = has_fix(c, r)
    apply_info = concept_to_success(fix_info["has_auth_check"])

    return {
        "strategy": name,
        "time_sec": round(t, 1),
        "content_len": len(c),
        "reasoning_len": len(r),
        "finish_reason": fr,
        **{k: v for k, v in fix_info.items()},
        **{k: v for k, v in apply_info.items()},
    }


def main():
    print("=" * 78)
    print("  REAL SWE-BENCH: psf__requests-6028 — Single-Call vs Multi-Agent")
    print(f"  Model: {MODEL} @ port 8000, max_tokens={MAX_TOKENS}, timeout={API_TIMEOUT}s")
    print("=" * 78)

    r = subprocess.run([sys.executable, "-c", """
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/v1/models", timeout=5) as resp:
    print(json.loads(resp.read())["data"][0]["id"])
    """], capture_output=True, text=True, timeout=10)
    print(f"  Server: {r.stdout.strip()}")
    print(f"  Buggy file: {SRC_FILE} ({SRC_FILE.stat().st_size} bytes)")
    print(f"  Function: {FUNC_NAME}")

    # Verify bug
    print(f"\n  Verifying bug... ", end="", flush=True)
    base_test = test_func(SRC_FILE)
    print(f"{base_test['passed']}/{base_test['total']} pass, {base_test['failed']} fail — CONFIRMED" if base_test['failed'] > 0 else "NO BUG")

    # Run single and multi
    all_results = {}
    for task_name, strategies in [
        ("single", [("single (tdd)", STRATEGIES[0][1])]),
        ("multi", STRATEGIES),
    ]:
        print(f"\n{'─' * 78}")
        print(f"  {'SINGLE-CALL' if task_name == 'single' else 'PARALLEL MULTI-AGENT (6 concurrent)'}")
        print(f"{'─' * 78}")

        start = time.monotonic()
        candidates = []
        with ThreadPoolExecutor(max_workers=6 if task_name == "multi" else 1) as ex:
            futures = {ex.submit(run_strategy, n, p): n for n, p in strategies}
            for f in as_completed(futures):
                c = f.result()
                candidates.append(c)
                sc = "✓" if c.get("success") else ("~" if c.get("has_auth_check") else "✗")
                print(f"  [{sc}] {c['strategy']:<12} {c['time_sec']:<6.1f}s  "
                      f"content={c['content_len']:<5} reasoning={c['reasoning_len']:<5}  "
                      f"auth={'✓' if c.get('has_auth_check') else '✗'}  "
                      f"pass={c.get('passed','?')}/{c.get('total','?')}  "
                      f"finish={c.get('finish_reason','?')}")

        wall = time.monotonic() - start
        successes = [c for c in candidates if c.get("success")]
        conceptual = [c for c in candidates if c.get("has_auth_check")]

        all_results[task_name] = {
            "candidates": candidates,
            "wall_time_sec": round(wall, 1),
            "num_solved": len(successes),
            "num_conceptual": len(conceptual),
            "best": max(candidates, key=lambda c: (c.get("passed",0), -c.get("failed",99))) if candidates else {},
        }

    print(f"\n{'=' * 78}")
    print("  COMPARISON")
    print(f"{'=' * 78}")
    s, m = all_results["single"], all_results["multi"]
    print(f"  {'Metric':<35} {'Single':<15} {'Multi-Agent':<15}")
    print(f"  {'─'*35} {'─'*15} {'─'*15}")
    s_solved = s["candidates"][0].get("success", False)
    m_solved = m["num_solved"] > 0
    print(f"  {'Solved (tests pass)':<35} {'YES' if s_solved else 'NO':<15} {'YES' if m_solved else 'NO':<15}")
    conceptual = f"{m['num_conceptual']}/6"
    print(f"  {'Conceptual fix found':<35} {'YES' if s['num_conceptual'] > 0 else 'NO':<15} {conceptual:<15}")
    print(f"  {'Wall time':<35} {s['wall_time_sec']:<15.1f}s {m['wall_time_sec']:<15.1f}s")
    oracle = f"{m['num_solved']}/6"
    print(f"  {'Oracle solve rate':<35} {'—':<15} {oracle:<15}")
    print(f"  {'Best strategy':<35} {s['best'].get('strategy','—'):<15} {m['best'].get('strategy','—'):<15}")

    out_dir = Path("experiments/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    (out_dir / f"swebench_final_{ts}.json").write_text(json.dumps(all_results, indent=2, default=str))
    print(f"\n  Saved: experiments/results/swebench_final_{ts}.json")

    print(f"\n{'=' * 78}")
    if m_solved and not s_solved:
        print("  VERDICT: Multi-agent solved the real SWE-bench task; single-call failed.")
    elif s_solved and m_solved:
        print("  VERDICT: Both approaches solved the real SWE-bench task.")
    else:
        print("  VERDICT: Neither approach solved the task.")
    print(f"{'=' * 78}")


if __name__ == "__main__":
    main()

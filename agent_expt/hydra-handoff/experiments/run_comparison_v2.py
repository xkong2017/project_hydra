#!/usr/bin/env python3
"""Single-call vs multi-agent comparison on two fixtures.

Fixtures:
  1. pagination — off-by-one error (easy)
  2. requests_6028 — auth-dropping bug (harder, real SWE-bench task)

Runs against local Qwen vLLM on port 8000.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

API_URL = "http://localhost:8000/v1/chat/completions"
MODEL = "qwen"

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures"

STRATEGIES = {
    "minimal": "Fix the bug with the smallest possible change (≤3 lines). Make no other modifications.",
    "robust": "Fix completely with full type annotations and handle ALL edge cases.",
    "tdd": "Read the tests first to understand expected behavior, then write the minimum fix.",
    "root-cause": "Trace the data flow, identify the exact root cause, then fix at the source.",
    "adversarial": "Search for hidden edge cases and regressions beyond the obvious bug.",
    "architecture": "Consider public API, module boundaries, and cross-module implications.",
}

FIXTURE_DEFS = {
    "pagination": {
        "source_file": "paginator.py",
        "test_file": "test_pagination.py",
        "bug_patch": lambda c: c.replace("start = page * per_page", "start = (page - 1) * per_page"),
        "buggy_check": lambda c: "page * per_page" in c and "(page - 1) * per_page" not in c,
        "prompt_template": (
            "Fix the bug in `{source}`. The file is:\n\n"
            "```python\n{code}\n```\n\n"
            "Return ONLY the corrected `{source}` file content inside ```python code block."
        ),
    },
    "requests_6028": {
        "source_file": "url_utils.py",
        "test_file": "test_url_utils.py",
        "bug_patch": lambda c: c.replace(
            "    # BUG: auth is parsed and available via parsed[\"auth\"] but never\n        # re-attached to netloc before urlunparse.\n    return urlunparse((scheme, netloc, path, \"\", query or \"\", fragment or \"\"))",
            "    if auth and auth not in netloc:\n        netloc = f\"{auth}@{netloc}\"\n    return urlunparse((scheme, netloc, path, \"\", query or \"\", fragment or \"\"))",
        ),
        "buggy_check": lambda c: "auth and auth not in netloc" not in c,
        "prompt_template": (
            "Fix the bug in `{source}`. The function `prepend_scheme_if_needed` drops "
            "authentication info (user:pass@) from URLs. The file is:\n\n"
            "```python\n{code}\n```\n\n"
            "The function should preserve auth components when reconstructing the URL. "
            "Return ONLY the corrected `{source}` file content inside ```python code block."
        ),
    },
}


def call_qwen(prompt: str, strategy_name: str, system_extra: str = "") -> tuple[str, float]:
    """Call local Qwen, return (response_text, elapsed_seconds)."""
    strategy = STRATEGIES.get(strategy_name, "")
    full = f"{system_extra}\n\n{strategy}\n\n{prompt}" if strategy else prompt

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a Python developer fixing a bug. Return only the corrected code file."},
            {"role": "user", "content": full},
        ],
        "max_tokens": 2048,
        "temperature": 0.3,
    }

    start = time.monotonic()
    resp = subprocess.run(
        [sys.executable, "-c", f"""
import json, urllib.request, sys
payload = {json.dumps(payload)}
req = urllib.request.Request(
    "{API_URL}",
    data=json.dumps(payload).encode(),
    headers={{"Content-Type": "application/json"}},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
        content = data["choices"][0]["message"]["content"]
        sys.stdout.write(content)
except Exception as e:
    sys.stderr.write(f"API ERROR: {{e}}\\n")
    sys.exit(1)
        """],
        capture_output=True, text=True, timeout=120,
    )
    elapsed = time.monotonic() - start

    if resp.returncode != 0:
        return (f"ERROR: {resp.stderr.strip()}", elapsed)
    return (resp.stdout.strip(), elapsed)


def extract_code(text: str) -> str:
    """Extract Python code from model response."""
    lines = text.split("\n")
    in_code = False
    code_lines = []
    for line in lines:
        s = line.strip()
        if s.startswith("```python"):
            in_code = True
            continue
        if s.startswith("```"):
            if in_code:
                break
            continue
        if in_code:
            code_lines.append(line)
    if code_lines:
        return "\n".join(code_lines)
    # Fallback: try to extract anything that looks like code
    for line in lines:
        if line.strip().startswith(("def ", "class ", "import ", "from ", "#")):
            in_code = True
        if in_code:
            code_lines.append(line)
    if code_lines:
        return "\n".join(code_lines)
    return text


def test_fix(code_str: str, test_file: str, fixture_path: Path, fixture_name: str) -> dict:
    """Apply fix code and run tests. Returns results."""
    with tempfile.TemporaryDirectory() as tmpdir:
        work = Path(tmpdir)
        source_file = fixture_path / FIXTURE_DEFS[fixture_name]["source_file"]
        test_path = fixture_path / test_file
        shutil.copy2(source_file, work / source_file.name)
        shutil.copy2(test_path, work / test_path.name)

        (work / source_file.name).write_text(code_str)

        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", test_file, "--tb=line"],
            cwd=work, capture_output=True, text=True, timeout=30,
        )

        passed = failed = 0
        for line in result.stdout.split("\n"):
            if "passed" in line:
                parts = [p.strip(",.") for p in line.split()]
                for i, p in enumerate(parts):
                    if p == "passed":
                        try:
                            passed = int(parts[i - 1])
                        except (ValueError, IndexError):
                            pass
                    if p == "failed":
                        try:
                            failed = int(parts[i - 1])
                        except (ValueError, IndexError):
                            pass

        return {
            "passed": passed,
            "failed": failed,
            "exit_code": result.returncode,
            "success": result.returncode == 0,
            "stdout_tail": result.stdout[-200:],
        }


def run_fixture(fixture_name: str, fixture_path: Path, mode: str = "single") -> dict:
    """Run single-call or multi-agent on a fixture."""
    source_file = FIXTURE_DEFS[fixture_name]["source_file"]
    test_file = FIXTURE_DEFS[fixture_name]["test_file"]
    prompt_tmpl = FIXTURE_DEFS[fixture_name]["prompt_template"]

    source_code = (fixture_path / source_file).read_text()

    if mode == "single":
        prompt = prompt_tmpl.format(source=source_file, code=source_code)
        response, api_time = call_qwen(prompt, "robust")
        code = extract_code(response)
        result = test_fix(code, test_file, fixture_path, fixture_name)
        return {
            "mode": "single",
            "api_time_sec": round(api_time, 1),
            "response_preview": response[:150],
            **result,
        }
    elif mode == "multi":
        candidates = []
        api_times = []
        total_start = time.monotonic()

        for name in ["minimal", "robust", "tdd", "root-cause", "adversarial", "architecture"]:
            prompt = prompt_tmpl.format(source=source_file, code=source_code)
            response, api_time = call_qwen(prompt, name)
            api_times.append(api_time)
            code = extract_code(response)
            result = test_fix(code, test_file, fixture_path, fixture_name)
            candidates.append({"strategy": name, "api_time_sec": round(api_time, 1), **result})

        total_time = time.monotonic() - total_start
        successes = [c for c in candidates if c["success"]]
        best = max(candidates, key=lambda c: (c["passed"], -c["failed"]))

        return {
            "mode": "multi",
            "total_time_sec": round(total_time, 1),
            "avg_api_time_sec": round(sum(api_times) / len(api_times), 1),
            "total_api_time_sec": round(sum(api_times), 1),
            "num_successful": len(successes),
            "overall_success": any(c["success"] for c in candidates),
            "best_candidate": best["strategy"],
            "best_passed": best["passed"],
            "best_failed": best["failed"],
            "candidates": candidates,
        }


def main():
    print("=" * 74)
    print("  HYDRACODE BENCHMARK V2: Single-Call vs Multi-Agent")
    print(f"  Model: Qwen3.6-27B (vLLM @ {API_URL})")
    print("=" * 74)

    # Verify model
    try:
        resp = subprocess.run(
            [sys.executable, "-c", f"""
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/v1/models", timeout=5) as r:
    data = json.loads(r.read())
    for m in data["data"]: print(m["id"])
            """],
            capture_output=True, text=True, timeout=10,
        )
        if not resp.stdout.strip():
            print("ERROR: Qwen server not running on port 8000"); sys.exit(1)
        print(f"  ✓ Server: {resp.stdout.strip()}\n")
    except Exception as e:
        print(f"ERROR: Cannot reach Qwen: {e}"); sys.exit(1)

    all_results = {}

    fixture_paths = {
        "pagination": FIXTURES_DIR / "pagination",
        "requests_6028": FIXTURES_DIR / "requests_6028_buggy",
    }
    for fixture_name, path_entry in fixture_paths.items():
        print(f"\n{'=' * 74}")
        print(f"  FIXTURE: {fixture_name}")
        print(f"  Path: {path_entry}")
        print(f"{'=' * 74}")

        # Phase 1: Single-call
        print(f"\n  ── Phase 1: Single-Call ──")
        single = run_fixture(fixture_name, path_entry, "single")
        print(f"     Time: {single['api_time_sec']}s  |  Tests: {single['passed']}/{single['passed']+single['failed']}  |  {'PASS' if single['success'] else 'FAIL'}")

        # Phase 2: Multi-agent
        print(f"  ── Phase 2: Multi-Agent (6 strategies) ──")
        multi = run_fixture(fixture_name, path_entry, "multi")
        for c in multi["candidates"]:
            mark = "✓" if c["success"] else "✗"
            print(f"     [{mark}] {c['strategy']:<12} {c['api_time_sec']:>5.1f}s  {c['passed']}/{c['passed']+c['failed']}")
        print(f"     ─────────────────────────────────────")
        print(f"     Best: {multi['best_candidate']}  |  Total: {multi['total_time_sec']}s  |  Oracle: {multi['num_successful']}/6  |  Overall: {'PASS' if multi['overall_success'] else 'FAIL'}")

        all_results[fixture_name] = {"single": single, "multi": multi}

    # Summary table
    print(f"\n{'=' * 74}")
    print("  FINAL COMPARISON")
    print(f"{'=' * 74}")
    print(f"  {'Fixture':<20} {'Mode':<12} {'Result':<8} {'Time':<8} {'Passed':<8}")
    print(f"  {'─'*20} {'─'*12} {'─'*8} {'─'*8} {'─'*8}")
    for fname, res in all_results.items():
        s = res["single"]
        m = res["multi"]
        print(f"  {fname:<20} {'Single':<12} {'PASS' if s['success'] else 'FAIL':<8} {s['api_time_sec']:<8.1f}s {s['passed']}/{s['passed']+s['failed']}")
        print(f"  {fname:<20} {'Multi':<12} {'PASS' if m['overall_success'] else 'FAIL':<8} {m['total_time_sec']:<8.1f}s {m['best_passed']}/{m['best_passed']+m['best_failed']}")
        print(f"  {fname:<20} {'Oracle@6':<12} {'─':<8} {'─':<8} {m['num_successful']}/6")
        print()

    # Save
    out_dir = Path("experiments/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    (out_dir / f"comparison_v2_{ts}.json").write_text(
        json.dumps(all_results, indent=2, default=str)
    )
    print(f"  Results: experiments/results/comparison_v2_{ts}.json")


if __name__ == "__main__":
    main()

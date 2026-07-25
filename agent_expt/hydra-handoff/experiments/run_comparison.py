#!/usr/bin/env python3
"""Single-call vs multi-agent comparison on pagination fixture.

Runs both modes against the local Qwen vLLM server on port 8000
and reports wall time, pass rate, and solution quality.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

API_URL = "http://localhost:8000/v1/chat/completions"
MODEL = "qwen"
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures/pagination"

STRATEGIES = {
    "minimal": (
        "You are a MINIMALIST developer. Fix the bug with the smallest possible change (≤3 lines). "
        "Make no other modifications."
    ),
    "robust": (
        "You are a ROBUST developer. Fix the bug completely with full type annotations and "
        "handle ALL edge cases including empty lists, negative values, and boundary conditions."
    ),
    "tdd": (
        "You are a TDD developer. First understand what the correct behavior should be by reading the "
        "tests, then write the minimum fix to make them pass."
    ),
    "root-cause": (
        "You are a ROOT-CAUSE analyst. Trace through the data flow carefully, identify the exact "
        "mathematical error and why it occurs, then fix it at the source."
    ),
    "adversarial": (
        "You are an ADVERSARIAL tester. Try to find hidden bugs beyond the obvious one. "
        "Check edge cases: empty input, single item, exact multiples, boundary conditions."
    ),
    "architecture": (
        "You are an ARCHITECTURE-FOCUSED developer. Consider the public API, module boundaries, "
        "and whether the fix has cross-module implications beyond the single function."
    ),
}


def call_qwen(prompt: str, strategy: str = "") -> str:
    """Call local Qwen and return the response text."""
    system_msg = STRATEGIES.get(strategy, "You are a helpful coding assistant.")

    full_prompt = (
        f"{system_msg}\n\n"
        f"## Task\n\n"
        f"Fix the bug in `paginator.py`. The file content is:\n\n"
        f"```python\n{prompt}\n```\n\n"
        f"The test file checks correct pagination behavior.\n\n"
        f"Return ONLY the corrected `paginator.py` file content inside a python code block. "
        f"Do not include any explanation before or after the code."
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a Python developer fixing a bug. Return only the corrected code file."},
            {"role": "user", "content": full_prompt},
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
    headers={{ "Content-Type": "application/json" }},
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
        if line.strip().startswith("```python"):
            in_code = True
            continue
        if line.strip().startswith("```"):
            if in_code:
                break
            continue
        if in_code:
            code_lines.append(line)
    if code_lines:
        return "\n".join(code_lines)

    for line in lines:
        if line.strip().startswith("def ") or line.strip().startswith("class "):
            in_code = True
        if in_code:
            code_lines.append(line)
    if code_lines:
        return "\n".join(code_lines)

    return text


def test_fix(code_str: str, fixture_path: Path) -> dict:
    """Apply a fix and run the test suite. Returns results."""
    with tempfile.TemporaryDirectory() as tmpdir:
        work = Path(tmpdir)
        for fname in ["paginator.py", "test_pagination.py"]:
            shutil.copy2(fixture_path / fname, work / fname)

        (work / "paginator.py").write_text(code_str)

        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "test_pagination.py", "--tb=line"],
            cwd=work, capture_output=True, text=True, timeout=30,
        )

        passed = failed = 0
        for line in result.stdout.split("\n"):
            if "passed" in line:
                parts = [p.strip(",.") for p in line.split()]
                for i, p in enumerate(parts):
                    if p == "passed":
                        try: passed = int(parts[i - 1])
                        except: pass
                    if p == "failed":
                        try: failed = int(parts[i - 1])
                        except: pass

        # Check for the exact fix
        correct_fix = "start = (page - 1) * per_page"
        has_correct_fix = correct_fix in code_str

        return {
            "passed": passed,
            "failed": failed,
            "exit_code": result.returncode,
            "has_correct_fix": has_correct_fix,
            "success": result.returncode == 0,
            "stdout": result.stdout[-300:],
        }


def run_single_baseline(fixture_path: Path) -> dict:
    """Single-call: one prompt, one fix attempt."""
    source_text = (fixture_path / "paginator.py").read_text()

    start = time.monotonic()
    response, api_time = call_qwen(source_text, "robust")
    total_time = time.monotonic() - start

    code = extract_code(response)
    result = test_fix(code, fixture_path)

    return {
        "mode": "single-call",
        "api_time_sec": round(api_time, 1),
        "total_time_sec": round(total_time, 1),
        "response_preview": response[:200],
        "code_preview": code[:200],
        **result,
    }


def run_multi_agent(fixture_path: Path) -> dict:
    """Multi-agent: 6 strategy prompts, pick best."""
    source_text = (fixture_path / "paginator.py").read_text()

    candidates = []
    api_times = []
    total_start = time.monotonic()

    for name in ["minimal", "robust", "tdd", "root-cause", "adversarial", "architecture"]:
        response, api_time = call_qwen(source_text, name)
        api_times.append(api_time)
        code = extract_code(response)
        result = test_fix(code, fixture_path)
        candidates.append({
            "strategy": name,
            "api_time_sec": round(api_time, 1),
            "response_preview": response[:150],
            **result,
        })

    total_time = time.monotonic() - total_start

    successes = [c for c in candidates if c["success"]]
    best = max(candidates, key=lambda c: (c["passed"], -c["failed"], c["has_correct_fix"]))

    return {
        "mode": "multi-agent",
        "total_time_sec": round(total_time, 1),
        "avg_api_time_sec": round(sum(api_times) / len(api_times), 1),
        "total_api_time_sec": round(sum(api_times), 1),
        "num_successful": len(successes),
        "num_candidates": len(candidates),
        "best_candidate": best["strategy"],
        "overall_success": any(c["success"] for c in candidates),
        "overall_has_correct_fix": any(c["has_correct_fix"] for c in candidates),
        "candidates": candidates,
    }


def main():
    print("=" * 70)
    print("HYDRACODE BENCHMARK: Single-Call vs Multi-Agent")
    print(f"Model: Qwen3.6-27B (vLLM @ {API_URL})")
    print(f"Fixture: {FIXTURE_DIR}")
    print("=" * 70)

    # --- Verify model is running ---
    try:
        resp = subprocess.run(
            [sys.executable, "-c", f"""
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/v1/models", timeout=5) as r:
    data = json.loads(r.read())
    for m in data["data"]:
        print(m["id"])
            """],
            capture_output=True, text=True, timeout=10,
        )
        if resp.returncode != 0 or not resp.stdout.strip():
            print("ERROR: Local Qwen server not running on port 8000")
            print(f"  {resp.stderr}")
            sys.exit(1)
        print(f"✓ Qwen server ready (model: {resp.stdout.strip()})\n")
    except Exception as e:
        print(f"ERROR: Cannot reach local Qwen server: {e}")
        print("Start it with: vllm serve qwen --port 8000")
        sys.exit(1)

    # --- Verify fixture has failing tests ---
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "test_pagination.py", "--tb=line"],
        cwd=FIXTURE_DIR, capture_output=True, text=True, timeout=10,
    )
    print(f"Fixture baseline: {result.stdout.strip()}")
    if result.returncode == 0:
        print("WARNING: Fixture tests already pass! Bug may be fixed.")
    else:
        print("✓ Fixture has failing tests (bug is present)\n")

    # --- Phase 1: Single-call baseline ---
    print("\n" + "-" * 70)
    print("PHASE 1: Single-Call Baseline")
    print("-" * 70)

    single = run_single_baseline(FIXTURE_DIR)

    print(f"  API time: {single['api_time_sec']}s")
    print(f"  Tests: {single['passed']} passed, {single['failed']} failed")
    print(f"  Correct fix: {'YES' if single['has_correct_fix'] else 'NO'}")
    print(f"  Overall: {'PASS' if single['success'] else 'FAIL'}")

    # --- Phase 2: Multi-agent pipeline ---
    print("\n" + "-" * 70)
    print("PHASE 2: Multi-Agent Pipeline (6 strategies)")
    print("-" * 70)

    multi = run_multi_agent(FIXTURE_DIR)

    for c in multi["candidates"]:
        status = "✓" if c["success"] else "✗"
        fix = "+" if c["has_correct_fix"] else "-"
        print(f"  [{status}] {c['strategy']:<12} {c['api_time_sec']:>5.1f}s  {c['passed']}/{c['passed']+c['failed']} pass  fix={fix}")

    print(f"\n  Best candidate: {multi['best_candidate']}")
    print(f"  Total time: {multi['total_time_sec']}s")
    print(f"  Overall: {'PASS' if multi['overall_success'] else 'FAIL'}")
    if multi['overall_has_correct_fix']:
        print("  Correct fix found by at least one agent")

    # --- Comparison ---
    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)

    s = single
    m = multi
    best_c = next((c for c in m["candidates"] if c["strategy"] == m["best_candidate"]), m["candidates"][0])

    print(f"\n  {'Metric':<35} {'Single':<12} {'Multi-Agent':<12}")
    print(f"  {'-'*35} {'-'*12} {'-'*12}")
    print(f"  {'Tests passed':<35} {s['passed']:<12} {best_c['passed']:<12}")
    print(f"  {'Tests failed':<35} {s['failed']:<12} {best_c['failed']:<12}")
    pass_range = f"{min(c['passed'] for c in m['candidates'])}→{max(c['passed'] for c in m['candidates'])}"
    print(f"  {'Worst→Best pass range':<35} {'—':<12} {pass_range:<12}")
    print(f"  {'Correct fix found':<35} {s['has_correct_fix']!s:<12} {m['overall_has_correct_fix']!s:<12}")
    print(f"  {'Overall solved':<35} {s['success']!s:<12} {m['overall_success']!s:<12}")
    print(f"  {'API time (total)':<35} {s['api_time_sec']:<12.1f}s {m['total_api_time_sec']:<12.1f}s")
    print(f"  {'Wall time (total)':<35} {s['total_time_sec']:<12.1f}s {m['total_time_sec']:<12.1f}s")

    oracle = f"{m['num_successful']}/{m['num_candidates']}"
    print(f"\n  {'Oracle pass@6':<35} {'—':<12} {oracle:<12}")

    # Save results
    results = {"single": single, "multi": multi}
    out_dir = Path("experiments/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    (out_dir / f"comparison_{ts}.json").write_text(json.dumps(results, indent=2))
    print(f"\n  Results saved to: experiments/results/comparison_{ts}.json")

    # Final verdict
    print("\n" + "=" * 70)
    if m["overall_success"] and not s["success"]:
        print("VERDICT: Multi-agent pipeline solved the task; single-call failed.")
    elif s["success"] and not m["overall_success"]:
        print("VERDICT: Single-call succeeded; multi-agent did not.")
    elif s["success"] and m["overall_success"]:
        print(f"VERDICT: Both succeeded. Multi-agent oracle pass@6 = {m['num_successful']}/{m['num_candidates']}.")
    else:
        print("VERDICT: Neither approach solved the task.")
    print("=" * 70)


if __name__ == "__main__":
    main()

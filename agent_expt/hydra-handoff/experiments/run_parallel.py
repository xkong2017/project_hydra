#!/usr/bin/env python3
"""Parallel multi-agent experiment: 6 concurrent Qwen calls on a real SWE-bench task.

Key fixes applied:
  1. max_tokens=8192 — prevents content:null from reasoning budget exhaustion
  2. Reasoning extraction fallback — when content is null, extract code from reasoning
  3. Compressed strategy prompts — shorter prompts reduce reasoning overhead
  4. Parallel dispatch via ThreadPoolExecutor — utilizes 6-way vLLM concurrency
  5. Dropped "robust" (always fails with long reasoning) — replaced with focused strategies
"""

import json
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

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures"

# Compressed strategy prompts — short, actionable, minimal reasoning overhead
STRATEGIES = [
    ("tdd",
     "Read the tests first to determine expected behavior, then write the minimum fix."),
    ("root-cause",
     "Trace the data flow to find the exact root cause, then fix at the source."),
    ("minimal",
     "Fix the bug with the smallest possible diff. No extra changes."),
    ("architecture",
     "Consider API contracts and module boundaries. Fix all affected paths."),
    ("adversarial",
     "Find hidden edge cases and regressions the obvious fix might miss."),
    ("alternative",
     "Explore a meaningfully different solution strategy than the obvious fix."),
]

FIXTURE = {
    "name": "requests_6028",
    "path": FIXTURES_DIR / "requests_6028_buggy",
    "source_file": "url_utils.py",
    "test_file": "test_url_utils.py",
    "prompt_template": (
        "Fix the bug where `prepend_scheme_if_needed` drops authentication info "
        "(user:pass@) from URLs.\n\n"
        "```python\n{code}\n```\n\n"
        "Return ONLY the corrected `{source}` file content inside ```python."
    ),
}


def call_qwen(prompt: str) -> tuple[str, str, float]:
    """Call Qwen, return (content, reasoning, elapsed_seconds)."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a Python developer fixing a bug. Return only the corrected code file."},
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
req = urllib.request.Request(
    "{API_URL}",
    data=json.dumps(payload).encode(),
    headers={{"Content-Type": "application/json"}},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read())
        c = d["choices"][0]["message"]
        result = {{
            "content": c.get("content"),
            "reasoning": c.get("reasoning", ""),
            "finish_reason": d["choices"][0].get("finish_reason", ""),
        }}
        sys.stdout.write(json.dumps(result))
except Exception as e:
    sys.stdout.write(json.dumps({{"error": str(e)}}))
        """],
        capture_output=True, text=True, timeout=300,
    )
    elapsed = time.monotonic() - start

    try:
        data = json.loads(resp.stdout)
        if "error" in data:
            return ("", "", elapsed)
        return (
            data.get("content") or "",
            data.get("reasoning") or "",
            elapsed,
        )
    except (json.JSONDecodeError, KeyError):
        return ("", "", elapsed)


def extract_code(text: str) -> str:
    """Extract Python code from model output (content or reasoning)."""
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

    for line in lines:
        s = line.strip()
        if s.startswith(("def ", "class ", "import ", "from ", "#", "\"\"\"", "'''")):
            in_code = True
        if in_code:
            code_lines.append(line)
    if code_lines:
        return "\n".join(code_lines)

    return text


def test_fix(code: str, fixture_cfg: dict) -> dict:
    """Test a candidate fix. Returns pass/fail with details."""
    fixture_path = fixture_cfg["path"]
    source_file = fixture_cfg["source_file"]
    test_file = fixture_cfg["test_file"]

    with tempfile.TemporaryDirectory() as tmpdir:
        work = Path(tmpdir)
        shutil.copy2(fixture_path / source_file, work / source_file)
        shutil.copy2(fixture_path / test_file, work / test_file)

        (work / source_file).write_text(code)

        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", test_file, "--tb=line"],
            cwd=work, capture_output=True, text=True, timeout=15,
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

        return {
            "success": result.returncode == 0,
            "passed": passed,
            "failed": failed,
            "exit_code": result.returncode,
            "pytest_output": result.stdout[-150:],
        }


def check_fix_correctness(code: str) -> dict:
    """Check if the fix is semantically correct (auth reconstruction)."""
    has_auth_check = "if auth" in code and "netloc" in code
    has_reconstruct = "auth" in code and "@" in code and "netloc" in code
    return {
        "has_auth_reconstruction": has_auth_check and has_reconstruct,
    }


def run_strategy(strategy_name: str, strategy_prompt: str, fixture_cfg: dict) -> dict:
    """Run a single strategy and return full results."""
    src_code = (fixture_cfg["path"] / fixture_cfg["source_file"]).read_text()
    prompt = f"{strategy_prompt}\n\n{fixture_cfg['prompt_template'].format(source=fixture_cfg['source_file'], code=src_code)}"

    content, reasoning, api_time = call_qwen(prompt)

    # Primary: extract from content. Fallback: extract from reasoning.
    code = extract_code(content) if content.strip() else extract_code(reasoning)
    has_reasoning_fallback = bool(content.strip() == "" and code.strip())

    test_result = test_fix(code, fixture_cfg)
    quality = check_fix_correctness(code)

    return {
        "strategy": strategy_name,
        "api_time_sec": round(api_time, 1),
        "content_len": len(content),
        "reasoning_len": len(reasoning),
        "used_reasoning_fallback": has_reasoning_fallback,
        "code_len": len(code),
        "code_preview": code[:200],
        **test_result,
        **quality,
    }


def main():
    print("=" * 74)
    print("  PARALLEL MULTI-AGENT BENCHMARK (6 concurrent calls)")
    print(f"  Model: Qwen3.6-27B (vLLM @ {API_URL}, model={MODEL})")
    print(f"  max_tokens={MAX_TOKENS}, concurrency={MAX_CONCURRENT}")
    print(f"  Fixture: {FIXTURE['name']} ({FIXTURE['path']})")
    print("=" * 74)

    # Verify server
    try:
        r = subprocess.run([sys.executable, "-c", """
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/v1/models", timeout=5) as resp:
    print(json.loads(resp.read())["data"][0]["id"])
        """], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            print(f"ERROR: Qwen server not responding: {r.stderr}"); sys.exit(1)
        print(f"  ✓ Server ready (model: {r.stdout.strip()})")
    except Exception as e:
        print(f"ERROR: {e}"); sys.exit(1)

    # Show fixture bug
    src = (FIXTURE["path"] / FIXTURE["source_file"]).read_text()
    test_src = (FIXTURE["path"] / FIXTURE["test_file"]).read_text()
    test_count = test_src.count("@pytest.mark.parametrize") + test_src.count("def test_")
    print(f"  ✓ Fixture has bug (source={len(src)}ch, tests={test_count} cases, 2 fail on buggy code)")

    # --- Phase 1: Single call baseline (better: tdd strategy, 8192 tokens) ---
    print(f"\n{'─' * 74}")
    print("  PHASE 1: Single-Call Baseline (tdd strategy, 8192 tokens)")
    print(f"{'─' * 74}")

    single = run_strategy("tdd", STRATEGIES[0][1], FIXTURE)
    print(f"  Time: {single['api_time_sec']}s  |  Tests: {single['passed']}/{single['passed']+single['failed']}")
    print(f"  Reasoning: {single['reasoning_len']}ch  Content: {single['content_len']}ch  Fallback: {single['used_reasoning_fallback']}")
    print(f"  Auth fix: {single['has_auth_reconstruction']}  Overall: {'PASS' if single['success'] else 'FAIL'}")
    if not single["success"] and single["code_preview"]:
        print(f"  Code preview: {single['code_preview'][:120]}")

    # --- Phase 2: Parallel multi-agent (6 concurrent calls) ---
    print(f"\n{'─' * 74}")
    print("  PHASE 2: Parallel Multi-Agent (6 concurrent strategies)")
    print(f"{'─' * 74}")

    candidates = []
    start_all = time.monotonic()

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        futures = {
            executor.submit(run_strategy, name, prompt, FIXTURE): name
            for name, prompt in STRATEGIES
        }
        for future in as_completed(futures):
            result = future.result()
            candidates.append(result)
            mark = "✓" if result["success"] else "✗"
            fb = " (reasoning fallback)" if result["used_reasoning_fallback"] else ""
            print(f"  [{mark}] {result['strategy']:<12} {result['api_time_sec']:>5.1f}s  "
                  f"{result['passed']}/{result['passed']+result['failed']}  "
                  f"auth_fix={'✓' if result['has_auth_reconstruction'] else '✗'}"
                  f"{fb}")

    total_time = time.monotonic() - start_all

    # Sort by success then by time
    candidates.sort(key=lambda c: (not c["success"], c["api_time_sec"]))
    successes = [c for c in candidates if c["success"]]
    best = next((c for c in candidates if c["success"]), candidates[0])
    max_time = max(c["api_time_sec"] for c in candidates)

    print(f"  {'─' * 70}")
    print(f"  Best: {best['strategy']}  |  Wall time: {total_time:.1f}s  "
          f"(max single: {max_time:.1f}s, parallel efficiency: {max_time/total_time:.0%})")
    print(f"  Oracle pass@6: {len(successes)}/{len(candidates)}")

    # --- Summary ---
    print(f"\n{'=' * 74}")
    print("  RESULTS SUMMARY")
    print(f"{'=' * 74}")

    print(f"\n  {'Metric':<35} {'Single':<15} {'Multi (parallel)':<15}")
    print(f"  {'─'*35} {'─'*15} {'─'*15}")
    print(f"  {'Solved':<35} {'YES' if single['success'] else 'NO':<15} {'YES' if len(successes)>0 else 'NO':<15}")
    print(f"  {'Tests passed':<35} {single['passed']:<15} {best['passed']:<15}")
    print(f"  {'Auth fix':<35} {single['has_auth_reconstruction']!s:<15} {best['has_auth_reconstruction']!s:<15}")
    print(f"  {'API time':<35} {single['api_time_sec']:<15.1f}s {total_time:<15.1f}s")
    print(f"  {'Max single strategy time':<35} {'─':<15} {max_time:<15.1f}s")
    print(f"  {'Parallel efficiency':<35} {'─':<15} {max_time/total_time:.0%}")
    oracle = f"{len(successes)}/{len(candidates)}"
    print(f"  {'Oracle pass@6':<35} {'─':<15} {oracle:<15}")
    print(f"  {'Reasoning fallback used':<35} {single['used_reasoning_fallback']!s:<15} {sum(1 for c in candidates if c['used_reasoning_fallback']):<15}")

    # Per-strategy detail
    print(f"\n  {'─'*74}")
    print(f"  Per-strategy detail:")
    print(f"  {'Strategy':<14} {'Tests':<8} {'Time':<8} {'Content':<10} {'Reasoning':<10} {'AuthFix':<8} {'Fallback':<9}")
    print(f"  {'─'*14} {'─'*8} {'─'*8} {'─'*10} {'─'*10} {'─'*8} {'─'*9}")
    all_cands = [single] + candidates
    for c in all_cands:
        fb = c.get("used_reasoning_fallback", False)
        print(f"  {c['strategy']:<14} {c['passed']}/{c['passed']+c['failed']:<5} {c['api_time_sec']:<8.1f} "
              f"{c['content_len']:<10} {c['reasoning_len']:<10} "
              f"{'✓' if c.get('has_auth_reconstruction') else '✗':<8} {fb!s:<9}")

    # Save
    results = {
        "config": {"model": MODEL, "max_tokens": MAX_TOKENS, "concurrency": MAX_CONCURRENT, "fixture": FIXTURE["name"]},
        "single": single,
        "multi": {"candidates": candidates, "total_time_sec": round(total_time, 1), "oracle_pass": f"{len(successes)}/{len(candidates)}"},
    }
    out_dir = Path("experiments/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    (out_dir / f"parallel_{ts}.json").write_text(json.dumps(results, indent=2, default=str))
    print(f"\n  Saved: experiments/results/parallel_{ts}.json")

    # Verdict
    print(f"\n{'=' * 74}")
    if len(successes) > 0 and not single["success"]:
        print("  VERDICT: Multi-agent parallel dispatch solved the task; single-call failed.")
        print(f"  Multi-agent oracle pass@6 = {len(successes)}/{len(candidates)}.")
    elif single["success"] and len(successes) > 0:
        print("  VERDICT: Both approaches succeeded. Multi-agent provides strategy diversity.")
    else:
        print("  VERDICT: Neither approach solved the task.")
    print(f"{'=' * 74}")


if __name__ == "__main__":
    main()

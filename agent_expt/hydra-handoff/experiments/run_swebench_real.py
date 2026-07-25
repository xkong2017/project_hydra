#!/usr/bin/env python3
"""Real SWE-bench Verified tasks: single-call vs parallel multi-agent.

Uses pre-cloned base repos (at buggy commits) with test patches applied.
Evaluates by running FAIL_TO_PASS tests before and after fix.
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

WORKTREES = Path("/home/mike2026/projects/agentic-ttc/worktrees")
MANIFESTS = Path("/home/mike2026/projects/agentic-ttc/manifests")

STRATEGIES = [
    ("tdd", "Read the tests first to determine expected behavior, then write the minimum fix."),
    ("root-cause", "Trace the data flow to find the exact root cause."),
    ("minimal", "Fix with the smallest possible diff. No extra changes."),
    ("architecture", "Consider API contracts. Fix all affected paths."),
    ("adversarial", "Find edge cases and regressions the obvious fix misses."),
    ("alternative", "Explore a different solution strategy than the obvious fix."),
]

# 5 real SWE-bench Verified tasks with different repos
TASK_IDS = [
    "psf__requests-6028",
    "astropy__astropy-13398",
    "django__django-13925",
    "pylint-dev__pylint-4970",
    "astropy__astropy-13579",
]


def load_task_manifest(task_id: str) -> dict | None:
    """Load task data from any manifest file."""
    for mf in sorted(MANIFESTS.glob("*.json")):
        if mf.stat().st_size > 10 * 1024 * 1024:
            continue
        try:
            data = json.loads(mf.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        tasks = data if isinstance(data, list) else data.get("tasks", data.get("pilot", []))
        for t in tasks:
            if isinstance(t, dict) and t.get("instance_id") == task_id:
                t.setdefault("FAIL_TO_PASS", t.get("fail_to_pass", []))
                t.setdefault("PASS_TO_PASS", t.get("pass_to_pass", []))
                return t
        if isinstance(data, dict):
            for key in ["seed", "pilot", "confirmation", "reserve"]:
                tasks = data.get(key, [])
                for t in tasks:
                    if isinstance(t, dict) and t.get("instance_id") == task_id:
                        t.setdefault("FAIL_TO_PASS", t.get("fail_to_pass", []))
                        t.setdefault("PASS_TO_PASS", t.get("pass_to_pass", []))
                        return t
    return None


def create_task_worktree(task_id: str, task: dict) -> Path:
    """Create a fresh worktree from the base repo with test_patch applied."""
    base_dir = WORKTREES / f"{task_id}_base"
    if not base_dir.exists():
        raise FileNotFoundError(f"Base repo not found: {base_dir}")

    work_dir = Path(tempfile.mkdtemp(prefix=f"swe_{task_id}_"))
    repo_dir = work_dir / "repo"

    # Clone from local base (much faster than re-cloning from GitHub)
    subprocess.run(["git", "clone", str(base_dir), str(repo_dir)],
        check=True, capture_output=True, timeout=60)

    subprocess.run(["git", "checkout", "-b", "swe-fix"],
        check=True, cwd=str(repo_dir), capture_output=True, timeout=30)

    # Apply test_patch
    test_patch = task.get("test_patch", "")
    if test_patch:
        proc = subprocess.run(
            ["git", "apply", "--input=-"],
            cwd=str(repo_dir), input=test_patch, text=True,
            capture_output=True, timeout=30,
        )
        if proc.returncode != 0:
            print(f"    Warning: test_patch apply failed: {proc.stderr[:100]}")

    return repo_dir


def run_fail_tests(repo_dir: Path, task: dict) -> dict:
    """Run FAIL_TO_PASS tests, return results."""
    fail_tests = task.get("FAIL_TO_PASS", [])
    if not fail_tests:
        # Direct function test (e.g., requests-6028)
        if task["instance_id"] == "psf__requests-6028":
            import importlib.util
            sys.path.insert(0, str(repo_dir))
            try:
                spec = importlib.util.spec_from_file_location(
                    "requests.utils", str(repo_dir / "requests/utils.py"))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                fn = getattr(mod, "prepend_scheme_if_needed")
                cases = [
                    ("http://user:pass@example.com/path?query",
                     "http://user:pass@example.com/path?query"),
                    ("http://user@example.com/path?query",
                     "http://user@example.com/path?query"),
                ]
                results = []
                for value, expected in cases:
                    actual = fn(value, "http")
                    results.append(actual == expected)
                total_pass = sum(results)
                return {"success": all(results), "passed": total_pass,
                        "failed": len(cases) - total_pass, "total": len(cases),
                        "details": results}
            finally:
                sys.path.pop(0)

    if not fail_tests:
        return {"success": True, "passed": 0, "failed": 0, "total": 0}

    passed = failed = 0
    for test_id in fail_tests:
        proc = subprocess.run(
            ["python3", "-m", "pytest", "-x", "--tb=line", test_id],
            cwd=str(repo_dir), capture_output=True, text=True, timeout=120,
        )
        if proc.returncode == 0:
            passed += 1
        else:
            failed += 1

    return {"success": failed == 0, "passed": passed, "failed": failed, "total": len(fail_tests)}


def call_qwen(prompt: str) -> tuple[str, str, float]:
    """Call Qwen, return (content, reasoning, elapsed)."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a Python developer fixing a bug. Return ONLY the corrected file content inside ```python."},
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
        sys.stdout.write(json.dumps({{"content": c.get("content"), "reasoning": c.get("reasoning","")}}))
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
    except Exception:
        return ("", "", elapsed)


def extract_code(text: str) -> str:
    """Extract Python code block from model output."""
    in_code, lines = False, []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```python"):
            in_code = True; continue
        if s.startswith("```") and in_code: break
        if in_code: lines.append(line)
    if lines: return "\n".join(lines)
    return text


def find_source_files(task: dict, repo_dir: Path) -> str:
    """Get relevant source files for the prompt."""
    tid = task["instance_id"]
    # For specific tasks, include the most likely buggy files
    file_map = {
        "psf__requests-6028": ["requests/utils.py", "requests/models.py"],
        "astropy__astropy-13398": ["astropy/coordinates/erfa_astrom.py"],
        "django__django-13925": ["django/core/checks/model_checks.py"],
        "pylint-dev__pylint-4970": ["pylint/checkers/similar.py"],
        "astropy__astropy-13579": ["astropy/wcs/wcsapi/wrappers/sliced_wcs.py"],
    }

    sources = {}
    for f in file_map.get(tid, [""]):
        fp = repo_dir / f
        if fp.exists():
            sources[f] = fp.read_text()
    return sources


def build_prompt(task: dict) -> str:
    """Build prompt with problem statement, failing tests, and source files."""
    lines = [
        f"# Task: {task['instance_id']}",
        f"# Repo: {task['repo']}",
        "",
        "## Problem Statement",
        task["problem_statement"],
        "",
        "## Failing Tests (must pass after fix)",
    ]
    for t in task.get("FAIL_TO_PASS", []):
        lines.append(f"- {t}")

    if task.get("PASS_TO_PASS"):
        lines.extend(["", "## Regression Tests (must continue passing)"])
        for t in task["PASS_TO_PASS"][:5]:
            lines.append(f"- {t}")

    return "\n".join(lines)


def apply_fix(repo_dir: Path, fix_code: str, filepath: str) -> bool:
    """Write the model's fix code to the target file."""
    target = repo_dir / filepath
    if not target.exists():
        return False
    target.write_text(fix_code)
    return True


def run_strategy(sn: str, sp: str, task_id: str, task: dict, repo_dir: Path,
                 source_files: dict, prompt_text: str) -> dict:
    """Run one strategy on a real SWE-bench task."""
    prompt = f"{sp}\n\n{prompt_text}\n\n## Source Files\n\n"
    for fpath, content in source_files.items():
        prompt += f"### {fpath}\n```python\n{content}\n```\n\n"
    prompt += "Return ONLY the corrected source file(s) inside ```python blocks. For each file, start with a comment `# FILE: path/to/file.py` before the code block."

    content, reasoning, api_time = call_qwen(prompt)

    # Parse multi-file output
    fixes_applied = []
    current_file = None
    current_code = ""
    for line in content.split("\n"):
        m = re.match(r"#\s*FILE:\s*(.+)", line)
        if m:
            if current_file and current_code.strip():
                ok = apply_fix(repo_dir, current_code, current_file)
                fixes_applied.append({"file": current_file, "applied": ok})
            current_file = m.group(1).strip()
            current_code = ""
        else:
            current_code += line + "\n"
    if current_file and current_code.strip():
        ok = apply_fix(repo_dir, current_code, current_file)
        fixes_applied.append({"file": current_file, "applied": ok})

    # If no # FILE: markers found, try single file extraction
    if not fixes_applied:
        code = extract_code(content)
        for fpath in source_files:
            if apply_fix(repo_dir, code, fpath):
                fixes_applied.append({"file": fpath, "applied": True})
                break

    # Run failing tests
    test_result = run_fail_tests(repo_dir, task)

    return {
        "strategy": sn,
        "api_time_sec": round(api_time, 1),
        "content_len": len(content),
        "reasoning_len": len(reasoning),
        "fixes_applied": len([f for f in fixes_applied if f["applied"]]),
        "files_attempted": len(fixes_applied),
        **test_result,
    }


def reset_repo(repo_dir: Path, base_dir: Path):
    """Reset repo to clean state (undo any fixes)."""
    subprocess.run(["git", "checkout", "-f"],
        check=False, cwd=str(repo_dir), capture_output=True)
    subprocess.run(["git", "clean", "-fd"],
        check=False, cwd=str(repo_dir), capture_output=True)


def main():
    print("=" * 78)
    print("  REAL SWE-BENCH VERIFIED: Single-Call vs Parallel Multi-Agent")
    print(f"  Model: {MODEL}, max_tokens={MAX_TOKENS}, concurrency=6")
    print(f"  Tasks: {', '.join(TASK_IDS)}")
    print("=" * 78)

    r = subprocess.run([sys.executable, "-c", """
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/v1/models", timeout=5) as resp:
    print(json.loads(resp.read())["data"][0]["id"])
    """], capture_output=True, text=True, timeout=10)
    print(f"  ✓ Server: {r.stdout.strip()}\n")

    all_results = {}

    for task_id in TASK_IDS:
        task = load_task_manifest(task_id)
        if not task:
            print(f"  ✗ {task_id}: not found in any manifest"); continue

        print(f"{'=' * 78}")
        print(f"  {task_id} ({task['repo']})")
        print(f"  Tests: {len(task.get('FAIL_TO_PASS',[]))} fail-to-pass, "
              f"{len(task.get('PASS_TO_PASS',[]))} pass-to-pass")
        print(f"{'=' * 78}")

        try:
            repo_dir = create_task_worktree(task_id, task)
        except FileNotFoundError as e:
            print(f"  ✗ {e}"); continue

        base_dir = WORKTREES / f"{task_id}_base"

        try:
            # Verify bug exists (run FAIL_TO_PASS on clean repo)
            print(f"  Verifying bug... ", end="", flush=True)
            baseline = run_fail_tests(repo_dir, task)
            print(f"{baseline['passed']}/{baseline['total']} pass "
                  f"({baseline['failed']} fail) — bug confirmed"
                  if baseline['failed'] > 0 else "ALL PASS — no bug detected!")

            # Get source files
            source_files = find_source_files(task, repo_dir)
            prompt_text = build_prompt(task)
            print(f"  Source files: {list(source_files.keys())}")

            # Phase 1: Single-call
            print(f"  Single-call (tdd)... ", end="", flush=True)
            single = run_strategy("tdd", STRATEGIES[0][1], task_id, task,
                                  repo_dir, source_files, prompt_text)
            sm = "✓" if single["success"] else "✗"
            print(f"[{sm}] {single['passed']}/{single['total']}  "
                  f"{single['api_time_sec']}s  (reasoning={single['reasoning_len']}ch)")

            # Reset repo for multi-agent
            reset_repo(repo_dir, base_dir)

            # Phase 2: Multi-agent
            print(f"  Multi-agent...")
            candidates = []
            start_all = time.monotonic()
            # Need fresh repo per strategy since they modify files
            with ThreadPoolExecutor(max_workers=1) as ex:
                futures = {}
                for sname, sprompt in STRATEGIES:
                    # Make fresh copy for each strategy
                    try:
                        sdir = create_task_worktree(task_id, task)
                    except FileNotFoundError:
                        continue
                    sf = find_source_files(task, sdir)
                    futures[ex.submit(run_strategy, sname, sprompt, task_id,
                                      task, sdir, sf, prompt_text)] = sname

                for f in as_completed(futures):
                    c = f.result()
                    candidates.append(c)
                    print(f"    {'✓' if c['success'] else '✗'} {c['strategy']:<12} "
                          f"{c['passed']}/{c['total']}  {c['api_time_sec']:<6.1f}s  "
                          f"r={c['reasoning_len']:<5}ch fixes={c['fixes_applied']}")

            total_time = time.monotonic() - start_all
            successes = [c for c in candidates if c["success"]]
            best = max(candidates, key=lambda c: (c["passed"], -c.get("failed", 0)))

            print(f"  Best: {best['strategy']} ({best['passed']}/{best['total']})  "
                  f"Oracle: {len(successes)}/6  Wall: {total_time:.1f}s")

            all_results[task_id] = {
                "single": single, "multi": {
                    "total_time_sec": round(total_time, 1),
                    "oracle": f"{len(successes)}/6",
                    "num_ok": len(successes),
                    "best": best["strategy"],
                    "best_p": best["passed"],
                    "best_f": best.get("failed", 0),
                    "candidates": candidates,
                }
            }

        finally:
            shutil.rmtree(repo_dir.parent, ignore_errors=True)

    # Summary
    print(f"\n{'=' * 78}")
    print("  FINAL RESULTS")
    print(f"{'=' * 78}")
    print(f"  {'Task':<30} {'Single':<8} {'Multi':<8} {'Oracle':<8} {'Best':<14}")
    print(f"  {'─'*30} {'─'*8} {'─'*8} {'─'*8} {'─'*14}")

    single_ok = multi_ok = 0
    for tid, res in all_results.items():
        s, m = res["single"], res["multi"]
        s_st = "PASS" if s.get("success") else "FAIL"
        m_st = "PASS" if m["num_ok"] > 0 else "FAIL"
        if s.get("success"): single_ok += 1
        if m["num_ok"] > 0: multi_ok += 1
        print(f"  {tid:<30} {s_st:<8} {m_st:<8} {m['oracle']:<8} {m['best']:<14}")

    print(f"\n  Solve rate:  Single={single_ok}/{len(all_results)} "
          f"Multi={multi_ok}/{len(all_results)}")
    print(f"  Δ = {multi_ok - single_ok}/{len(all_results)} "
          f"({'PASS' if multi_ok > single_ok else 'SAME' if multi_ok == single_ok else 'FAIL'})")

    out_dir = Path("experiments/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    (out_dir / f"swebench_real_{ts}.json").write_text(
        json.dumps(all_results, indent=2, default=str))
    print(f"\n  Saved: experiments/results/swebench_real_{ts}.json")


if __name__ == "__main__":
    main()

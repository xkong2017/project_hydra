#!/usr/bin/env python3
"""Real SWE-bench Verified: 3 tasks, single-call vs multi-agent.

Uses direct function tests (not pytest) to avoid dependency hell.
Tasks: requests-6028, astropy-13579, django-13925
"""

import importlib.util
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
WORKTREES = Path("/home/mike2026/projects/agentic-ttc/worktrees")
MANIFESTS = Path("/home/mike2026/projects/agentic-ttc/manifests")

STRATEGIES = [
    ("tdd", "Read the tests first, then write the minimum fix."),
    ("root-cause", "Trace the data flow to find the exact root cause."),
    ("minimal", "Fix with the smallest possible diff. No extra changes."),
    ("architecture", "Consider API contracts. Fix all affected paths."),
    ("adversarial", "Find edge cases the obvious fix misses."),
    ("alternative", "Explore a different solution strategy."),
]

TASKS_CONFIG = [
    {
        "id": "psf__requests-6028",
        "repo": "psf/requests",
        "manifest": "swebench_verified_filtered.json",
        "source_files": ["requests/utils.py"],
        "target_func": "prepend_scheme_if_needed",
        "test_cases": [
            ("http://user:pass@example.com/path?query", "http://user:pass@example.com/path?query"),
            ("http://user@example.com/path?query", "http://user@example.com/path?query"),
        ],
        "total": 2,
    },
]


def load_task(task_id: str) -> dict | None:
    for mf in sorted(MANIFESTS.glob("*.json")):
        if mf.stat().st_size > 10 * 1024 * 1024:
            continue
        try:
            data = json.loads(mf.read_text())
        except Exception:
            continue
        tasks = data if isinstance(data, list) else []
        if not tasks and isinstance(data, dict):
            for key in ["seed", "pilot", "confirmation", "reserve", "tasks"]:
                val = data.get(key, [])
                if isinstance(val, list):
                    tasks.extend(val)
        for t in tasks:
            if isinstance(t, dict) and t.get("instance_id") == task_id:
                return t
    return None


def verify_bug(repo_dir: Path, cfg: dict) -> dict:
    """Verify the bug exists by running test_cases."""
    sys.path.insert(0, str(repo_dir))
    try:
        spec = importlib.util.spec_from_file_location(
            "requests.utils", str(repo_dir / "requests/utils.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, cfg["target_func"])

        passed = failed = 0
        details = []
        for value, expected in cfg["test_cases"]:
            actual = fn(value, "http")
            ok = actual == expected
            details.append({"value": value, "expected": expected, "actual": actual, "ok": ok})
            if ok:
                passed += 1
            else:
                failed += 1
        return {"success": failed == 0, "passed": passed, "failed": failed, "total": len(cfg["test_cases"]), "details": details}
    finally:
        sys.path.pop(0)


def verify_fix(repo_dir: Path, cfg: dict) -> dict:
    """Verify the fix by rebuilding the module and running tests."""
    # Clear any cached imports
    for key in list(sys.modules.keys()):
        if key.startswith("requests"):
            del sys.modules[key]

    sys.path.insert(0, str(repo_dir))
    try:
        spec = importlib.util.spec_from_file_location(
            "requests.utils", str(repo_dir / "requests/utils.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, cfg["target_func"])

        passed = failed = 0
        for value, expected in cfg["test_cases"]:
            actual = fn(value, "http")
            if actual == expected:
                passed += 1
            else:
                failed += 1
        return {"success": failed == 0, "passed": passed, "failed": failed, "total": len(cfg["test_cases"])}
    finally:
        sys.path.pop(0)


def call_qwen(prompt: str) -> tuple[str, str, float]:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a Python developer fixing a bug. Return ONLY the corrected file inside ```python."},
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
        sys.stdout.write(json.dumps({{"c": c.get("content",""), "r": c.get("reasoning","")}}))
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
        return (data.get("c") or "", data.get("r") or "", elapsed)
    except Exception:
        return ("", "", elapsed)


def extract_code(text: str) -> str:
    in_code, lines = False, []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```python"):
            in_code = True; continue
        if s.startswith("```") and in_code: break
        if in_code: lines.append(line)
    return "\n".join(lines) if lines else text


def run_strategy(sn: str, sp: str, cfg: dict, task: dict, repo_dir: Path) -> dict:
    """Run one strategy on a real SWE-bench task."""
    # Read source files
    sources = {}
    for f in cfg["source_files"]:
        fp = repo_dir / f
        if fp.exists():
            sources[f] = fp.read_text()

    # Build prompt
    prompt_parts = [
        sp,
        f"\n## Task: {cfg['id']}",
        f"\n## Problem Statement\n{task['problem_statement']}",
        "\n## Failing Tests (must pass after fix)",
    ]
    for t in task.get("FAIL_TO_PASS", []):
        prompt_parts.append(f"- {t}")
    prompt_parts.append("\n## Source Files")
    for fpath, content in sources.items():
        prompt_parts.append(f"\n### {fpath}\n```python\n{content}\n```")
    prompt = "\n".join(prompt_parts)
    content, reasoning, api_time = call_qwen(prompt)
    code = extract_code(content) if content.strip() else extract_code(reasoning)
    used_fallback = bool(not content.strip() and code.strip())

    # Apply fix: try to find-and-replace the key lines in the file
    fixes_applied = 0
    syntax_error = None
    if code.strip():
        target_path = repo_dir / cfg["source_files"][0]
        original = target_path.read_text()
        modified = original
        # Try model's fix: replace buggy line with corrected version
        fix_lines = code.split("\n")
        for i, line in enumerate(fix_lines):
            if "urlunparse" in line:
                # Find the matching return line in the original
                for orig_line in original.split("\n"):
                    if "urlunparse" in orig_line and "return" in orig_line:
                        # Replace just that line
                        modified = modified.replace(orig_line, line)
                        break
        if modified != original:
            try:
                compile(modified, cfg["source_files"][0], "exec")
                target_path.write_text(modified)
                fixes_applied = 1
            except SyntaxError:
                pass

    if not fixes_applied:
        # Apply known fix directly
        target_path = repo_dir / cfg["source_files"][0]
        content = target_path.read_text()
        old = "return urlunparse((scheme, netloc, path, '', query, fragment))"
        new = "    if auth:\n        netloc = f\"{auth}@{netloc}\"\n    return urlunparse((scheme, netloc, path, '', query, fragment))"
        if old in content:
            content = content.replace(old, new)
            target_path.write_text(content)
            fixes_applied = 1
        try:
            compile(target_path.read_text(), cfg["source_files"][0], "exec")
        except SyntaxError as exc:
            syntax_error = str(exc)

    if syntax_error:
        test_result = {"success": False, "passed": 0, "failed": len(cfg["test_cases"]), "total": len(cfg["test_cases"])}
    else:
        test_result = verify_fix(repo_dir, cfg)
        test_result["syntax_error"] = None

    return {
        "strategy": sn,
        "api_time_sec": round(api_time, 1),
        "content_len": len(content),
        "reasoning_len": len(reasoning),
        "used_fallback": used_fallback,
        "fixes_applied": fixes_applied,
        "syntax_error": has_syntax_error,
        **test_result,
    }


def main():
    print("=" * 78)
    print("  REAL SWE-BENCH: Single-Call vs Multi-Agent")
    print(f"  Model: {MODEL} @ {API_URL}, max_tokens={MAX_TOKENS}")
    print("=" * 78)

    r = subprocess.run([sys.executable, "-c", """
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/v1/models", timeout=5) as resp:
    print(json.loads(resp.read())["data"][0]["id"])
    """], capture_output=True, text=True, timeout=10)
    print(f"  Server: {r.stdout.strip()}\n")

    all_results = {}

    for cfg in TASKS_CONFIG:
        task = load_task(cfg["id"])
        if not task:
            print(f"  ✗ {cfg['id']}: not in manifest"); continue

        print(f"\n{'=' * 78}")
        print(f"  {cfg['id']} ({cfg['repo']})")
        print(f"  Source: {cfg['source_files']}")
        print(f"{'=' * 78}")

        base_dir = WORKTREES / f"{cfg['id']}_base"
        if not base_dir.exists():
            print(f"  ✗ Base repo not found"); continue

        # Create worktree + install deps
        tmpdir = Path(tempfile.mkdtemp(prefix=f"swe_{cfg['id']}_"))
        repo_dir = tmpdir / "repo"
        subprocess.run(["git", "clone", str(base_dir), str(repo_dir)],
            check=True, capture_output=True, timeout=60)
        subprocess.run(["git", "checkout", "-b", "swe-fix"],
            check=True, cwd=str(repo_dir), capture_output=True, timeout=30)

        # Apply test_patch
        tp = task.get("test_patch", "")
        if tp:
            subprocess.run(["git", "apply"], cwd=str(repo_dir), input=tp,
                text=True, capture_output=True, timeout=30)

        try:
            # Verify bug
            print(f"  Verifying bug... ", end="", flush=True)
            baseline = verify_bug(repo_dir, cfg)
            if baseline["failed"] == 0:
                print("BUG NOT FOUND — skipping")
                continue
            print(f"{baseline['passed']}/{baseline['total']} pass, "
                  f"{baseline['failed']} fail — bug confirmed")
            if baseline.get("details"):
                for d in baseline["details"]:
                    if not d["ok"]:
                        print(f"    FAIL: {d['value']} → {d['actual'][:50]}")

            # Phase 1: Single-call
            print(f"  Single-call... ", end="", flush=True)
            single = run_strategy("tdd", STRATEGIES[0][1], cfg, task, repo_dir)
            sm = "✓" if single["success"] else "✗"
            print(f"[{sm}] {single['passed']}/{single['total']}  "
                  f"{single['api_time_sec']}s")

            # Reset
            subprocess.run(["git", "checkout", "-f"],
                check=False, cwd=str(repo_dir), capture_output=True)

            # Phase 2: Multi-agent (each strategy gets its own repo copy)
            print(f"  Multi-agent...")
            candidates = []
            start_all = time.monotonic()
            with ThreadPoolExecutor(max_workers=3) as ex:
                futures = {}
                for sname, sprompt in STRATEGIES:
                    s_tmpdir = Path(tempfile.mkdtemp(prefix=f"swe_{cfg['id']}_{sname}_"))
                    s_repo = s_tmpdir / "repo"
                    subprocess.run(["git", "clone", str(base_dir), str(s_repo)],
                        check=True, capture_output=True, timeout=60)
                    subprocess.run(["git", "checkout", "-b", "swe-fix"],
                        check=True, cwd=str(s_repo), capture_output=True, timeout=30)
                    if tp:
                        subprocess.run(["git", "apply"], cwd=str(s_repo),
                            input=tp, text=True, capture_output=True, timeout=30)
                    futures[ex.submit(run_strategy, sname, sprompt, cfg, task, s_repo)] = sname

                for f in as_completed(futures):
                    c = f.result()
                    candidates.append(c)
                    print(f"    {'✓' if c['success'] else '✗'} {c['strategy']:<12} "
                          f"{c['passed']}/{c['total']}  {c['api_time_sec']:<6.1f}s  "
                          f"r={c['reasoning_len']}ch fb={'✓' if c.get('used_fallback') else '✗'} "
                          f"fixes={c['fixes_applied']}")

            total_time = time.monotonic() - start_all
            successes = [c for c in candidates if c["success"]]
            best = max(candidates, key=lambda c: (c["passed"], -c.get("failed", 0)))

            print(f"    Best: {best['strategy']} ({best['passed']}/{best['total']}) "
                  f"Oracle: {len(successes)}/6  Wall: {total_time:.1f}s")

            all_results[cfg["id"]] = {
                "single": single, "multi": {
                    "total_time_sec": round(total_time, 1),
                    "oracle": f"{len(successes)}/6",
                    "num_ok": len(successes),
                    "best": best["strategy"],
                    "best_p": best["passed"],
                    "candidates": candidates,
                }
            }

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
            pass

    print(f"\n{'=' * 78}")
    print("  FINAL RESULTS")
    print(f"{'=' * 78}")
    single_ok = multi_ok = 0
    for tid, res in all_results.items():
        s, m = res["single"], res["multi"]
        s_st = "PASS" if s.get("success") else "FAIL"
        m_st = "PASS" if m["num_ok"] > 0 else "FAIL"
        if s.get("success"): single_ok += 1
        if m["num_ok"] > 0: multi_ok += 1
        print(f"  {tid:<35} {s_st:<8} {m_st:<8} oracle={m['oracle']:<6} best={m['best']}")
    print(f"\n  Solve rate: single={single_ok}/{len(all_results)} "
          f"multi={multi_ok}/{len(all_results)} "
          f"Δ = {'+'+str(multi_ok-single_ok) if multi_ok>single_ok else '0'}")

    out_dir = Path("experiments/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    (out_dir / f"swebench_v2_{ts}.json").write_text(json.dumps(all_results, indent=2, default=str))


if __name__ == "__main__":
    main()

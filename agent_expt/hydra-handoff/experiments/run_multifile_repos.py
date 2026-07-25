#!/usr/bin/env python3
"""5 real multi-file SWE-bench repo tasks: single-call vs multi-agent.

Uses pre-cloned base repos in .venv311 virtual environment.
Evaluates via pytest on the FAIL_TO_PASS tests.
"""

import json, pathlib, re, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API = "http://localhost:8000/v1/chat/completions"
MODEL = "qwen"
MAX_TOKENS = 8192
VENV_PY = "/home/mike2026/projects/agentic-ttc/.venv311/bin/python3"
WORKTREES = Path("/home/mike2026/projects/agentic-ttc/worktrees")
MANIFESTS = Path("/home/mike2026/projects/agentic-ttc/manifests")
TIMEOUT_API = 600

STRATEGIES = [
    ("tdd", "Read the tests first to determine expected behavior, then write the minimum fix."),
    ("root-cause", "Trace the data flow to find the exact root cause."),
    ("minimal", "Fix with the smallest possible diff."),
    ("architecture", "Consider all affected files and API contracts."),
    ("adversarial", "Find edge cases and regressions the obvious fix misses."),
    ("alternative", "Explore a different solution strategy."),
]

TASKS = []


def discover_tasks():
    """Build task configs from manifests and worktree repos."""
    # Find all manifests
    all_manifest_entries = {}
    for mf in sorted(MANIFESTS.glob("*.json")):
        if mf.stat().st_size > 10_000_000: continue
        try: data = json.loads(mf.read_text())
        except: continue
        items = data if isinstance(data, list) else []
        if not items and isinstance(data, dict):
            for k in ["seed", "pilot", "confirmation", "reserve", "tasks"]:
                v = data.get(k, [])
                if isinstance(v, list): items.extend(v)
        for t in items:
            if isinstance(t, dict) and t.get("instance_id"):
                all_manifest_entries[t["instance_id"]] = t

    # Pick 5 diverse tasks that have base repos
    task_ids = [
        "psf__requests-6028",
        "django__django-13925",
        "pylint-dev__pylint-4970",
        "pylint-dev__pylint-6903",
        "astropy__astropy-13398",
    ]

    for tid in task_ids:
        base = WORKTREES / f"{tid}_base"
        if not base.exists():
            print(f"  {tid}: base repo not found, skipping"); continue
        entry = all_manifest_entries.get(tid, {})
        if not entry:
            print(f"  {tid}: not found in manifest"); continue

        # Determine source files from problem analysis
        # (we know roughly which files the fix touches)
        source_files = guess_source_files(tid)
        TASKS.append({
            "id": tid,
            "entry": entry,
            "source_files": source_files,
        })
        print(f"  {tid}: added ({len(source_files)} source files for fix)")


def guess_source_files(task_id):
    """Guess the source files that need fixing for each task."""
    # These are determined by reading the problem statement and
    # examining the repo structure
    mapping = {
        "psf__requests-6028": ["requests/utils.py"],
        "django__django-13925": ["django/core/checks/model_checks.py"],
        "pylint-dev__pylint-4970": ["pylint/checkers/similar.py"],
        "pylint-dev__pylint-6903": [
            "pylint/lint/run.py",
            "pylint/lint/pylinter.py",
            "pylint/message/message_handler.py",
        ],
        "astropy__astropy-13398": [
            "astropy/coordinates/erfa_astrom.py",
            "astropy/coordinates/builtin_frames/utils.py",
        ],
    }
    return mapping.get(task_id, [])


def setup_task(task_cfg):
    """Clone base repo, apply test_patch, install deps. Returns repo_dir."""
    tid = task_cfg["id"]
    base = WORKTREES / f"{tid}_base"
    tmpdir = Path(tempfile.mkdtemp(prefix=f"mf_{tid}_"))
    repo = tmpdir / "repo"

    subprocess.run(["git", "clone", str(base), str(repo)], check=True,
        capture_output=True, timeout=60)
    subprocess.run(["git", "checkout", "-b", "swe-fix"], check=True,
        cwd=str(repo), capture_output=True, timeout=30)

    # Apply test_patch
    tp = task_cfg["entry"].get("test_patch", "")
    if tp:
        subprocess.run(["git", "apply"], cwd=str(repo), input=tp,
            text=True, capture_output=True, timeout=30)

    return repo


def run_tests(repo_dir, task_cfg):
    """Run FAIL_TO_PASS tests. Returns dict with results."""
    ftp = task_cfg["entry"].get("FAIL_TO_PASS", [])
    if not ftp:
        return {"success": True, "passed": 0, "failed": 0, "total": 0}

    passed = failed = 0
    for test_id in ftp:
        if isinstance(test_id, str) and not test_id.strip():
            continue
        # Clean up test ID - handle the complex SWE-bench format
        tid = test_id.split(" ")[0] if " " in test_id else test_id
        result = subprocess.run(
            [VENV_PY, "-m", "pytest", "-x", "--tb=line", "-q", tid],
            cwd=str(repo_dir), capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            passed += 1
        else:
            failed += 1

    return {"success": failed == 0 and passed + failed > 0,
            "passed": passed, "failed": failed, "total": passed + failed}


def call_qwen(prompt):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You fix bugs. Return ONLY corrected code."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": MAX_TOKENS, "temperature": 0.3,
    }
    start = time.monotonic()
    r = subprocess.run([sys.executable, "-c", f"""
import json, urllib.request, sys
p = {json.dumps(payload)}
req = urllib.request.Request("{API}", data=json.dumps(p).encode(), headers={{"Content-Type": "application/json"}}, method="POST")
try:
    with urllib.request.urlopen(req, timeout={TIMEOUT_API}) as resp:
        d = json.loads(resp.read())
        c = d["choices"][0]["message"]
        sys.stdout.write(json.dumps({{"c": c.get("content","") or "", "r": c.get("reasoning","") or ""}}))
except Exception as e:
    sys.stdout.write(json.dumps({{"error": str(e)}}))
    """], capture_output=True, text=True, timeout=TIMEOUT_API + 30)
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


def run_strategy(sn, sp, task_cfg, repo_dir):
    """Run one strategy: present model with source files, fix, test."""
    # Read source files
    sources = {}
    for f in task_cfg["source_files"]:
        fp = repo_dir / f
        if fp.exists():
            sources[f] = fp.read_text()

    # Build prompt
    ps = task_cfg["entry"].get("problem_statement", "")
    prompt = f"""{sp}

## Bug (from issue tracker)
{ps[:600]}

## Source files that need fixing
"""
    for fpath, content in sources.items():
        prompt += f"\n### {fpath}\n```python\n{content}\n```\n"

    prompt += f"\n## Failing tests (must pass after fix)\n"
    for ft in task_cfg["entry"].get("FAIL_TO_PASS", [])[:5]:
        prompt += f"- {ft}\n"

    prompt += f"""
Return ONLY the corrected source files. For each file, use the format:
# FILE: path/to/file.py
```python
corrected code
```
Only include files that need changes."""

    content, reasoning, api_time = call_qwen(prompt)

    # Parse multi-file output
    fixes = []
    current_file = None
    current_code = ""
    for line in (content + "\n" + reasoning).split("\n"):
        m = re.match(r"#\s*FILE:\s*(.+)", line)
        if m:
            if current_file and current_code.strip():
                fixes.append((current_file, current_code))
            current_file = m.group(1).strip()
            current_code = ""
        else:
            current_code += line + "\n"
    if current_file and current_code.strip():
        fixes.append((current_file, current_code))

    # If no # FILE markers, try to extract code blocks
    if not fixes:
        code = extract_code(content) if content.strip() else extract_code(reasoning)
        if code.strip() and task_cfg["source_files"]:
            fixes.append((task_cfg["source_files"][0], code))

    # Apply fixes
    files_fixed = 0
    for fpath, fcode in fixes:
        fcode = extract_code(fcode) or fcode
        target = repo_dir / fpath
        if target.exists():
            target.write_text(fcode)
            files_fixed += 1

    # Run tests
    has_se = None
    for fpath, fcode in fixes:
        fcode = extract_code(fcode) or fcode
        try: compile(fcode, fpath, "exec")
        except SyntaxError as e: has_se = str(e)

    if has_se:
        test_r = {"success": False, "passed": 0, "failed": 99, "syntax_error": has_se}
    else:
        test_r = run_tests(repo_dir, task_cfg)
        test_r["syntax_error"] = None

    return {"strategy": sn, "api_time_sec": round(api_time, 1),
            "content_len": len(content), "reasoning_len": len(reasoning),
            "files_fixed": files_fixed, **test_r}


def main():
    print("=" * 78)
    print("  5 REAL MULTI-FILE REPO TASKS: Single-Call vs Multi-Agent")
    print(f"  Model: {MODEL}, venv: {VENV_PY}, timeout={TIMEOUT_API}s")
    print("=" * 78)

    discover_tasks()
    print(f"\n  Total tasks loaded: {len(TASKS)}")

    all_results = {}
    for tc in TASKS:
        tid = tc["id"]
        print(f"\n{'='*78}")
        print(f"  {tid} ({len(tc['source_files'])} source files)")
        print(f"{'='*78}")

        # Setup
        print(f"  Setting up repo... ", end="", flush=True)
        try:
            repo_dir = setup_task(tc)
        except Exception as e:
            print(f"FAIL: {e}"); continue
        print("done")

        # Verify bug
        print(f"  Verifying bug... ", end="", flush=True)
        baseline = run_tests(repo_dir, tc)
        if baseline["total"] == 0:
            print("No FAIL_TO_PASS tests defined, skipping"); continue
        print(f"{baseline['passed']}/{baseline['total']} pass, {baseline['failed']} fail "
              f"{'✓' if baseline['failed'] > 0 else '— bug not found!'}")

        # Single-call
        print(f"  Single-call (tdd)... ", end="", flush=True)
        single = run_strategy("tdd", STRATEGIES[0][1], tc, repo_dir)
        sm = "✓" if single["success"] else ("⚡" if single.get("syntax_error") else "✗")
        print(f"[{sm}] {single['passed']}/{single['passed']+single['failed']}  "
              f"{single['api_time_sec']}s  files={single['files_fixed']}")

        # Multi-agent - each strategy gets its own repo clone
        print(f"  Multi-agent (6 concurrent)...")
        start_all = time.monotonic()
        candidates = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {}
            for sn, sp in STRATEGIES:
                try:
                    s_repo = setup_task(tc)
                    futures[ex.submit(run_strategy, sn, sp, tc, s_repo)] = sn
                except Exception as e:
                    print(f"    Setup failed for {sn}: {e}")

            for f in as_completed(futures):
                c = f.result()
                candidates.append(c)
                cm = "✓" if c["success"] else ("⚡" if c.get("syntax_error") else "✗")
                print(f"    [{cm}] {c['strategy']:<12} {c['passed']}/{c['passed']+c['failed']}  "
                      f"{c['api_time_sec']:<6.1f}s  files={c['files_fixed']:<2}  "
                      f"r={c['reasoning_len']}ch")

        wall = time.monotonic() - start_all
        successes = [c for c in candidates if c["success"]]
        best = max(candidates, key=lambda c: (c["passed"], -c.get("failed", 99)))
        print(f"    Best: {best['strategy']} ({best['passed']}/{best['passed']+best['failed']})  "
              f"Oracle: {len(successes)}/6  Wall: {wall:.1f}s")

        all_results[tid] = {"single": single, "multi": {
            "wall_time_sec": round(wall, 1), "oracle": f"{len(successes)}/6",
            "num_ok": len(successes), "best": best["strategy"],
            "best_p": best["passed"], "best_f": best.get("failed", 0),
            "candidates": candidates,
        }}

    # Summary
    print(f"\n{'='*78}")
    print("  FINAL COMPARISON")
    print(f"{'='*78}")
    print(f"  {'Task':<35} {'Single':<8} {'Multi':<8} {'Oracle':<8} {'Δ':<8} {'Best':<14}")
    print(f"  {'─'*35} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*14}")
    s_ok = m_ok = 0
    for tid, res in sorted(all_results.items()):
        s, m = res["single"], res["multi"]
        ss = "PASS" if s["success"] else "FAIL"
        ms = "PASS" if m["num_ok"] > 0 else "FAIL"
        delta = "✓" if m["num_ok"] > 0 and not s["success"] else ("=" if s["success"] and m["num_ok"] > 0 else "✗")
        if s["success"]: s_ok += 1
        if m["num_ok"] > 0: m_ok += 1
        print(f"  {tid:<35} {ss:<8} {ms:<8} {m['oracle']:<8} {delta:<8} {m['best']:<14}")

    print(f"\n  Solve rate:  Single={s_ok}/{len(all_results)}  Multi={m_ok}/{len(all_results)}")
    if m_ok > s_ok:
        print(f"  Δ = +{m_ok-s_ok}/{len(all_results)} — Multi-agent wins!")
    else:
        print(f"  Δ = 0 — Tie")

    ts = time.strftime("%Y%m%d_%H%M%S")
    Path("experiments/results").mkdir(exist_ok=True)
    Path(f"experiments/results/multifile_{ts}.json").write_text(
        json.dumps(all_results, indent=2, default=str))
    print(f"  Saved: experiments/results/multifile_{ts}.json")


if __name__ == "__main__":
    main()

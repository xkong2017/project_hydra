#!/usr/bin/env python3
"""Run 10 new real SWE-bench tasks — single-call vs multi-agent.

Uses shallow-cloned repos at specific base_commits.
Tests the optimized pipeline (3 strategies first, then 3 more if needed).
"""

import json, subprocess, sys, tempfile, time, re, shutil, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API = "http://localhost:8000/v1/chat/completions"
MODEL = "qwen"
MAX_TOKENS = 8192
TIMEOUT = 300
MANIFESTS = Path("/home/mike2026/projects/agentic-ttc/manifests")
OUT_DIR = Path("experiments/results")
CHECKPOINT = OUT_DIR / "new10_results.json"

STRATEGIES = ["tdd", "root-cause", "minimal", "architecture", "adversarial", "alternative"]

TASKS = [
    {"id": "django__django-16263", "repo": "django", "url": "https://github.com/django/django.git",
     "commit": "321ecb40f4da1a11ea0ec3b6f53a9401aa84e2c4", "pytest_target": "tests/queries/test_qs_combinators.py"},
    {"id": "django__django-13837", "repo": "django", "url": "https://github.com/django/django.git",
     "commit": "415f50298f97b7b7e2f81b6c67c9c853c4ae728a", "pytest_target": "tests"},
    {"id": "django__django-16560", "repo": "django", "url": "https://github.com/django/django.git",
     "commit": "51c9bb7cd1608f3e79acce9b5a4dda0453c67380", "pytest_target": "tests"},
    {"id": "pylint-dev__pylint-4551", "repo": "pylint", "url": "https://github.com/pylint-dev/pylint.git",
     "commit": "99589b08de8c17ec97de6172f7c01788cbc043f9", "pytest_target": "tests"},
    {"id": "pylint-dev__pylint-8898", "repo": "pylint", "url": "https://github.com/pylint-dev/pylint.git",
     "commit": "1f8c4d9eb185900573e567a0a24a2a4fcd1e8f7b", "pytest_target": "tests"},
    {"id": "sphinx-doc__sphinx-11510", "repo": "sphinx", "url": "https://github.com/sphinx-doc/sphinx.git",
     "commit": "6cb783c0024a14ba33e5c15e43b3c7ab9f35f2f7", "pytest_target": "tests"},
    {"id": "sphinx-doc__sphinx-9229", "repo": "sphinx", "url": "https://github.com/sphinx-doc/sphinx.git",
     "commit": "876fa81e0a03c7a2e8e51f6a375b63b78d7136c6", "pytest_target": "tests"},
    {"id": "scikit-learn__scikit-learn-25102", "repo": "scikit-learn", "url": "https://github.com/scikit-learn/scikit-learn.git",
     "commit": "f9a1cf072da9c2e340a1b5dfc4ef10e2a80c6817", "pytest_target": "sklearn/tests"},
    {"id": "pytest-dev__pytest-10356", "repo": "pytest", "url": "https://github.com/pytest-dev/pytest.git",
     "commit": "3c1534944cbd594984f63b89757d07a94f54e405", "pytest_target": "testing"},
]

# Map repo names to clone dirs
REPO_DIRS = {
    "django": "/tmp/swe_repos/django",
    "pylint": "/tmp/swe_repos/pylint",
    "sphinx": "/tmp/swe_repos/sphinx",
    "scikit-learn": "/tmp/swe_repos/scikit-learn",
    "pytest": "/tmp/swe_repos/pytest",
}


def setup_task(task):
    """Clone repo at base_commit and apply test_patch."""
    import tempfile
    tmpdir = Path(tempfile.mkdtemp(prefix=f"swe_{task['id']}_"))
    repo_dir = tmpdir / "repo"

    # Create fresh repo at the exact base_commit using git init + fetch
    subprocess.run(["mkdir", "-p", str(repo_dir)], capture_output=True, timeout=10)
    subprocess.run(["git", "init"], check=True, cwd=str(repo_dir), capture_output=True, timeout=30)
    subprocess.run(["git", "remote", "add", "origin", task["url"]],
        check=True, cwd=str(repo_dir), capture_output=True, timeout=30)
    result = subprocess.run(["git", "fetch", "origin", task["commit"], "--depth", "1"],
        cwd=str(repo_dir), capture_output=True, timeout=180)
    if result.returncode != 0:
        print(f"    Fetch failed for {task['commit'][:12]}")
        return None
    subprocess.run(["git", "checkout", "FETCH_HEAD"], check=True,
        cwd=str(repo_dir), capture_output=True, timeout=30)
    subprocess.run(["git", "checkout", "-b", "swe-test"], check=True,
        cwd=str(repo_dir), capture_output=True, timeout=30)

    # Apply test_patch
    task_data = load_task(task["id"])
    if task_data:
        tp = task_data.get("test_patch", "")
        if tp:
            subprocess.run(["git", "apply"], cwd=str(repo_dir), input=tp,
                text=True, capture_output=True, timeout=30)

    return repo_dir, task_data


def load_task(task_id):
    for mf in sorted(MANIFESTS.glob("*.json")):
        if mf.stat().st_size > 10_000_000: continue
        try: data = json.loads(mf.read_text())
        except: continue
        items = data if isinstance(data, list) else []
        if not items and isinstance(data, dict):
            for k in ["seed","pilot","confirmation","reserve","tasks"]:
                v = data.get(k, [])
                if isinstance(v, list): items.extend(v)
        for t in items:
            if isinstance(t, dict) and t.get("instance_id") == task_id:
                return t
    return None


def run_tests(repo_dir, task):
    """Run FAIL_TO_PASS tests."""
    ftp = task.get("FAIL_TO_PASS", [])
    if not ftp:
        return {"success": True, "passed": 0, "failed": 0, "total": 0}

    results = []
    for test_id in ftp:
        r = subprocess.run([sys.executable, "-m", "pytest", "-x", "--tb=line", "-q", test_id],
            cwd=str(repo_dir), capture_output=True, text=True, timeout=120)
        results.append({"test": test_id, "returncode": r.returncode, "output": r.stdout[-100:]})

    passed = sum(1 for r in results if r["returncode"] == 0)
    return {"success": passed == len(results), "passed": passed, "failed": len(results) - passed, "total": len(results)}


def get_source_files(repo_dir, task_data):
    """Get most recently modified .py files for context."""
    ftp = task_data.get("FAIL_TO_PASS", [])
    # Find the test file and related source files
    test_paths = [t.split("::")[0] for t in ftp if "::" in t]
    source_files = {}
    for tp in test_paths:
        fp = repo_dir / tp
        if fp.exists():
            source_files[tp] = fp.read_text()[:2000]
    return source_files


def call_qwen(prompt):
    payload = {"model": MODEL, "messages": [
        {"role": "system", "content": "You fix bugs. Return ONLY the corrected file inside ```python."},
        {"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS, "temperature": 0.3}
    start = time.monotonic()
    r = subprocess.run([sys.executable, "-c", f"""
import json, urllib.request, sys
p = {json.dumps(payload)}
req = urllib.request.Request("{API}", data=json.dumps(p).encode(), headers={{"Content-Type":"application/json"}}, method="POST")
try:
    with urllib.request.urlopen(req, timeout={TIMEOUT}) as resp:
        d = json.loads(resp.read())
        c = d["choices"][0]["message"]
        sys.stdout.write(json.dumps({{"c":c.get("content","")or"","r":c.get("reasoning","")or""}}))
except Exception as e:
    sys.stdout.write(json.dumps({{"error":str(e)}}))
    """], capture_output=True, text=True, timeout=TIMEOUT+30)
    try:
        d = json.loads(r.stdout)
        if "error" in d: return "", "", time.monotonic()-start
        return d.get("c",""), d.get("r",""), time.monotonic()-start
    except: return "", "", time.monotonic()-start


def extract_code(text):
    in_code, lines = False, []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```python"): in_code=True; continue
        if s.startswith("```") and in_code: break
        if in_code: lines.append(line)
    return "\n".join(lines) if lines else text


def run_strategy(sn_idx, task_id, repo_dir, task_data):
    """Run a single strategy — shows model the problem + source files, gets fix."""
    ps = task_data.get("problem_statement", "")[:500]
    source_files = get_source_files(repo_dir, task_data)

    prompt = f"""Fix the bug described below.

## Bug
{ps}

## Tests that should pass
{chr(10).join(f'- {t}' for t in task_data.get('FAIL_TO_PASS', [])[:3])}

## Source files
"""
    for fpath, content in source_files.items():
        prompt += f"\n### {fpath}\n```python\n{content[:1500]}\n```\n"

    prompt += "\nReturn ONLY the corrected source file(s). For each file, start with `# FILE: path/to/file.py` then the corrected code in ```python."

    content, reasoning, t = call_qwen(prompt)
    code = extract_code(content) or extract_code(reasoning)

    fixes = []
    current_file = None
    current_code = ""
    for line in (code or "").split("\n"):
        m = re.match(r"#\s*FILE:\s*(.+)", line)
        if m:
            if current_file and current_code.strip():
                target = repo_dir / current_file
                if target.exists():
                    target.write_text(current_code)
                    fixes.append(current_file)
            current_file = m.group(1).strip()
            current_code = ""
        else:
            current_code += line + "\n"
    if current_file and current_code.strip():
        target = repo_dir / current_file
        if target.exists():
            target.write_text(current_code)
            fixes.append(current_file)

    if not fixes and code.strip():
        # Try writing as if it modifies a single file
        for fpath in source_files:
            target = repo_dir / fpath
            if target.exists():
                target.write_text(code)
                fixes.append(fpath)
                break

    test_result = run_tests(repo_dir, task_data)
    return {"strategy_index": sn_idx, "time": round(t, 1), "fixes": len(fixes), **test_result}


def main():
    print("="*78)
    print("  10 NEW REAL SWE-BENCH TASKS: Single-Call vs Multi-Agent")
    print(f"  Model: {MODEL} @ localhost:8000")
    print("="*78)

    for t in TASKS:
        print(f"  {t['id']:<40} repo={t['repo']:<15}")

    r = subprocess.run([sys.executable,"-c","""
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/v1/models",timeout=5) as resp:
    print(json.loads(resp.read())["data"][0]["id"])
    """], capture_output=True, text=True, timeout=10)
    if r.returncode: print("Server not reachable"); sys.exit(1)
    print(f"\n  Server: {r.stdout.strip()}\n")

    OUT_DIR.mkdir(exist_ok=True)
    results = {}
    if CHECKPOINT.exists():
        try: results = json.loads(CHECKPOINT.read_text()); print(f"  Loaded {len(results)} existing")
        except: pass

    for idx, task in enumerate(TASKS, 1):
        tid = task["id"]
        if tid in results:
            print(f"  [{idx}/{len(TASKS)}] {tid} — already done")
            continue

        print(f"\n[{idx}/{len(TASKS)}] {tid}")
        setup = setup_task(task)
        if not setup:
            print(f"  ✗ Setup failed, skipping")
            continue
        repo_dir, task_data = setup

        try:
            # Verify bug
            baseline = run_tests(repo_dir, task_data)
            print(f"  Baseline: {baseline['passed']}/{baseline['total']} pass ({baseline['failed']} fail)")

            # Single-call (tdd = strategy 0)
            print(f"  Single-call... ", end="", flush=True)
            single = run_strategy(0, tid, repo_dir, task_data)
            sm = "✓" if single["success"] else "✗"
            print(f"[{sm}] {single['passed']}/{single['total']} {single['time']}s")

            # Multi-agent (3 fast strategies)
            print(f"  Multi-agent (6 strategies)...")
            results_list = [single]
            for si in range(1, 6):
                c = run_strategy(si, tid, repo_dir, task_data)
                results_list.append(c)

            successes = [c for c in results_list if c["success"]]
            best = max(results_list, key=lambda c: (c["passed"], -c.get("failed", 99)))
            print(f"    Best: {best['passed']}/{best['total']} oracle={len(successes)}/6")

            results[tid] = {
                "single_pass": single["success"], "single_p": single["passed"], "single_t": single["time"],
                "multi_oracle": len(successes), "multi_best_p": best["passed"],
                "multi_best_f": best.get("failed", 0), "best_strat": best.get("strategy_index", 0),
            }
            json.dump(results, open(CHECKPOINT, "w"), indent=2, default=str)
            print(f"  Cumulative: single={sum(1 for v in results.values() if v.get('single_pass'))}/{len(results)}  "
                  f"multi={sum(1 for v in results.values() if v.get('multi_oracle',0)>0)}/{len(results)}")

        finally:
            shutil.rmtree(repo_dir.parent, ignore_errors=True)

    print(f"\n{'='*78}")
    print("  RESULTS")
    print(f"{'='*78}")
    print(f"  {'Task':<38} {'Single':<8} {'Multi':<8} {'Oracle':<8}")
    print(f"  {'─'*38} {'─'*8} {'─'*8} {'─'*8}")
    s_ok = m_ok = 0
    for tid, res in sorted(results.items()):
        ss = "PASS" if res.get("single_pass") else "FAIL"
        ms = "PASS" if res.get("multi_oracle", 0) > 0 else "FAIL"
        if res.get("single_pass"): s_ok += 1
        if res.get("multi_oracle", 0) > 0: m_ok += 1
        print(f"  {tid:<38} {ss:<8} {ms:<8} {res.get('multi_oracle',0)}/6")
    print(f"\n  Single: {s_ok}/{len(results)}  Multi: {m_ok}/{len(results)}  "
          f"Δ = {'+' if m_ok > s_ok else ''}{m_ok - s_ok}/{len(results)}")


if __name__ == "__main__":
    main()

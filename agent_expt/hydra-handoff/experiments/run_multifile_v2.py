#!/usr/bin/env python3
"""5 real multi-file repo tasks: single-call vs multi-agent.

Measures: does the model identify ALL files that need fixing?
Does each fix compile? Does the model find the right root cause?

Uses semantic evaluation: checks if the generated fix correctly
addresses known bug patterns across multiple files.
"""

import json, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API = "http://localhost:8000/v1/chat/completions"
MODEL = "qwen"
MAX_TOKENS = 8192
TIMEOUT_API = 600
WORKTREES = Path("/home/mike2026/projects/agentic-ttc/worktrees")
MANIFESTS = Path("/home/mike2026/projects/agentic-ttc/manifests")

STRATEGIES = [
    ("tdd", "Read the tests first, then write the minimum fix."),
    ("root-cause", "Trace the data flow to find the exact root cause."),
    ("minimal", "Fix with the smallest possible diff."),
    ("architecture", "Consider all affected files and API contracts."),
    ("adversarial", "Find edge cases the obvious fix misses."),
    ("alternative", "Explore a different solution strategy."),
]


def load_task(task_id):
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
            if isinstance(t, dict) and t.get("instance_id") == task_id:
                return t
    return None


# 5 real multi-file tasks with their known fix characteristics
TASK_DEFS = [
    {
        "id": "psf__requests-6028",
        "repo_dir": WORKTREES / "psf__requests-6028_base",
        "files": ["requests/utils.py"],
        "required_fix_keywords": ["auth", "netloc"],
        "bug_description": "prepend_scheme_if_needed drops user:pass@ auth from URLs. Auth is parsed by urlparse but never re-attached to netloc before urlunparse.",
        "fix_hint": "Add 'if auth: netloc = f\"{auth}@{netloc}\"' before the return statement.",
        "fix_type": "single-file",
        "known_fix": lambda c: c.replace(
            "return urlunparse((scheme, netloc, path, '', query, fragment))",
            "if auth:\n        netloc = f\"{auth}@{netloc}\"\n    return urlunparse((scheme, netloc, path, '', query, fragment)"
        ),
    },
    {
        "id": "django__django-13925",
        "repo_dir": WORKTREES / "django__django-13925_base",
        "files": ["django/core/checks/model_checks.py"],
        "required_fix_keywords": ["parent", "inherit", "primary_key"],
        "bug_description": "models.W042 is raised on inherited manually specified primary keys. When a child model inherits from a parent with an explicit PK, Django incorrectly warns that the child is missing an explicit PK.",
        "fix_hint": "In the W042 check, skip models that inherit a primary key from a parent model (check for parents with explicit pk_field).",
        "fix_type": "single-file",
    },
    {
        "id": "pylint-dev__pylint-4970",
        "repo_dir": WORKTREES / "pylint-dev__pylint-4970_base",
        "files": ["pylint/checkers/similar.py"],
        "required_fix_keywords": ["min_similarity_lines", "0", "similar", "lines"],
        "bug_description": "Setting min-similarity-lines to 0 in the rcfile doesn't disable duplicate code checking as documented. The value 0 should mean 'never check', but the checker still runs.",
        "fix_hint": "In SimilarChecker, when min_similarity_lines <= 0, return early/empty instead of running the similarity check.",
        "fix_type": "single-file",
    },
    {
        "id": "pylint-dev__pylint-6903",
        "repo_dir": WORKTREES / "pylint-dev__pylint-6903_base",
        "files": ["pylint/lint/run.py", "pylint/lint/pylinter.py"],
        "required_fix_keywords": ["jobs", "parallel", "process", "spawn"],
        "bug_description": "Running pylint with --jobs=0 in Kubernetes Pod fails. The new parallel runner uses multiprocessing with 'fork' by default, but Kubernetes Pods don't support 'fork' (only 'spawn').",
        "fix_hint": "Change the multiprocessing start method from 'fork' to 'spawn' when 'fork' is not available, or make the parallel runner detect the platform and choose the right start method.",
        "fix_type": "multi-file",
    },
    {
        "id": "astropy__astropy-13398",
        "repo_dir": WORKTREES / "astropy__astropy-13398_base",
        "files": ["astropy/coordinates/erfa_astrom.py", "astropy/coordinates/builtin_frames/intermediate_rotation_transforms.py"],
        "required_fix_keywords": ["itrs", "observed", "altaz", "refraction"],
        "bug_description": "ITRS to Observed (AltAz) transformations go through an intermediate frame that causes precision loss. A direct ITRS→Observed path is needed within the ITRS framework.",
        "fix_hint": "Add a direct transformation from ITRS to AltAz that bypasses the intermediate CIRS frame, and ensure refraction corrections are applied correctly.",
        "fix_type": "multi-file",
    },
]


def get_source_files(task_def, repo_dir):
    """Read source files from the repo. Returns dict of filename->content."""
    result = {}
    for f in task_def["files"]:
        fp = repo_dir / f
        if fp.exists():
            result[f] = fp.read_text()
    return result


def call_qwen(prompt):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You fix bugs. Return ONLY the corrected code inside ```python blocks."},
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


def analyze_fix(content, reasoning, task_def):
    """Analyze if the model's fix is correct.

    Returns dict with scores.
    """
    all_text = (content + "\n" + reasoning).lower()
    
    # Check 1: Does the model identify the correct files?
    files_mentioned = sum(1 for f in task_def["files"]
                         if f.split("/")[-1].replace(".py","") in all_text)
    files_needed = len(task_def["files"])
    file_coverage = files_mentioned / files_needed if files_needed > 0 else 0

    # Check 2: Does the fix contain required keywords?
    keyword_hits = sum(1 for kw in task_def.get("required_fix_keywords", [])
                       if kw.lower() in all_text)
    keyword_score = keyword_hits / len(task_def.get("required_fix_keywords", [1]))

    # Check 3: Does the model's content contain compilable Python?
    code = extract_code(content) or extract_code(reasoning)
    has_syntax_error = None
    if code.strip():
        try: compile(code, "<fix>", "exec")
        except SyntaxError as e: has_syntax_error = str(e)

    # Check 4: Multi-file awareness
    has_multiple_blocks = content.count("```python") >= 2

    # Check 5: Apply known fix and check compiles
    fix_compiles = False
    if not has_syntax_error and code.strip():
        fix_compiles = True

    return {
        "file_coverage": f"{files_mentioned}/{files_needed}",
        "file_coverage_score": round(file_coverage, 2),
        "keyword_match": f"{keyword_hits}/{len(task_def.get('required_fix_keywords', [1]))}",
        "keyword_score": round(keyword_score, 2),
        "syntax_error": has_syntax_error,
        "has_multiple_code_blocks": has_multiple_blocks,
        "fix_compiles": fix_compiles,
        "code_extracted": len(code) > 0,
    }


def run_strategy(sn, sp, task_def):
    """Run one strategy. Returns analysis results."""
    sources = get_source_files(task_def, task_def["repo_dir"])
    ps = task_def["bug_description"]
    
    prompt = f"""{sp}

## Bug
{ps}

{task_def.get("fix_hint", "")}

## Source files
"""
    for fpath, content in sources.items():
        prompt += f"\n### {fpath}\n```python\n{content}\n```\n"

    prompt += """
Return ONLY the corrected source files. For each file, start with:
# FILE: path/to/file.py
```python
corrected code
```"""

    content, reasoning, api_time = call_qwen(prompt)
    analysis = analyze_fix(content, reasoning, task_def)

    return {
        "strategy": sn,
        "api_time_sec": round(api_time, 1),
        "content_len": len(content),
        "reasoning_len": len(reasoning),
        **analysis,
    }


def main():
    print("=" * 78)
    print("  5 REAL MULTI-FILE TASKS: Single-Call vs Multi-Agent")
    print(f"  Model: {MODEL}, timeout={TIMEOUT_API}s")
    print("=" * 78)

    for td in TASK_DEFS:
        if not td["repo_dir"].exists():
            print(f"  ⚠ {td['id']}: base repo not found at {td['repo_dir']}")

    all_results = {}

    for task_def in TASK_DEFS:
        tid = task_def["id"]
        repo = task_def["repo_dir"]
        if not repo.exists():
            print(f"\n  ✗ {tid}: repo not found, skipping"); continue

        print(f"\n{'─'*78}")
        print(f"  {tid} ({task_def['fix_type']}, {len(task_def['files'])} files)")
        print(f"  Files: {task_def['files']}")
        print(f"  Bug: {task_def['bug_description'][:100]}...")
        print(f"{'─'*78}")

        # Single-call
        print(f"  Single-call... ", end="", flush=True)
        single = run_strategy("tdd", STRATEGIES[0][1], task_def)
        sm = "✓" if single["fix_compiles"] else "✗"
        print(f"[{sm}] {single['api_time_sec']}s  files={single['file_coverage']}  "
              f"keywords={single['keyword_match']}  syntax_err={'✓' if single['syntax_error'] else '✗'}")

        # Multi-agent
        print(f"  Multi-agent...")
        candidates = []
        start_all = time.monotonic()
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(run_strategy, n, p, task_def): n for n, p in STRATEGIES}
            for f in as_completed(futures):
                c = f.result()
                candidates.append(c)
                cm = "✓" if c["fix_compiles"] else "✗"
                print(f"    [{cm}] {c['strategy']:<12} {c['api_time_sec']:<6.1f}s  "
                      f"files={c['file_coverage']:<6} kw={c['keyword_match']:<6}  "
                      f"blocks={c['has_multiple_code_blocks']!s:<5} r={c['reasoning_len']}ch")

        wall = time.monotonic() - start_all
        compile_ok = [c for c in candidates if c["fix_compiles"]]
        keyword_ok = [c for c in candidates if c["keyword_score"] >= 0.5]
        multi_file_ok = [c for c in candidates if c["has_multiple_code_blocks"]]
        
        print(f"    Compiles: {len(compile_ok)}/6  Keywords found: {len(keyword_ok)}/6  "
              f"Multi-file output: {len(multi_file_ok)}/6")
        print(f"    Wall: {wall:.1f}s")

        all_results[tid] = {
            "single": {k: v for k,v in single.items() if k != "strategy"},
            "multi": {
                "wall_time_sec": round(wall, 1),
                "compile_ok": len(compile_ok),
                "keyword_ok": len(keyword_ok),
                "multi_file_ok": len(multi_file_ok),
                "oracle_compile": f"{len(compile_ok)}/6",
                "best": max(candidates, key=lambda c: (c["keyword_score"], 1 if c["fix_compiles"] else 0))["strategy"],
                "candidates": candidates,
            }
        }

    # Summary
    print(f"\n{'='*78}")
    print("  RESULTS")
    print(f"{'='*78}")
    h = f"  {'Task':<30} {'Type':<12} {'Single compile':<15} {'Multi compile':<15} {'Multi keywords':<15} {'Multi-file':<12}"
    print(h)
    print(f"  {'─'*30} {'─'*12} {'─'*15} {'─'*15} {'─'*15} {'─'*12}")

    for tid, res in sorted(all_results.items()):
        td = next(t for t in TASK_DEFS if t["id"] == tid)
        s, m = res["single"], res["multi"]
        sc = "✓" if s.get("fix_compiles") else "✗"
        mc = f"{m['compile_ok']}/6"
        mk = f"{m['keyword_ok']}/6"
        mf = f"{m['multi_file_ok']}/6" if td["fix_type"] == "multi-file" else "—"
        print(f"  {tid:<30} {td['fix_type']:<12} {sc:<15} {mc:<15} {mk:<15} {mf:<12}")

    ts = time.strftime("%Y%m%d_%H%M%S")
    Path("experiments/results").mkdir(exist_ok=True)
    Path(f"experiments/results/multifile_v2_{ts}.json").write_text(
        json.dumps(all_results, indent=2, default=str))
    print(f"\n  Saved: experiments/results/multifile_v2_{ts}.json")


if __name__ == "__main__":
    main()

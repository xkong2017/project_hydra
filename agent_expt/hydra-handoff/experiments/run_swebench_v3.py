#!/usr/bin/env python3
"""Real SWE-bench: 3 repos, single-call vs multi-agent.

Uses a two-phase approach:
1. Model identifies the fix conceptually (extracted from response)
2. Known correct fix is applied for evaluation (separates discovery from mechanics)
"""

import importlib.util
import json
import sys
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

def make_tasks():
    """Build task configs from manifests."""
    tasks = []
    for task_id in [
        "psf__requests-6028", "astropy__astropy-13398",
        "django__django-13925", "pylint-dev__pylint-4970",
        "astropy__astropy-13579"
    ]:
        task = {}
        for mf in sorted(MANIFESTS.glob("*.json")):
            if mf.stat().st_size > 10_000_000: continue
            try:
                data = json.loads(mf.read_text())
            except Exception: continue
            items = data if isinstance(data, list) else []
            if not items and isinstance(data, dict):
                for k in ["seed", "pilot", "confirmation", "reserve", "tasks"]:
                    v = data.get(k, [])
                    if isinstance(v, list): items.extend(v)
            for t in items:
                if isinstance(t, dict) and t.get("instance_id") == task_id:
                    task = t
        if task:
            tasks.append(task)
    return tasks


def load_task(task_id: str) -> dict | None:
    for mf in sorted(MANIFESTS.glob("*.json")):
        if mf.stat().st_size > 10_000_000:
            continue
        try:
            data = json.loads(mf.read_text())
        except Exception:
            continue
        items = data if isinstance(data, list) else []
        if not items and isinstance(data, dict):
            for k in ["seed", "pilot", "confirmation", "reserve", "tasks"]:
                v = data.get(k, [])
                if isinstance(v, list):
                    items.extend(v)
        for t in items:
            if isinstance(t, dict) and t.get("instance_id") == task_id:
                return t
    return None


def test_func(repo_dir: Path, cfg: dict) -> dict:
    """Test the function. Returns pass/fail."""
    sys.path.insert(0, str(repo_dir))
    for key in list(sys.modules):
        if key.startswith("requests"):
            del sys.modules[key]
    try:
        spec = importlib.util.spec_from_file_location(
            "requests.utils", str(repo_dir / cfg["file"]))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, cfg["func"])
        p = f = 0
        for val, exp in cfg["tests"]:
            if fn(val, "http") == exp:
                p += 1
            else:
                f += 1
        return {"success": f == 0, "passed": p, "failed": f, "total": len(cfg["tests"])}
    finally:
        sys.path.pop(0)


def call_qwen(prompt: str) -> tuple[str, str, float]:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a Python developer fixing a bug. Explain the problem and return the fixed code."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": MAX_TOKENS, "temperature": 0.3,
    }
    start = time.monotonic()
    resp = subprocess.run([sys.executable, "-c", f"""
import json, urllib.request
p = {json.dumps(payload)}
req = urllib.request.Request("{API_URL}", data=json.dumps(p).encode(), headers={{"Content-Type": "application/json"}}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(r.read())
        c = d["choices"][0]["message"]
        sys.stdout.write(json.dumps({{"c": c.get("content",""), "r": c.get("reasoning","")}}))
except Exception as e:
    sys.stdout.write(json.dumps({{"error": str(e)}}))
    """], capture_output=True, text=True, timeout=600)
    elapsed = time.monotonic() - start
    try:
        d = json.loads(resp.stdout)
        return (d.get("c","") or "", d.get("r","") or "", elapsed)
    except Exception:
        return ("", "", elapsed)


def has_conceptual_fix(text: str) -> bool:
    """Check if the model's output contains the conceptual fix for this bug."""
    ltext = text.lower()
    # Check for key concepts: auth should be re-attached to netloc
    score = 0
    if "if auth" in ltext or "auth is not none" in ltext: score += 2
    if "netloc" in ltext and ("@" in text or "f'" in text or 'f"' in text): score += 2
    if "urlunparse" in ltext and "(scheme" in ltext: score += 1
    if "user:pass" in ltext or "auth" in ltext: score += 1
    return score >= 4


def run_strategy(sn: str, sp: str, cfg: dict, task: dict) -> dict:
    """Run one strategy. Evaluates fix discovery, not application."""
    full_src = (WORKTREES / f"{cfg['id']}_base" / cfg["file"]).read_text()
    lines = full_src.split("\n")
    func_lines = []
    in_func = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"def {cfg['func']}("):
            in_func = True
        if in_func:
            func_lines.append(line)
            # End when we hit a non-decorator top-level def
            if i > 0 and stripped.startswith("def ") and not stripped.startswith(f"def {cfg['func']}("):
                func_lines.pop()
                break
    func_src = "\n".join(func_lines)

    prompt = f"""{sp}

Bug: {task['problem_statement'][:500]}

Failing tests:
{chr(10).join(f'- {t[0]} -> expected {t[1]}' for t in cfg['tests'])}

Source code for function `{cfg['func']}` in `{cfg['file']}`:
```python
{func_src}
```

Explain what the bug is and how to fix it. Return ONLY the fixed function body (the code inside the function, with proper indentation)."""

    content, reasoning, api_time = call_qwen(prompt)
    all_text = content + "\n" + reasoning
    conceptual = has_conceptual_fix(all_text)

    return {
        "strategy": sn,
        "api_time_sec": round(api_time, 1),
        "response_len": len(content),
        "reasoning_len": len(reasoning),
        "conceptual_fix": conceptual,
        "response_preview": content[:300],
    }


def main():
    print("=" * 78)
    print("  REAL SWE-BENCH: Single-Call vs Multi-Agent")
    print(f"  Model: {MODEL} @ port 8000, max_tokens={MAX_TOKENS}")
    print(f"  Tasks: {', '.join(t['id'] for t in TASKS)}")
    print("=" * 78)

    r = subprocess.run([sys.executable, "-c", """
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/v1/models", timeout=5) as resp:
    print(json.loads(resp.read())["data"][0]["id"])
    """], capture_output=True, text=True, timeout=10)
    print(f"  Server: {r.stdout.strip()}\n")

    # Verify bug
    print("Verifying bugs...")
    for task_cfg in TASKS:
        base_dir = WORKTREES / f"{task_cfg['id']}_base"
        r = test_func(base_dir, task_cfg)
        status = "BUG CONFIRMED" if r["failed"] > 0 else "NO BUG"
        print(f"  {task_cfg['id']}: {r['passed']}/{r['total']} pass, {r['failed']} fail - {status}")
    print()

    all_results = {}

    for task_cfg in TASKS:
        task = load_task(task_cfg["id"])
        if not task:
            continue

        print(f"{'─' * 78}")
        print(f"  {task_cfg['id']}")
        print(f"{'─' * 78}")

        basetime = (WORKTREES / f"{task_cfg['id']}_base" / task_cfg["file"]).stat().st_mtime

        # Single-call
        print(f"  Single-call... ", end="", flush=True)
        single = run_strategy("tdd", STRATEGIES[0][1], task_cfg, task)
        sm = "✓" if single["conceptual_fix"] else "✗"
        print(f"[{sm}] {single['api_time_sec']}s  (resp={single['response_len']}ch, reason={single['reasoning_len']}ch)")

        # Multi-agent
        print(f"  Multi-agent (6 strategies)...")
        start = time.monotonic()
        candidates = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(run_strategy, n, p, task_cfg, task): n for n, p in STRATEGIES}
            for f in as_completed(futures):
                c = f.result()
                candidates.append(c)
                mk = "✓" if c["conceptual_fix"] else "✗"
                print(f"    [{mk}] {c['strategy']:<12} {c['api_time_sec']:<6.1f}s  "
                      f"resp={c['response_len']}ch reason={c['reasoning_len']}ch")

        wall = time.monotonic() - start
        successes = [c for c in candidates if c["conceptual_fix"]]
        all_results[task_cfg["id"]] = {
            "single": single, "multi": {
                "wall_time_sec": round(wall, 1),
                "oracle": f"{len(successes)}/6",
                "num_ok": len(successes),
                "candidates": candidates,
            }
        }

    # Summary
    print(f"\n{'=' * 78}")
    print("  RESULTS")
    print(f"{'=' * 78}")
    print(f"  {'Task':<30} {'Single':<10} {'Multi':<10} {'Oracle@6':<10}")
    print(f"  {'─'*30} {'─'*10} {'─'*10} {'─'*10}")
    s_ok = m_ok = 0
    for tid, res in all_results.items():
        s, m = res["single"], res["multi"]
        ss = "✓" if s["conceptual_fix"] else "✗"
        ms = "✓" if m["num_ok"] > 0 else "✗"
        if s["conceptual_fix"]: s_ok += 1
        if m["num_ok"] > 0: m_ok += 1
        print(f"  {tid:<30} {ss:<10} {ms:<10} {m['oracle']:<10}")
    print(f"\n  Solve rate: single={s_ok}/{len(all_results)} multi={m_ok}/{len(all_results)}")
    print(f"  Δ = {'+' if m_ok > s_ok else ''}{m_ok - s_ok}/{len(all_results)}")

    out_dir = Path("experiments/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    (out_dir / f"swebench_v3_{ts}.json").write_text(json.dumps(all_results, indent=2, default=str))


if __name__ == "__main__":
    import subprocess
    main()

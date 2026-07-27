#!/usr/bin/env python3
"""Self-contained development pipeline runner.
Usage: python3 run_dev.py "Build a todo API with priorities and categories"
       python3 run_dev.py --source path/to/source.py --test path/to/test.py
"""

import json, os, shutil, subprocess, sys, tempfile, textwrap, time, re
from pathlib import Path

API = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
MODEL = os.environ.get("VLLM_MODEL", "qwen")
MAX_TOKENS = 8192
TIMEOUT = 300

STRATEGIES = [
    ("tdd", "Read the tests first, then implement."),
    ("root-cause", "Design the data model first."),
    ("minimal", "Minimum implementation."),
    ("architecture", "Clean separation of concerns."),
    ("adversarial", "Handle all edge cases."),
    ("alternative", "Use a different approach."),
]


def qwen(prompt, temp=0.3):
    payload = {"model": MODEL, "messages": [
        {"role": "system", "content": "You are a Python developer. Return ONLY the requested code inside ```python."},
        {"role": "user", "content": prompt}], "max_tokens": MAX_TOKENS, "temperature": temp}
    start = time.monotonic()
    r = subprocess.run([sys.executable, "-c", f"""
import json, urllib.request, sys
p = {json.dumps(payload)}
req = urllib.request.Request("{API}/chat/completions", data=json.dumps(p).encode(),
    headers={{"Content-Type":"application/json"}}, method="POST")
try:
    with urllib.request.urlopen(req, timeout={TIMEOUT}) as resp:
        d = json.loads(resp.read())["choices"][0]["message"]
        sys.stdout.write(json.dumps({{"c":d.get("content","")or"","r":d.get("reasoning","")or""}}))
except Exception as e:
    sys.stdout.write(json.dumps({{"error":str(e)}}))
    """], capture_output=True, text=True, timeout=TIMEOUT+30)
    try:
        d = json.loads(r.stdout)
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


def run_tests(source_code, test_code, src_file="source.py", test_file="test_source.py"):
    with tempfile.TemporaryDirectory() as td:
        w = Path(td)
        (w/src_file).write_text(source_code)
        (w/test_file).write_text(test_code)
        r = subprocess.run([sys.executable,"-m","pytest","-q",test_file,"--tb=line"],
            cwd=w, capture_output=True, text=True, timeout=15)
        p=f=e=0
        for line in r.stdout.split("\n"):
            for i,t in enumerate(line.replace(",","").replace(".","").split()):
                if t=="passed":
                    try: p=int(line.split()[i-1])
                    except: pass
                if t=="failed":
                    try: f=int(line.split()[i-1])
                    except: pass
            if "error" in line.lower() and "passed" not in line and "failed" not in line:
                e = 1
        err = r.returncode if not p and not f and r.returncode else f
        return {"success":r.returncode==0,"passed":p,"failed":err,"output":r.stdout[-200:]}


def main():
    print("="*70)
    print("  HYDRACODE-6: Development Pipeline")
    print(f"  Model: {MODEL} @ {API}")
    print("="*70)

    # Parse args
    args = sys.argv[1:]
    feature = " ".join(args) if args else "Build a todo list API with CRUD operations"
    src_file, test_file = "source.py", "test_source.py"
    src_dir = Path(".")
    
    # Check for --source/--test flags
    if "--source" in args:
        si = args.index("--source")
        src_file = args[si+1]
    if "--test" in args:
        ti = args.index("--test")
        test_file = args[ti+1]

    # Verify server
    r = subprocess.run([sys.executable,"-c",f"""
import urllib.request, json
with urllib.request.urlopen("{API}/models",timeout=5) as resp:
    print(json.loads(resp.read())["data"][0]["id"])
    """], capture_output=True, text=True, timeout=10)
    if r.returncode:
        print(f"✗ Server not reachable at {API}")
        print(f"  Start with: vllm serve qwen --port 8000")
        sys.exit(1)
    print(f"  Server: {r.stdout.strip()} ✓\n")

    # STEP 1: Generate tests from feature description
    print(f"  Step 1: Generating tests from: {feature[:80]}...")
    test_prompt = f"""Generate pytest test functions for: {feature}

Requirements:
- Use pytest only (no unittest)
- Each test function tests one thing
- Use descriptive test names
- Cover: basic operations, edge cases, error handling
- Assumes all classes are in 'source.py'

Return ONLY the test code inside ```python."""
    c, r, _ = qwen(test_prompt)
    test_code = extract_code(c) or extract_code(r)
    if not test_code.strip():
        print(f"  ✗ Failed to generate tests")
        sys.exit(1)
    print(f"  ✓ Generated {test_code.count('def test_')} test functions")

    # STEP 2: Generate skeleton from tests
    print(f"  Step 2: Generating code skeleton...")
    skel_prompt = f"""Implement the classes needed by these tests.
The tests import from 'source'. Create ONLY the required classes and methods.
Use pass for method bodies — this is a skeleton.

Tests:
```python
{test_code}
```

Return ONLY the skeleton code inside ```python."""
    c, r, _ = qwen(skel_prompt)
    skeleton = extract_code(c) or extract_code(r)
    if not skeleton.strip():
        skeleton = "# Generated from tests\npass\n"
    print(f"  ✓ Skeleton: {skeleton.count('def ')} methods, {skeleton.count('class ')} classes")

    # STEP 3: Run pipeline (3→3→refine)
    print(f"\n  Step 3: Running pipeline (parallel rollouts)...")
    
    candidates = []
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {}
        for sn, sp in STRATEGIES:
            prompt = f"{sp}\n\nImplement the code to pass these tests:\n\n```python\n{test_code}\n```\n\nUse this skeleton:\n```python\n{skeleton}\n```\n\nReturn ONLY the full source.py implementation."
            futures[ex.submit(lambda s=sn, p=prompt: (s, *qwen(p)))] = sn
        for f in as_completed(futures):
            sn, c, r, t = f.result()
            code = extract_code(c) or extract_code(r)
            tr = run_tests(code, test_code)
            candidates.append({"sn":sn,"code":code,"t":t,**tr})
            print(f"    [{'✓' if tr['success'] else '✗'}] {sn:<12}: {tr['passed']}/{tr['passed']+tr['failed']} ({t:.1f}s)")

    best = max(candidates, key=lambda c: (c["passed"], -c.get("failed",99)))
    if best["success"]:
        print(f"\n  ✓ SOLVED in Phase 1 ({best['sn']}, {best['t']:.1f}s)")
        final_code = best["code"]
    else:
        # Refinement
        print(f"\n  Step 4: Refinement (test-feedback)...")
        err = ""
        with tempfile.TemporaryDirectory() as td:
            w = Path(td)
            (w/src_file).write_text(best["code"])
            (w/test_file).write_text(test_code)
            r = subprocess.run([sys.executable,"-m","pytest","-v",test_file,"--tb=long"],
                cwd=w, capture_output=True, text=True, timeout=15)
            err = (r.stdout + r.stderr)[:1500]
        
        ref_prompt = f"""The previous attempt was INCORRECT. Test failures:

```
{err}
```

Implement the code to pass these tests:
```python
{test_code}
```

Fix the ORIGINAL skeleton:
```python
{skeleton}
```

Return ONLY the full source.py implementation."""
        c, r, _ = qwen(ref_prompt, temp=0.1)
        final_code = extract_code(c) or extract_code(r)
        tr = run_tests(final_code, test_code)
        print(f"    [{'✓' if tr['success'] else '✗'}] refine: {tr['passed']}/{tr['passed']+tr['failed']}")

    # OUTPUT
    src_out = Path("output/source.py")
    src_out.parent.mkdir(exist_ok=True)
    src_out.write_text(final_code)
    
    test_out = Path("output/test_source.py")
    test_out.write_text(test_code)

    print(f"\n{'='*70}")
    print(f"  RESULTS")
    print(f"{'='*70}")
    print(f"  Source: output/source.py")
    print(f"  Tests:  output/test_source.py")
    print(f"  Final:  {'PASS' if tr.get('success', best['success']) else 'FAIL'}")
    print(f"\n  To run tests:")
    print(f"    cd output && python3 -m pytest test_source.py -v")


if __name__ == "__main__":
    main()

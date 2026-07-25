#!/usr/bin/env python3
"""Prepare buggy fixture versions and verify they fail."""

import shutil, subprocess, sys, tempfile
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "hydra-code/tests/e2e/fixtures"

BUG_PATCHES = {
    "pagination": {
        "source": "paginator.py",
        "test": "test_pagination.py",
        "perfect": lambda c: c.replace("start = page * per_page", "start = (page - 1) * per_page"),
        "verify_correct": lambda r: r.returncode == 0,
    },
    "requests_6028": {
        "source": "url_utils.py",
        "test": "test_url_utils.py",
        "perfect": lambda c: c.replace(
            "    if auth:\n        netloc = f\"{auth}@{netloc}\"\n", ""
        ),
        "verify_correct": lambda r: r.returncode == 0,
    },
}


def main():
    for name in ["pagination", "requests_6028"]:
        info = BUG_PATCHES[name]
        fixture_dir = FIXTURES_DIR / name
        source = fixture_dir / info["source"]
        test_file = fixture_dir / info["test"]
        buggy_code = source.read_text()

        print(f"=== {name} ===")
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            shutil.copy2(source, work / info["source"])
            shutil.copy2(test_file, work / info["test"])

            # Test buggy version
            r_buggy = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", info["test"], "--tb=no"],
                cwd=work, capture_output=True, text=True, timeout=10,
            )
            buggy_fails = r_buggy.returncode != 0

            # Apply perfect fix
            fixed_code = info["perfect"](buggy_code)
            (work / info["source"]).write_text(fixed_code)

            # Test fixed version
            r_fixed = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", info["test"], "--tb=no"],
                cwd=work, capture_output=True, text=True, timeout=10,
            )
            fixed_passes = r_fixed.returncode == 0

            print(f"  Buggy tests: {'FAIL ✓' if buggy_fails else 'PASS ✗'}")
            print(f"  Fixed tests: {'PASS ✓' if fixed_passes else 'FAIL ✗'}")
            print(f"  Buggy output: {r_buggy.stdout.strip()[-100:]}")
            if buggy_fails and fixed_passes:
                print(f"  → Ready for experiment ✓")
            else:
                print(f"  → NOT usable: buggy={'fail' if buggy_fails else 'pass'}, fixed={'pass' if fixed_passes else 'fail'}")
        print()


if __name__ == "__main__":
    main()

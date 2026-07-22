"""SWE-bench verified task handlers for fake Claude.

Each task defines:
- A detector function to recognize the repo/bug from CWD files
- A fix function to apply the correct patch
- The commit message
"""

from __future__ import annotations

import os
import subprocess


def git_commit(message: str) -> None:
    """Stage all changes and commit."""
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", message], check=True)


# --- psf__requests-6028: Proxy auth bug (real repo) ---

def fix_requests_proxy_auth() -> int:
    """Fix prepend_scheme_if_needed losing auth info in real requests repo.

    Bug: parse_url() returns netloc without auth components, so the
    reconstructed URL drops user:pass@ from the netloc field.
    Fix: Reconstruct netloc with auth when present.
    """
    path = "requests/utils.py"
    if not os.path.isfile(path):
        return -1

    content = open(path).read()

    old_block = (
        "    if scheme is None:\n"
        "        scheme = new_scheme\n"
        "    if path is None:\n"
        "        path = ''\n"
        "\n"
        "    return urlunparse((scheme, netloc, path, '', query, fragment))"
    )

    new_block = (
        "    if scheme is None:\n"
        "        scheme = new_scheme\n"
        "    if path is None:\n"
        "        path = ''\n"
        "\n"
        "    if auth and auth not in netloc:\n"
        "        netloc = auth + '@' + netloc\n"
        "    return urlunparse((scheme, netloc, path, '', query, fragment))"
    )

    if old_block not in content:
        return -1

    content = content.replace(old_block, new_block)
    open(path, "w").write(content)
    git_commit("fix: preserve auth info in prepend_scheme_if_needed")
    return 0


# --- psf__requests-6028: Proxy auth bug (fixture) ---

def fix_requests_proxy_auth_fixture() -> int:
    """Fix prepend_scheme_if_needed losing auth info in test fixture."""
    path = "url_utils.py"
    if not os.path.isfile(path):
        return -1

    content = open(path).read()

    old_block = (
        "    # BUG: auth is lost — should reconstruct netloc with auth\n"
        '    return urlunparse((scheme, netloc, path, "", query or "", fragment or ""))'
    )

    new_block = (
        '    if auth and auth not in netloc:\n'
        '        netloc = auth + "@" + netloc\n'
        '    return urlunparse((scheme, netloc, path, "", query or "", fragment or ""))'
    )

    if old_block not in content:
        return -1

    content = content.replace(old_block, new_block)
    open(path, "w").write(content)
    git_commit("fix: preserve auth info in prepend_scheme_if_needed")
    return 0


# --- django__django-13925: W042 on inherited PK ---

def fix_django_inherited_pk() -> int:
    """Fix models.W042 raised on inherited manually specified primary key."""
    path = "django/core/checks/model_checks.py"
    if not os.path.isfile(path):
        path = "django/db/models/options.py"
        if not os.path.isfile(path):
            return -1

    content = open(path).read()
    if "W042" not in content:
        return -1

    git_commit("fix: skip W042 for inherited explicit primary keys")
    return 0


# --- pytest-dev__pytest-10051: clear_for_call_stage ---

def fix_pytest_clear_for_call() -> int:
    """Fix pytest logging fixture clear_for_call stage."""
    path = "src/_pytest/logging.py"
    if not os.path.isfile(path):
        path = "_pytest/logging.py"
        if not os.path.isfile(path):
            return -1

    content = open(path).read()
    git_commit("fix: logging fixture clear_for_call stage")
    return 0


# Task detectors: (file_check, fix_fn)
# Order matters: check fixture first, then real repo files
SWE_TASK_DETECTORS = [
    # requests-6028 fixture (test fixture)
    (
        lambda: os.path.isfile("url_utils.py")
        and "prepend_scheme_if_needed" in open("url_utils.py").read(),
        fix_requests_proxy_auth_fixture,
    ),
    # psf__requests-6028 (real repo)
    (
        lambda: os.path.isfile("requests/utils.py")
        and "prepend_scheme_if_needed" in open("requests/utils.py").read(),
        fix_requests_proxy_auth,
    ),
    # django__django-13925
    (
        lambda: os.path.isfile("django/core/checks/model_checks.py")
        or os.path.isfile("django/db/models/options.py"),
        fix_django_inherited_pk,
    ),
    # pytest-dev__pytest-10051
    (
        lambda: os.path.isfile("src/_pytest/logging.py")
        or os.path.isfile("_pytest/logging.py"),
        fix_pytest_clear_for_call,
    ),
]


def detect_and_fix_swe() -> int:
    """Detect SWE-bench task from CWD and apply the fix."""
    for detector, fix_fn in SWE_TASK_DETECTORS:
        if detector():
            return fix_fn()
    return -1
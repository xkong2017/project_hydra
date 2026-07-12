AGENT_ROLES = {
    "security_reviewer": {
        "name": "Security Reviewer",
        "prompt": """Review the code below for security vulnerabilities.
Find: SQL injection, XSS, hardcoded secrets, auth bypass, insecure data handling.
For each issue list: severity, location, risk, fix.

```
{code}```""",
    },
    "performance_analyst": {
        "name": "Performance Analyst",
        "prompt": """Review the code below for performance issues.
Find: bad algorithms, blocking I/O, memory waste, missing cache.
For each issue list: impact, location, better approach.

```
{code}```""",
    },
    "architecture_critic": {
        "name": "Architecture Critic",
        "prompt": """Review the code below for architecture quality.
Find: coupling issues, missing patterns, scalability limits.
For each issue list: principle violated, location, fix.

```
{code}```""",
    },
    "test_coverage_checker": {
        "name": "Test Coverage Checker",
        "prompt": """Review the code below for test coverage gaps.
Find: untested paths, missing edge cases, integration gaps.
For each gap list: risk, scenario, test outline.

```
{code}```""",
    },
    "style_auditor": {
        "name": "Style Auditor",
        "prompt": """Review the code below for style and readability.
Find: bad naming, deep nesting, dead code, missing docs.
For each issue list: severity, location, improved code.

```
{code}```""",
    },
    "summary_synthesizer": {
        "name": "Summary Synthesizer",
        "prompt": """Synthesize these agent reports into an executive summary.
Include: health score (1-10), top 5 issues, improvement roadmap, key strengths.

{agent_reports}""",
    },
}


def get_agent_prompts(role_names: list[str] | None = None) -> dict:
    if role_names:
        return {k: AGENT_ROLES[k] for k in role_names if k in AGENT_ROLES}
    return AGENT_ROLES.copy()
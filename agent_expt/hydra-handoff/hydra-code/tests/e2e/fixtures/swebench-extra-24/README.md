# E2: Command injection — shell command not escaped

**Bug**: run_command() uses shell=True without escaping.

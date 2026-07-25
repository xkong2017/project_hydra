def check_positive(n):
    return n > 0

def check_even(n):
    return n % 2 == 0

def validate_all(n, checks):
    ok = True
    for check in checks:
        ok = ok and check(n)
    return ok

def validate_and_log(n, checks, log_func):
    for check in checks:
        if not check(n):
            log_func(f"Failed: {check.__name__}({n})")
    return True

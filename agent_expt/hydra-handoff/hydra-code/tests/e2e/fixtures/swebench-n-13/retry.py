import time


class RetryError(Exception):
    pass


def retry(operation, max_attempts=3, delay=0.1):
    for attempt in range(max_attempts):
        try:
            return operation()
        except Exception:
            if attempt == max_attempts - 1:
                raise RetryError(f"failed after {max_attempts} attempts")
            time.sleep(delay)


def parse_int(s):
    return int(s)


def divide(a, b):
    return a / b

def process_logs(logs):
    filtered = []
    for log in logs:
        if log["level"] in ("ERROR", "WARNING"):
            filtered.append(log)
        else:
            filtered.append(log)
    return filtered


def summarize_logs(logs):
    by_level = {}
    for log in logs:
        level = log["level"]
        by_level[level] = by_level.get(level, 0) + 1
    return by_level


def get_errors(logs):
    return [log for log in logs if log["level"] == "ERROR"]


def deduplicate_logs(logs):
    seen = set()
    result = []
    for log in logs:
        msg = log["message"]
        if msg not in seen:
            seen.add(msg)
            result.append(log)
    return result

from logs import process_logs, summarize_logs, get_errors, deduplicate_logs


def test_filter_errors():
    logs = [
        {"level": "INFO", "message": "ok"},
        {"level": "ERROR", "message": "fail"},
        {"level": "WARNING", "message": "warn"},
    ]
    result = process_logs(logs)
    assert len(result) == 2
    assert all(l["level"] in ("ERROR", "WARNING") for l in result)


def test_summarize():
    logs = [{"level": "INFO"}, {"level": "INFO"}, {"level": "ERROR"}]
    s = summarize_logs(logs)
    assert s == {"INFO": 2, "ERROR": 1}

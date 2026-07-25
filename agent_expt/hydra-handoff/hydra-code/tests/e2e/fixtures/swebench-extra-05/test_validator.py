from validator import validate_all, validate_and_log, check_positive, check_even


def test_all_pass():
    assert validate_all(4, [check_positive, check_even])


def test_first_fails_short_circuit():
    log_entries = []
    def log(msg):
        log_entries.append(msg)
    result = validate_and_log(-2, [check_positive, check_even], log)
    assert result is False
    assert len(log_entries) == 1, f"Expected 1 log, got {len(log_entries)}: {log_entries}"

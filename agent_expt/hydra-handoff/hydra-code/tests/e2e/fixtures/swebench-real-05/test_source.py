from source import LogCapture

def test_get_records():
    lc = LogCapture()
    lc._records.append("error")
    assert len(lc.get_records("call")) == 1

def test_clear_empties():
    lc = LogCapture()
    lc._records.append("error")
    lc.clear()
    assert len(lc.get_records("call")) == 0

def test_get_records_after_clear():
    lc = LogCapture()
    lc._records.append("error")
    lc.clear()
    result = lc.get_records("call")
    assert len(result) == 0, "get_records should return empty after clear!"

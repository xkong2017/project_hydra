from source import check_similar

def test_no_similar():
    assert check_similar(["a", "b", "c"], 3) == []

def test_zero_min_disables():
    result = check_similar(["a", "b", "a"], 0)
    assert result == [], "min_lines=0 should disable checking"

def test_finds_similar():
    result = check_similar(["a", "b", "a"], 1)
    assert len(result) > 0
